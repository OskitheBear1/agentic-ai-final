"""Stage 2 — Enrich. Model role: Jev (TypeSafe) fixed-choice classifier. Code: validation, quote, entities.

Input:  pending in-scope reviews from the run's state DB (written by ingest).
Output: `results` rows (completed / quarantined) + one `calls` row per attempted model call.
Batching: up to 50 pending reviews per batch. Exact duplicate texts are sent once; the other IDs reuse the
validated result with `cache_source_id`. Each Jev request carries exactly one review (1 <= 50).
Saved atomically after every batch. Stop rules: budget cap, --max-batches, --time-limit, Ctrl-C.
"""

import hashlib
import json
import random
import signal
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from .common import INTENTS, TOPICS, load_env
from .features import FEATURE_VERSION, entities, evidence_quote
from .ledger import BudgetExceeded, call_cost, load_rates
from .state import connect, end_invocation, log_call, start_invocation

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from prompts import jev_questions_v1 as Q  # noqa: E402

SCHEMA_VERSION = "schema-v1"
BATCH_SIZE = 50
JEV_MODEL = "jev-latest"
NEEDS_REVIEW_CONF = 0.5          # topic or intent confidence below this -> needs_review
EST_TOKENS_PER_CALL = 1600       # worst-case reservation (measured ~1,170 input tokens per call)
MAX_TRANSIENT_ATTEMPTS = 3       # API errors: initial + 2 retries with backoff + jitter
MAX_INVALID_ATTEMPTS = 2         # invalid model output: initial + 1 retry, then quarantine


class InvalidOutput(ValueError):
    pass


class InjectedAPIError(RuntimeError):
    """Synthetic transient failure used only by the declared fault-injection test (--inject-faults)."""


def questions():
    from typesafe_sdk import Choice, Score
    return {"topic": Choice(**Q.TOPIC), "intent": Choice(**Q.INTENT),
            "severity": Choice(**Q.SEVERITY), "sentiment": Score(**Q.SENTIMENT)}


def label_config_for(served_model):
    return f"{served_model}+{Q.PROMPT_VERSION}+{SCHEMA_VERSION}+{FEATURE_VERSION}"


def to_record(text, answers):
    """Map Jev answers into the common schema; raise InvalidOutput if anything is off."""
    try:
        topic = answers["topic"].choice
        intent = answers["intent"].choice
        severity = int(answers["severity"].choice)
        raw_score = float(answers["sentiment"].score)
    except (KeyError, AttributeError, TypeError, ValueError) as e:
        raise InvalidOutput(f"missing/typed answer: {e}")
    if topic not in TOPICS or intent not in INTENTS or not 1 <= severity <= 5 or not 0 <= raw_score <= 4:
        raise InvalidOutput(f"out-of-schema answer {topic}/{intent}/{severity}/{raw_score}")
    conf = {k: round(float(answers[k].confidence), 4) for k in ("topic", "intent", "severity", "sentiment")}
    quote = evidence_quote(text, topic)
    if not quote or quote not in text:
        raise InvalidOutput("evidence quote not an exact substring")
    return {"topic": topic, "intent": intent, "severity": severity,
            "sentiment": round(raw_score / 2 - 1, 4),  # 5 levels 0..4 -> -1..1
            "entities": entities(text), "evidence_quote": quote,
            "needs_review": bool(min(conf["topic"], conf["intent"]) < NEEDS_REVIEW_CONF),
            "confidence": conf}


class Faults:
    """Deterministic fault injection for the declared retry test. Disabled unless --inject-faults is given."""

    def __init__(self, spec):
        self.p = {}
        for part in (spec or "").split(","):
            if "=" in part:
                k, v = part.split("=")
                self.p[k.strip()] = float(v)

    def hit(self, kind, review_id, attempt):
        p = self.p.get(kind, 0)
        if not p:
            return False
        h = int(hashlib.sha256(f"{kind}:{review_id}:{attempt}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        return h < p


class Enricher:
    def __init__(self, run, ledger, workers=1, faults=None, rps=20.0):
        load_env()
        from typesafe_sdk import RetryPolicy, TypeSafeClient
        self.run, self.ledger, self.workers = run, ledger, workers
        # SDK retries off: our loop retries so that every attempt is logged and costed.
        self.client = TypeSafeClient(model=JEV_MODEL, retry=RetryPolicy(max_retries=0), timeout=30.0)
        self.questions = questions()
        self.faults = Faults(faults)
        self.rates = load_rates()
        self.min_interval = 1.0 / rps
        self._rate_lock = threading.Lock()
        self._next_slot = 0.0
        self.served_model = None

    def _throttle(self):
        with self._rate_lock:
            now = time.monotonic()
            wait = self._next_slot - now
            self._next_slot = max(now, self._next_slot) + self.min_interval
        if wait > 0:
            time.sleep(wait)

    def classify(self, review_id, text, phase, inv_id):
        """Return (record_or_None, reason, attempts, call_logs). Never raises except BudgetExceeded."""
        from typesafe_sdk import (TypeSafeAPIConnectionError, TypeSafeAPITimeoutError, TypeSafeInternalServerError,
                                  TypeSafeRateLimitError)
        transient = (TypeSafeRateLimitError, TypeSafeInternalServerError, TypeSafeAPITimeoutError,
                     TypeSafeAPIConnectionError, InjectedAPIError)
        logs, attempt, invalid_count, transient_count = [], 0, 0, 0
        while True:
            attempt += 1
            key = f"{review_id}:{attempt}:{uuid.uuid4().hex}"
            est = EST_TOKENS_PER_CALL * self.rates[("jev", "input_tokens")] + len(text) / 3 * self.rates[("jev", "input_tokens")]
            self.ledger.reserve(key, est)  # raises BudgetExceeded -> caller stops admitting work
            log = {"run": self.run, "role": "enrich", "review_ids": [review_id], "phase": phase, "attempt": attempt,
                   "invocation": inv_id, "started_at": time.time(), "fault_injected": False}
            t0 = time.monotonic()
            try:
                if self.faults.hit("api_error", review_id, attempt):
                    log["fault_injected"] = True
                    raise InjectedAPIError("injected transient API error (fault-injection test)")
                self._throttle()
                resp = self.client.system_one(state=text, questions=self.questions)
                log["duration_s"] = round(time.monotonic() - t0, 4)
                raw = getattr(resp, "raw_http_response", None)
                log["request_id"] = (raw.headers.get("x-typesafe-request-id") if raw is not None else None) or f"local-{uuid.uuid4().hex}"
                log["model"] = resp.model
                log["input_tokens"] = int(resp.usage.input_tokens or 0)
                log["output_tokens"] = int(resp.usage.output_tokens or 0)
                log["cost_usd"] = call_cost(resp.model, log, self.rates)
                self.ledger.settle(key, log["request_id"], self.run, "enrich", resp.model, log["cost_usd"])
                if self.served_model is None:
                    self.served_model = resp.model
                elif resp.model != self.served_model:
                    raise RuntimeError(f"served model changed mid-run: {self.served_model} -> {resp.model}; stop and re-version")
                log["label_config"] = label_config_for(resp.model)
                answers = dict(resp.answers)
                if self.faults.hit("malformed", review_id, attempt):
                    log["fault_injected"] = True
                    answers.pop("topic", None)  # simulate a malformed response (real call, real cost)
                try:
                    rec = to_record(text, answers)
                except InvalidOutput as e:
                    invalid_count += 1
                    log.update(outcome="failed", error=f"invalid_output: {e}")
                    logs.append(log)
                    if invalid_count >= MAX_INVALID_ATTEMPTS:
                        return None, "invalid_model_output_after_retry", attempt, logs
                    continue
                log["outcome"] = "succeeded"
                logs.append(log)
                rec["label_config"] = log["label_config"]
                return rec, None, attempt, logs
            except transient as e:
                self.ledger.release(key)
                transient_count += 1
                log.update(outcome="failed", error=f"{type(e).__name__}: {str(e)[:200]}", model=log.get("model") or JEV_MODEL,
                           request_id=getattr(e, "request_id", None) or f"failed-{uuid.uuid4().hex}",
                           input_tokens=0, output_tokens=0, cost_usd=0.0, duration_s=round(time.monotonic() - t0, 4))
                logs.append(log)
                if transient_count >= MAX_TRANSIENT_ATTEMPTS:
                    return None, "api_error_after_retries", attempt, logs
                time.sleep(min(8.0, 0.5 * 2 ** (transient_count - 1)) * (1 - random.random() * 0.25))
            except BudgetExceeded:
                raise
            except Exception as e:  # non-retryable (auth, bad request, ...): log and quarantine this review
                self.ledger.release(key)
                log.update(outcome="failed", error=f"{type(e).__name__}: {str(e)[:200]}", model=log.get("model") or JEV_MODEL,
                           request_id=getattr(e, "request_id", None) or f"failed-{uuid.uuid4().hex}",
                           input_tokens=0, output_tokens=0, cost_usd=0.0, duration_s=round(time.monotonic() - t0, 4))
                logs.append(log)
                if "served model changed" in str(e):
                    raise
                return None, f"api_error_nonretryable:{type(e).__name__}", attempt, logs


def run_enrich(run, ledger, workers=1, max_batches=None, time_limit=None, faults=None, rps=20.0, retry_quarantined=False):
    con = connect(run)
    if retry_quarantined:
        con.execute("DELETE FROM results WHERE status='quarantined' AND reason LIKE 'api_error%'")
    done = con.execute("SELECT COUNT(*) FROM results WHERE status='completed'").fetchone()[0]
    phase = "resume" if done else "initial"
    inv = start_invocation(con, "enrich", phase, {"workers": workers, "max_batches": max_batches, "faults": faults})
    enricher = Enricher(run, ledger, workers=workers, faults=faults, rps=rps)
    if done:  # resume: reuse the existing label_config so cache lookups and config-drift checks work
        cfg = con.execute("SELECT label_config FROM results WHERE status='completed' AND cache_source_id IS NULL "
                          "ORDER BY completed_at DESC LIMIT 1").fetchone()[0]
        enricher.served_model = cfg.split("+")[0]

    stop = {"flag": None}
    def on_sigint(sig, frame):
        stop["flag"] = "interrupted_by_user"
        print("\n[enrich] Ctrl-C received: finishing the current batch, then stopping…", flush=True)
    old = signal.signal(signal.SIGINT, on_sigint)

    t_start = time.monotonic()
    batches = completed = quarantined = cache_hits = 0
    status = "finished"
    try:
        while True:
            if stop["flag"]:
                status = stop["flag"]; break
            if max_batches is not None and batches >= max_batches:
                status = "stopped_max_batches"; break
            if time_limit and time.monotonic() - t_start > time_limit:
                status = "stopped_time_limit"; break
            pending = con.execute(
                "SELECT r.review_id, r.review_text, r.text_sha256 FROM reviews r LEFT JOIN results x USING(review_id) "
                "WHERE r.pre_status='pending' AND x.review_id IS NULL ORDER BY r.scope_rank LIMIT ?", (BATCH_SIZE,)).fetchall()
            if not pending:
                break
            batches += 1
            batch_no = con.execute("SELECT COALESCE(MAX(batch_no),0)+1 FROM results").fetchone()[0]

            # 1) result cache: exact text already completed under the current label_config in this run
            originals, rows_out, followers = {}, [], {}
            for p in pending:
                if p["text_sha256"] in originals:
                    followers.setdefault(p["text_sha256"], []).append(p["review_id"])
                    continue
                cfg = label_config_for(enricher.served_model) if enricher.served_model else None
                hit = cfg and con.execute(
                    "SELECT x.* FROM results x JOIN reviews r USING(review_id) WHERE r.text_sha256=? AND x.status='completed' "
                    "AND x.cache_source_id IS NULL AND x.label_config=? LIMIT 1", (p["text_sha256"], cfg)).fetchone()
                if hit:
                    rows_out.append(dict(hit) | {"review_id": p["review_id"], "cache_source_id": hit["review_id"],
                                                 "attempts": 0, "batch_no": batch_no, "phase": phase, "completed_at": time.time()})
                    cache_hits += 1
                else:
                    originals[p["text_sha256"]] = p

            # 2) one Jev call per distinct uncached text (bounded worker pool)
            def work(p):
                return p, enricher.classify(p["review_id"], p["review_text"], phase, inv)
            call_logs = []
            budget_hit = None
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(work, p) for p in originals.values()]
                for f in futures:
                    try:
                        p, (rec, reason, attempts, logs) = f.result()
                    except BudgetExceeded as e:
                        budget_hit = str(e)
                        continue
                    call_logs += logs
                    base = {"review_id": p["review_id"], "attempts": attempts, "batch_no": batch_no, "phase": phase,
                            "completed_at": time.time(), "cache_source_id": None}
                    if rec:
                        row = base | rec | {"status": "completed", "reason": None}
                        rows_out.append(row)
                        for fid in followers.get(p["text_sha256"], []):
                            rows_out.append(row | {"review_id": fid, "cache_source_id": p["review_id"], "attempts": 0})
                            cache_hits += 1
                    else:
                        rows_out.append(base | {"status": "quarantined", "reason": reason})
                        for fid in followers.get(p["text_sha256"], []):
                            rows_out.append(base | {"review_id": fid, "status": "quarantined", "reason": reason, "attempts": 0})

            # 3) atomic save of the whole batch (results + every attempted call)
            con.execute("BEGIN IMMEDIATE")
            for c in call_logs:
                log_call(con, c)
            for r in rows_out:
                if budget_hit and r.get("status") is None:
                    continue
                con.execute("INSERT OR REPLACE INTO results(review_id,status,topic,intent,sentiment,severity,entities,evidence_quote,"
                            "needs_review,label_config,cache_source_id,attempts,reason,confidence,batch_no,phase,completed_at) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (r["review_id"], r["status"], r.get("topic"), r.get("intent"), r.get("sentiment"), r.get("severity"),
                             json.dumps(r["entities"]) if isinstance(r.get("entities"), list) else r.get("entities"),
                             r.get("evidence_quote"), int(r["needs_review"]) if r.get("needs_review") is not None else None,
                             r.get("label_config"), r.get("cache_source_id"), r.get("attempts"), r.get("reason"),
                             json.dumps(r["confidence"]) if isinstance(r.get("confidence"), dict) else r.get("confidence"),
                             r["batch_no"], r["phase"], r["completed_at"]))
            con.execute("COMMIT")
            completed += sum(r["status"] == "completed" for r in rows_out)
            quarantined += sum(r["status"] == "quarantined" for r in rows_out)
            if batches % 20 == 0 or batches <= 2:
                el = time.monotonic() - t_start
                print(f"[enrich] batch {batches}: +{completed} completed, {quarantined} quarantined, {cache_hits} cache hits, "
                      f"spent ${ledger.spent():.4f}, {el:.0f}s, {completed / max(el, 1e-9):.1f} rec/s", flush=True)
            if budget_hit:
                status = "stopped_budget"; print("[enrich]", budget_hit); break
    finally:
        signal.signal(signal.SIGINT, old)
        summary = {"phase": phase, "batches": batches, "completed": completed, "quarantined": quarantined,
                   "cache_hits": cache_hits, "wall_s": round(time.monotonic() - t_start, 3), "workers": workers,
                   "label_config": label_config_for(enricher.served_model) if enricher.served_model else None}
        end_invocation(con, inv, status, summary)
        con.close()
    print(f"[enrich] {status}: {summary}")
    return status, summary

"""One bounded Claude call with structured output, cost accounting, retries and call logging.

Used by the verify (Haiku), group-taxonomy (Haiku) and memo (Sonnet) roles. Every attempt —
including failures — becomes a `calls` row; cost is computed from returned usage × rates.csv.
"""

import json
import random
import time
import uuid

from .common import load_env
from .ledger import BudgetExceeded, call_cost, load_rates

MAX_TRANSIENT_ATTEMPTS = 3
MAX_INVALID_ATTEMPTS = 2

_client = None


def client():
    global _client
    if _client is None:
        load_env()
        import anthropic
        _client = anthropic.Anthropic(max_retries=0, timeout=120.0)  # our loop retries and logs each attempt
    return _client


def call(*, run, role, model, system, user, schema, review_ids, ledger, invocation, max_tokens, est_usd,
         validate=None, thinking_off=False, effort="low", phase=None):
    """Return (parsed_json_or_None, logs, error). `validate(parsed)` returns a list of problems ([] = ok)."""
    import anthropic
    rates = load_rates()
    logs, attempt, invalid, transient = [], 0, 0, 0
    messages = [{"role": "user", "content": user}]
    while True:
        attempt += 1
        key = f"{role}:{uuid.uuid4().hex}"
        ledger.reserve(key, est_usd)
        log = {"run": run, "role": role, "review_ids": review_ids, "model": model, "phase": phase,
               "attempt": attempt, "invocation": invocation, "started_at": time.time(), "fault_injected": False}
        t0 = time.monotonic()
        try:
            params = dict(model=model, max_tokens=max_tokens,
                          system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                          messages=messages,
                          output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}})
            if thinking_off:
                params["thinking"] = {"type": "disabled"}
            resp = client().messages.create(**params)
            u = resp.usage
            log.update(request_id=resp._request_id or resp.id, model=resp.model, duration_s=round(time.monotonic() - t0, 4),
                       input_tokens=u.input_tokens or 0, output_tokens=u.output_tokens or 0,
                       cache_read_input_tokens=getattr(u, "cache_read_input_tokens", 0) or 0,
                       cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", 0) or 0)
            log["cost_usd"] = call_cost(resp.model, log, rates)
            ledger.settle(key, log["request_id"], run, role, resp.model, log["cost_usd"])
            problems = []
            if resp.stop_reason != "end_turn":
                problems = [f"stop_reason={resp.stop_reason}"]
                parsed = None
            else:
                text = next(b.text for b in resp.content if b.type == "text")
                parsed = json.loads(text)
                problems = validate(parsed) if validate else []
            if problems:
                invalid += 1
                log.update(outcome="failed", error="invalid_output: " + "; ".join(problems)[:500])
                logs.append(log)
                if invalid >= MAX_INVALID_ATTEMPTS:
                    return None, logs, log["error"]
                # Retry once, telling the model exactly what failed validation.
                messages = [{"role": "user", "content": user},
                            {"role": "assistant", "content": text if parsed is not None else "{}"},
                            {"role": "user", "content": "Your answer failed validation: " + "; ".join(problems)[:1500] +
                             ". Return a corrected JSON answer for the original request."}]
                continue
            log["outcome"] = "succeeded"
            logs.append(log)
            return parsed, logs, None
        except BudgetExceeded:
            raise
        except (anthropic.RateLimitError, anthropic.InternalServerError, anthropic.APIConnectionError,
                anthropic.APITimeoutError) as e:
            ledger.release(key)
            transient += 1
            log.update(outcome="failed", error=f"{type(e).__name__}: {str(e)[:200]}", request_id=f"failed-{uuid.uuid4().hex}",
                       input_tokens=0, output_tokens=0, cost_usd=0.0, duration_s=round(time.monotonic() - t0, 4))
            logs.append(log)
            if transient >= MAX_TRANSIENT_ATTEMPTS:
                return None, logs, log["error"]
            time.sleep(min(20.0, 2 ** transient) * (1 - random.random() * 0.25))
        except Exception as e:
            ledger.release(key)
            log.update(outcome="failed", error=f"{type(e).__name__}: {str(e)[:300]}", request_id=f"failed-{uuid.uuid4().hex}",
                       input_tokens=0, output_tokens=0, cost_usd=0.0, duration_s=round(time.monotonic() - t0, 4))
            logs.append(log)
            return None, logs, log["error"]

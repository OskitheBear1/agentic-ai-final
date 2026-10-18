"""100-review cost and runtime calculator (COST_CALCULATOR.md).

DEFAULT = OFFLINE REPLAY. No API key, no network, no model calls:
    python3 cost/calculator.py                         # recompute everything from saved evidence -> cost/report.md
    python3 cost/calculator.py --rates-multiplier 2    # sanity check: API subtotal doubles, time unchanged
    python3 cost/calculator.py --scope 660609          # change projected volume; measured pilot is unchanged

Evidence collection (no API calls; copies saved pilot/dev-run logs into cost/):
    python3 cost/calculator.py collect --pilot-run pilot --refresh-runs dev500,dev10k

Paid pilot execution is a separate, explicit command (cold run with empty cache, then warm run):
    python3 cost/calculator.py pilot --paid

Every cost is recomputed as billed_units x price_per_unit from cost/usage.csv and cost/rates.csv;
the cost_usd values logged at call time are never reused, so editing rates changes every total.
"""

import argparse
import csv
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ITEMS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens")
STAGE_ORDER = ("enrich", "verify", "group", "memo")


# ---------------------------------------------------------------- loading
def load_rates(mult=1.0):
    rates, meta = {}, {}
    with open(HERE / "rates.csv", newline="") as f:
        for r in csv.DictReader(f):
            rates[(r["model"], r["billing_item"])] = float(r["usd_per_million_units"]) / 1e6 * mult
            meta[(r["model"], r["billing_item"])] = r
    return rates, meta


def rate_model(model):
    return "jev" if model.startswith("jev") else model


def read_jsonl(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def cost_of(call, rates):
    m = rate_model(call["model"])
    total, missing = 0.0, []
    for item in ITEMS:
        units = int(call.get(item) or 0)
        if units:
            if (m, item) in rates:
                total += units * rates[(m, item)]
            else:
                missing.append(f"{m}/{item}")
    return total, missing


# ---------------------------------------------------------------- collect (no API calls)
def collect(pilot_run, refresh_runs):
    sys.path.insert(0, str(ROOT))
    import sqlite3
    db = ROOT / "state" / f"{pilot_run}.db"
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    log = [json.loads(l) for l in open(ROOT / "artifacts" / pilot_run / "run_log.jsonl") if l.strip()]
    alls = [r for r in log if r["stage"] == "all"]
    cold, warm = alls[0], alls[-1]
    cold_t0, warm_t0 = cold["started_at"], warm["started_at"]
    calls = []
    for c in con.execute("SELECT * FROM calls ORDER BY started_at"):
        c = dict(c)
        c["review_ids"] = json.loads(c["review_ids"])
        c["pilot_run"] = "cold" if c["started_at"] < warm_t0 else "warm"
        calls.append(c)
    with open(HERE / "pilot_calls.jsonl", "w") as f:
        for c in calls:
            f.write(json.dumps({k: c[k] for k in ("request_id", "pilot_run", "role", "model", "phase", "outcome", "attempt",
                                                  "label_config", "review_ids", "input_tokens", "output_tokens",
                                                  "cache_read_input_tokens", "cache_creation_input_tokens",
                                                  "started_at", "duration_s", "error", "fault_injected", "invocation")}) + "\n")
    # one row per mutually exclusive billing item, each mapped to its rate row and call request_id
    with open(HERE / "usage.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["request_id", "pilot_run", "role", "provider", "rate_model", "billing_item", "billed_units", "unit", "source"])
        for c in calls:
            for item in ITEMS:
                units = int(c.get(item) or 0)
                if units:
                    w.writerow([c["request_id"], c["pilot_run"], c["role"],
                                "typesafe" if c["model"].startswith("jev") else "anthropic", rate_model(c["model"]),
                                item, units, "token", "provider response usage"])
    with open(ROOT / "artifacts" / pilot_run / "grading" / "records.jsonl") as src, open(HERE / "pilot_records.jsonl", "w") as dst:
        dst.write(src.read())
    ing = json.loads((ROOT / "artifacts" / pilot_run / "ingest" / "ingestion_report.json").read_text())
    measurements = {"pilot_run": pilot_run, "input_file": ing["input_file"], "input_sha256": ing["input_sha256"],
                    "rows": ing["rows"], "distinct_texts": ing["scope"]["distinct_texts_in_scope"],
                    "cold": {k: cold[k] for k in ("started_at", "wall_clock_s", "stage_seconds", "spent_this_command_usd")},
                    "warm": {k: warm[k] for k in ("started_at", "wall_clock_s", "stage_seconds", "spent_this_command_usd")},
                    "settings": {"workers": 1, "enrich_batch_size": 50, "reviews_per_enrich_request": 1,
                                 "verify_sample": 20, "verify_reviews_per_request": 25,
                                 "models": {"enrich": "jev-latest (served jev-1.13.0), no thinking control (fixed-choice model)",
                                            "verify": "claude-haiku-5-5, thinking disabled, effort low, structured output",
                                            "group": "claude-haiku-5-5 taxonomy (thinking disabled) + jev-latest subtopic choice",
                                            "memo": "claude-sonnet-5-5, adaptive thinking, effort low, structured output"},
                                 "prompt_versions": {"enrich": "jev-q1+schema-v1+quote-v1", "verify": "verify-v1",
                                                     "group": "group-v1", "memo": "memo-v1"}},
                    "machine": "Apple M2 Pro, 16 GB RAM, macOS (local orchestration; no local inference)"}
    for run in [r for r in (refresh_runs or "").split(",") if r]:
        rcon = sqlite3.connect(ROOT / "state" / f"{run}.db")
        rows = rcon.execute("SELECT role, outcome, COUNT(*), SUM(input_tokens), SUM(output_tokens), SUM(attempt>1) FROM calls GROUP BY 1,2").fetchall()
        inv = rcon.execute("SELECT summary FROM invocations WHERE stage='enrich' AND status='finished' ORDER BY inv_id").fetchall()
        res = rcon.execute("SELECT status, COUNT(*) FROM results GROUP BY 1").fetchall()
        rrep = json.loads((ROOT / "artifacts" / run / "ingest" / "ingestion_report.json").read_text())
        measurements.setdefault("refresh", {})[run] = {
            "rows": rrep["rows"], "distinct_texts": rrep["scope"]["distinct_texts_in_scope"],
            "calls": [dict(zip(("role", "outcome", "n", "input_tokens", "output_tokens", "retried"), r)) for r in rows],
            "results": dict(res), "enrich_invocations": [json.loads(s[0]) for s in inv if s[0]]}
    (HERE / "pilot_measurements.json").write_text(json.dumps(measurements, indent=2) + "\n")
    print(f"collected {len(calls)} calls, usage.csv, pilot_records.jsonl, pilot_measurements.json (no API calls)")


# ---------------------------------------------------------------- compute (offline)
def compute(args):
    rates, meta = load_rates(args.rates_multiplier)
    calls = read_jsonl(HERE / "pilot_calls.jsonl")
    records = read_jsonl(HERE / "pilot_records.jsonl")
    m = json.loads((HERE / "pilot_measurements.json").read_text())
    a = json.loads((HERE / "assumptions.json").read_text())
    if args.scope:
        a["projection"]["classified_rows"] = args.scope
    if args.budget:
        a["controls"]["budget_usd"] = args.budget

    # measured pilot, by run and stage — cost recomputed from usage x rates
    stage = defaultdict(lambda: defaultdict(float))
    unresolved = set()
    for c in calls:
        s = stage[(c["pilot_run"], c["role"], rate_model(c["model"]))]
        cost, missing = cost_of(c, rates)
        unresolved.update(missing)
        s["requests"] += 1
        s["failed"] += c["outcome"] == "failed"
        s["retries"] += (c.get("attempt") or 1) > 1
        s["reviews_sent"] += len(c["review_ids"])
        for item in ITEMS:
            s[item] += int(c.get(item) or 0)
        s["cost"] += cost
        s["sum_call_seconds"] += c.get("duration_s") or 0
    completed = sum(r["status"] == "completed" for r in records)
    cold_cost = sum(v["cost"] for (run, _, _), v in stage.items() if run == "cold")
    warm_cost = sum(v["cost"] for (run, _, _), v in stage.items() if run == "warm")
    warm_enrich_calls = sum(v["requests"] for (run, role, _), v in stage.items() if run == "warm" and role == "enrich")
    cache_hits = sum(1 for r in records if r.get("cache_source_id"))

    # per-unit measurements; refreshed with larger dev runs when available (more stable averages)
    e = [c for c in calls if c["role"] == "enrich" and c["outcome"] == "succeeded" and c["pilot_run"] == "cold"]
    jev_in = sum(c["input_tokens"] for c in e) / len(e)
    jev_out = sum(c["output_tokens"] for c in e) / len(e)
    enrich_rps_1w = len(e) / m["cold"]["stage_seconds"]["enrich"]
    unit_source = "100-review pilot"
    best = None
    for run, r in (m.get("refresh") or {}).items():
        ec = [x for x in r["calls"] if x["role"] == "enrich" and x["outcome"] == "succeeded"]
        if ec and ec[0]["n"] and (best is None or ec[0]["n"] > best[1]["n"]):
            best = (run, ec[0], r)
    measured_tput = {"1_worker_pilot": round(enrich_rps_1w, 2)}
    if best:
        run, ec, r = best
        jev_in, jev_out = ec["input_tokens"] / ec["n"], ec["output_tokens"] / ec["n"]
        unit_source = f"refreshed from dev run '{run}' ({ec['n']} enrich calls)"
        for inv in r["enrich_invocations"]:
            if inv.get("wall_s") and inv.get("completed"):
                measured_tput[f"{inv['workers']}_workers_{run}"] = round(inv["completed"] / inv["wall_s"], 2)
    verify_cost_per_review = sum(v["cost"] for (run, role, _), v in stage.items() if run == "cold" and role == "verify") / m["settings"]["verify_sample"]
    group_jev = stage[("cold", "group", "jev")]
    group_assign_cost = group_jev["cost"] / max(group_jev["requests"], 1)
    taxonomy_cost = stage[("cold", "group", "claude-haiku-5-5")]["cost"]
    memo_cost = stage[("cold", "memo", "claude-sonnet-5-5")]["cost"]
    complaint_share = sum(r.get("intent") in ("complaint", "cancellation") for r in records) / max(completed, 1)

    P, C = a["projection"], a["controls"]
    jev_rate = rates[("jev", "input_tokens")]
    jev_out_rate = rates.get(("jev", "output_tokens"), 0.0)
    jev_call = jev_in * jev_rate + jev_out * jev_out_rate
    haiku_fallback_call = (P["fallback_input_tokens"] * rates[("claude-haiku-5-5", "input_tokens")] +
                           P["fallback_output_tokens"] * rates[("claude-haiku-5-5", "output_tokens")])
    tput = C["max_workers"] * enrich_rps_1w if C["max_workers"] > 1 else enrich_rps_1w
    tput = min(tput, C["rps_cap"])
    tput_basis = f"MODELED: {C['max_workers']} x measured 1-worker rate, capped at rps_cap {C['rps_cap']}"
    for k, v in measured_tput.items():
        if k.startswith(f"{C['max_workers']}_workers"):
            tput, tput_basis = v, f"measured ({k})"  # prefer a measured throughput at the chosen concurrency

    def scenario(name, retry, invalid, fallback, distinct):
        work = distinct
        calls_ = work * (1 + retry + invalid)
        enrich = calls_ * jev_call
        fb = work * min(fallback, C["max_fallback_fraction"]) * haiku_fallback_call
        verify = P["verify_sample"] * verify_cost_per_review * (1 + retry)
        group = taxonomy_cost + work * complaint_share * group_assign_cost * (1 + retry)
        memo = memo_cost * (1 + invalid * 10)  # a failed memo validation repeats the whole call
        total = enrich + fb + verify + group + memo
        hours = (calls_ / tput + work * complaint_share / tput) / 3600 + P["fixed_overhead_s"] / 3600
        return {"scenario": name, "distinct_texts_sent": work, "enrich_calls": round(calls_), "enrich_usd": enrich,
                "fallback_usd": fb, "verify_usd": verify, "group_usd": group, "memo_usd": memo, "api_total_usd": total,
                "est_hours": hours, "over_budget": total > C["budget_usd"]}

    rows = P["classified_rows"]
    distinct = P["distinct_texts_by_scope"].get(str(rows), round(rows * P["distinct_ratio_default"]))
    scen = [scenario("base (exact-text reuse)", P["base_retry_rate"], P["base_invalid_rate"], P["base_fallback_fraction"], distinct),
            scenario("conservative (reuse)", P["cons_retry_rate"], P["cons_invalid_rate"], P["cons_fallback_fraction"], distinct),
            scenario("base, no reuse", P["base_retry_rate"], P["base_invalid_rate"], P["base_fallback_fraction"], rows)]
    if rows != 660609:
        scen.append(scenario("reference: full corpus 660,609, reuse (484,189 texts)", P["base_retry_rate"], P["base_invalid_rate"],
                             P["base_fallback_fraction"], 484189))

    # ------------------------------------------------------------ report
    L = []
    L.append("# 100-review cost & runtime calculator — report\n")
    L.append(f"_Generated offline by `python3 cost/calculator.py` from saved evidence (no API calls). "
             f"Rates multiplier: **{args.rates_multiplier}**. Currency: USD._\n")
    L.append("## 1. Measured pilot (real calls)\n")
    L.append(f"- Input: `{m['input_file']}` sha256 `{m['input_sha256']}` · {m['rows']} rows · {m['distinct_texts']} distinct texts")
    L.append(f"- Records: **{completed} completed**, {len(records) - completed} quarantined/failed · result-cache hits {cache_hits}")
    L.append(f"- Cold run (empty result cache, 1 worker): **{m['cold']['wall_clock_s']:.1f} s wall-clock**, "
             f"API **${cold_cost:.5f}** · Warm run (saved cache): **{m['warm']['wall_clock_s']:.2f} s**, API ${warm_cost:.5f}, "
             f"**{warm_enrich_calls} new enrichment calls**, 0 downstream calls (verify/group/memo reused by input fingerprint)")
    L.append(f"- Cost per 1,000 input rows (cold): **${cold_cost / m['rows'] * 1000:.4f}** · per completed record: ${cold_cost / max(completed, 1):.6f}")
    L.append(f"- Throughput (cold, enrichment, 1 worker): {enrich_rps_1w:.2f} reviews/s · stage seconds: "
             + ", ".join(f"{k} {v:.2f}" for k, v in m["cold"]["stage_seconds"].items()))
    L.append("- Summed call durations are not wall-clock; the wall-clock above is measured end-to-end by the orchestrator.\n")
    L.append("| run | stage | provider · model | settings | requests | failed | retries | input tok | cache-read | output tok | API $ |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for (run, role, model), v in sorted(stage.items(), key=lambda x: (x[0][0], STAGE_ORDER.index(x[0][1]))):
        L.append(f"| {run} | {role} | {'typesafe' if model == 'jev' else 'anthropic'} · {model} | {m['settings']['models'][role]} | "
                 f"{int(v['requests'])} | {int(v['failed'])} | {int(v['retries'])} | {int(v['input_tokens'])} | "
                 f"{int(v['cache_read_input_tokens'])} | {int(v['output_tokens'])} | {v['cost']:.6f} |")
    if not any(run == "warm" for run, _, _ in stage):
        L.append("| warm | (all) | — | saved result cache | 0 | 0 | 0 | 0 | 0 | 0 | 0.000000 |")
    L.append(f"\nPrompt/schema versions: {json.dumps(m['settings']['prompt_versions'])} · enrichment batch size "
             f"{m['settings']['enrich_batch_size']} reviews (1 review per Jev request) · workers {m['settings']['workers']}.")
    L.append(f"\nUnresolved billing items (no rate): {sorted(unresolved) or 'none'}. Local compute (M2 Pro laptop, electricity) "
             "is **unknown, not $0**; no local inference is used. Hosting (Supabase/Vercel free tiers) is outside API spend.\n")
    L.append("## 2. Rates used (editable: `cost/rates.csv`)\n")
    L.append("| model | billing item | $ / 1M units (after multiplier) | status | source | checked |")
    L.append("|---|---|---|---|---|---|")
    for (mod, item), r in meta.items():
        L.append(f"| {mod} | {item} | {rates[(mod, item)] * 1e6:.4f} | {r['status']} | [link]({r['source_url']}) | {r['checked_date']} |")
    L.append("\nFormula: `item_cost = billed_units × price_per_unit` (price per 1M ÷ 1,000,000); `total = Σ item_cost`. "
             "Input, cache-read, cache-write and output tokens are mutually exclusive in the usage logs. Standard tier only (no Batch API used).\n")
    L.append(f"## 3. Full-run projection — {rows:,} classified rows\n")
    L.append(f"Per-unit inputs ({unit_source}): Jev {jev_in:.0f} input + {jev_out:.0f} output tokens per call; "
             f"verify ${verify_cost_per_review:.6f}/review; subtopic assignment ${group_assign_cost:.6f}/complaint text; "
             f"taxonomy ${taxonomy_cost:.4f} once; memo ${memo_cost:.4f} once; complaint share {complaint_share:.2f}. "
             f"Throughput used: {tput:.1f} reviews/s at {C['max_workers']} workers [{tput_basis}] (measured so far: {measured_tput}).\n")
    L.append("| scenario | texts sent | enrich calls | enrich $ | fallback $ | verify $ | group $ | memo $ | **API total $** | est. hours | budget |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for s in scen:
        L.append(f"| {s['scenario']} | {s['distinct_texts_sent']:,} | {s['enrich_calls']:,} | {s['enrich_usd']:.2f} | {s['fallback_usd']:.2f} | "
                 f"{s['verify_usd']:.3f} | {s['group_usd']:.2f} | {s['memo_usd']:.3f} | **{s['api_total_usd']:.2f}** | {s['est_hours']:.2f} | "
                 f"{'**EXCEEDS BUDGET**' if s['over_budget'] else 'ok'} |")
    L.append("\nFallback $ is declared headroom for a capped stronger-model re-label (max_fallback_fraction); the current pipeline "
             "quarantines instead of escalating, so measured fallback spend is $0.")
    L.append(f"\nAll 660,622 source rows are accounted for: {rows:,} classified, 13 empty-text quarantines, the rest quarantined as "
             "`outside_declared_classification_scope`. Fixed overhead (taxonomy, memo, ingest) is added once, not per review.\n")
    L.append("## 4. Controls (editable: `cost/assumptions.json`)\n")
    for k, v in C.items():
        L.append(f"- `{k}` = {v}")
    L.append(f"\n- Scaling decision: {a['decision']}\n")
    L.append("## 5. How to recheck\n\n```sh\npython3 cost/calculator.py                        # offline replay (default)\n"
             "python3 cost/calculator.py --rates-multiplier 2   # API subtotal doubles; times unchanged\n"
             "python3 cost/calculator.py --scope 660609         # projection changes; measured pilot unchanged\n```\n")
    out = HERE / ("report.md" if args.rates_multiplier == 1 and not args.scope else "report_whatif.md")
    out.write_text("\n".join(L) + "\n")
    summary = {"cold_api_usd": round(cold_cost, 8), "warm_api_usd": round(warm_cost, 8), "warm_enrich_calls": warm_enrich_calls,
               "cold_wall_s": m["cold"]["wall_clock_s"], "warm_wall_s": m["warm"]["wall_clock_s"],
               "scenarios": [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in s.items()} for s in scen]}
    (HERE / ("projection.json" if out.name == "report.md" else "projection_whatif.json")).write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=1))
    print(f"-> {out.relative_to(ROOT)}")


def pilot(paid):
    if not paid:
        sys.exit("The pilot makes paid API calls. Re-run as: python3 cost/calculator.py pilot --paid")
    py = str(ROOT / ".venv" / "bin" / "python")
    base = [py, "-m", "pipeline.run", "all", "--input", "data/cost_100.csv", "--run", "pilot", "--scope", "0",
            "--workers", "1", "--verify-n", "20", "--paid"]
    subprocess.run(base + ["--fresh"], cwd=ROOT, check=True)   # cold: empty result cache
    subprocess.run(base, cwd=ROOT, check=True)                 # warm: saved result cache
    collect("pilot", "")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", nargs="?", default="replay", choices=["replay", "collect", "pilot"])
    p.add_argument("--rates-multiplier", type=float, default=1.0)
    p.add_argument("--scope", type=int, default=None, help="projected classified rows (default from assumptions.json)")
    p.add_argument("--budget", type=float, default=None)
    p.add_argument("--pilot-run", default="pilot")
    p.add_argument("--refresh-runs", default="")
    p.add_argument("--paid", action="store_true")
    a = p.parse_args()
    if a.command == "collect":
        collect(a.pilot_run, a.refresh_runs)
    elif a.command == "pilot":
        pilot(a.paid)
    else:
        compute(a)


if __name__ == "__main__":
    main()

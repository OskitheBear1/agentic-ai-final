"""Pipeline orchestrator (code). Accepts any input CSV and runs the six stages without chat pasting.

  python -m pipeline.run all --input data/cost_100.csv --run pilot_cold --scope 0 --verify-n 20 --paid
  python -m pipeline.run enrich --run full --workers 4 --max-batches 40 --paid     # stop early = interruption demo
  python -m pipeline.run snapshot --run full --name before
  python -m pipeline.run rank --run full                                           # offline, no model calls

Stages that call a model refuse to run without --paid. The spend ledger (state/ledger.db) is shared across
all runs and stops admitting new calls once spent + reserved would exceed --budget.
"""

import argparse
import json
import sys
import time

from .common import ARTIFACTS, write_json

PAID = {"enrich", "verify", "group", "memo", "all"}


def stage_rank(run):
    from .export import record_rows
    from .rank import rank, read_membership, write
    from .state import connect
    con = connect(run)
    records = {r["review_id"]: r for r in record_rows(con) if r["status"] == "completed"}
    con.close()
    rows, aggs = rank(records, read_membership(ARTIFACTS / run / "group" / "membership.csv"))
    write(rows, aggs, ARTIFACTS / run / "rank")
    print(f"[rank] {len(rows)} issues ranked (code only)")
    return {"issues": len(rows), "top": rows[:3]}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stage", choices=["ingest", "enrich", "verify", "group", "rank", "memo", "export", "snapshot", "all"])
    p.add_argument("--input", help="input CSV (ingest/all/export)")
    p.add_argument("--run", required=True, help="run name; state in state/<run>.db, outputs in artifacts/<run>/")
    p.add_argument("--scope", type=int, default=0, help="classification scope size; 0 = every eligible row")
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--rps", type=float, default=20.0, help="global request-per-second cap for Jev")
    p.add_argument("--budget", type=float, default=12.0, help="global USD cap across all runs (ledger)")
    p.add_argument("--max-batches", type=int, default=None, help="stop enrichment after N batches (interruption demo)")
    p.add_argument("--time-limit", type=float, default=None, help="stop enrichment after N seconds")
    p.add_argument("--inject-faults", default=None, help="declared test only, e.g. api_error=0.05,malformed=0.03")
    p.add_argument("--retry-quarantined", action="store_true", help="re-attempt reviews quarantined for API errors")
    p.add_argument("--verify-n", type=int, default=1000)
    p.add_argument("--taxonomy", default=None, help="frozen taxonomy JSON (skip proposal call)")
    p.add_argument("--name", default=None, help="snapshot name: before | after")
    p.add_argument("--gzip", action="store_true", help="gzip records.jsonl in the export")
    p.add_argument("--fresh", action="store_true", help="ingest: delete saved state first (cold run, empty result cache)")
    p.add_argument("--paid", action="store_true", help="required for any stage that makes paid model calls")
    a = p.parse_args()

    if a.stage in PAID and not a.paid:
        sys.exit(f"'{a.stage}' makes paid model calls. Re-run with --paid to confirm (budget cap ${a.budget:.2f}).")

    from .ledger import Ledger
    ledger = Ledger(a.budget)
    timings, summary = {}, {"run": a.run, "stage": a.stage, "started_at": time.time(), "budget_usd": a.budget,
                            "spent_before_usd": round(ledger.spent(), 6)}
    t_all = time.monotonic()

    def timed(name, fn):
        t = time.monotonic()
        out = fn()
        timings[name] = round(time.monotonic() - t, 3)
        summary[name] = out
        return out

    stages = ["ingest", "enrich", "verify", "group", "rank", "memo", "export"] if a.stage == "all" else [a.stage]
    for s in stages:
        if s == "ingest":
            from .ingest import ingest
            timed("ingest", lambda: ingest(a.input, a.scope or 10**9, a.run, ARTIFACTS / a.run / "ingest", fresh=a.fresh)["status_counts"])
        elif s == "enrich":
            from .enrich import run_enrich
            status, _ = timed("enrich", lambda: run_enrich(a.run, ledger, a.workers, a.max_batches, a.time_limit,
                                                           a.inject_faults, a.rps, a.retry_quarantined))
            if a.stage == "all" and status != "finished":
                print(f"[run] enrichment stopped ({status}); downstream stages not run. Resume with the same command.")
                break
        elif s == "verify":
            from .verify import run_verify
            timed("verify", lambda: run_verify(a.run, ledger, a.verify_n))
        elif s == "group":
            from .group import run_group
            timed("group", lambda: run_group(a.run, ledger, a.taxonomy, workers=a.workers))
        elif s == "rank":
            timed("rank", lambda: stage_rank(a.run))
        elif s == "memo":
            from .memo import run_memo
            timed("memo", lambda: run_memo(a.run, ledger))
        elif s == "export":
            from .export import export
            inp = a.input or json.loads((ARTIFACTS / a.run / "ingest" / "ingestion_report.json").read_text())["input_file"]
            from pathlib import Path
            path = Path(inp) if Path(inp).exists() else Path("data") / inp
            timed("export", lambda: str(export(a.run, path, gzip_records=a.gzip)))
        elif s == "snapshot":
            from .export import snapshot
            timed("snapshot", lambda: str(snapshot(a.run, a.name)))

    summary.update(stage_seconds=timings, wall_clock_s=round(time.monotonic() - t_all, 3),
                   spent_after_usd=round(ledger.spent(), 6), ended_at=time.time())
    summary["spent_this_command_usd"] = round(summary["spent_after_usd"] - summary["spent_before_usd"], 6)
    log = ARTIFACTS / a.run / "run_log.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as f:
        f.write(json.dumps(summary, default=str) + "\n")
    write_json(ARTIFACTS / a.run / f"run_summary_{a.stage}.json", summary)
    print(f"[run] {a.stage} done in {summary['wall_clock_s']}s; spent this command ${summary['spent_this_command_usd']:.5f}; "
          f"ledger total ${summary['spent_after_usd']:.5f}")


if __name__ == "__main__":
    main()

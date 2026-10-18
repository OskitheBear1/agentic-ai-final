"""Export the standardized grading/ folder for a run (code only). See tools/GRADING_CONTRACT.md."""

import csv
import gzip
import json
import shutil
from pathlib import Path

from .common import ARTIFACTS, sha, write_json
from .state import connect

RECORD_FIELDS = ("topic", "intent", "sentiment", "severity", "entities", "evidence_quote", "needs_review", "label_config")


def record_rows(con):
    q = ("SELECT r.review_id, r.source_sha256, r.pre_status, r.pre_reason, x.* FROM reviews r "
         "LEFT JOIN results x USING(review_id) ORDER BY r.row_idx")
    for row in con.execute(q):
        row = dict(row)
        base = {"review_id": row["review_id"], "source_sha256": row["source_sha256"]}
        if row["pre_status"] == "quarantined":
            yield base | {"status": "quarantined", "reason": row["pre_reason"]}
        elif row["status"] is None:
            yield base | {"status": "quarantined", "reason": "pending_not_processed_in_this_run"}
        elif row["status"] == "quarantined":
            yield base | {"status": "quarantined", "reason": row["reason"], "attempts": row["attempts"]}
        else:
            rec = base | {"status": "completed", "topic": row["topic"], "intent": row["intent"],
                          "sentiment": row["sentiment"], "severity": row["severity"],
                          "entities": json.loads(row["entities"]), "evidence_quote": row["evidence_quote"],
                          "needs_review": bool(row["needs_review"]), "label_config": row["label_config"]}
            if row["cache_source_id"]:
                rec["cache_source_id"] = row["cache_source_id"]
            yield rec


def call_rows(con):
    for c in con.execute("SELECT * FROM calls ORDER BY started_at"):
        c = dict(c)
        out = {"request_id": c["request_id"], "role": c["role"], "review_ids": json.loads(c["review_ids"]),
               "model": c["model"], "phase": c["phase"], "outcome": c["outcome"],
               "label_config": c["label_config"] or f"{c['model']}+{c['role']}",
               "input_tokens": int(c["input_tokens"] or 0), "output_tokens": int(c["output_tokens"] or 0),
               "cache_read_input_tokens": int(c["cache_read_input_tokens"] or 0),
               "cache_creation_input_tokens": int(c["cache_creation_input_tokens"] or 0),
               "cost_usd": round(c["cost_usd"] or 0.0, 8), "duration_s": c["duration_s"], "attempt": c["attempt"],
               "started_at": c["started_at"], "run": c["run"], "invocation": c["invocation"]}
        if c["error"]:
            out["error"] = c["error"]
        if c["fault_injected"]:
            out["fault_injected"] = True
        if c["artifacts"]:
            out["input_artifacts"] = json.loads(c["artifacts"])
        yield out


def export(run, input_csv, out_dir=None, gzip_records=False):
    con = connect(run)
    a = ARTIFACTS / run
    out = Path(out_dir or a / "grading")
    out.mkdir(parents=True, exist_ok=True)
    n = con.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
    write_json(out / "run.json", {"version": "a5-audit-v1", "analysis_count": n, "analysis_sha256": sha(input_csv),
                                  "classification_input_fields": ["review_text"], "allow_multi_issue": False,
                                  "run_name": run, "input_file": Path(input_csv).name,
                                  "declared_classification_scope": con.execute(
                                      "SELECT COUNT(*) FROM reviews WHERE pre_status='pending'").fetchone()[0]})
    shutil.copy(a / "ingest" / "ingestion.json", out / "ingestion.json")
    rec_path = out / ("records.jsonl.gz" if gzip_records else "records.jsonl")
    opener = (lambda p: gzip.open(p, "wt", encoding="utf-8")) if gzip_records else (lambda p: open(p, "w", encoding="utf-8"))
    with opener(rec_path) as f:
        for r in record_rows(con):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(out / "calls.jsonl", "w", encoding="utf-8") as f:
        for c in call_rows(con):
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    for src, name in ((a / "group" / "membership.csv", "membership.csv"), (a / "rank" / "ranking.csv", "ranking.csv"),
                      (a / "memo" / "claims.csv", "claims.csv"), (a / "checkpoints" / "checkpoint_before.json", "checkpoint_before.json"),
                      (a / "checkpoints" / "checkpoint_after.json", "checkpoint_after.json")):
        if src.exists():
            shutil.copy(src, out / name)
    con.close()
    print(f"[export] grading folder -> {out}")
    return out


def snapshot(run, name):
    """Save completed_ids (checkpoint_before.json / checkpoint_after.json) for the interruption/resume evidence."""
    con = connect(run)
    ids = [r[0] for r in con.execute("SELECT review_id FROM results WHERE status='completed' ORDER BY review_id")]
    con.close()
    path = ARTIFACTS / run / "checkpoints" / f"checkpoint_{name}.json"
    write_json(path, {"completed_ids": ids, "count": len(ids)})
    print(f"[snapshot] {len(ids)} completed IDs -> {path}")
    return path

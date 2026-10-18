"""Stage 1 — Ingest (code only, no model calls).

Reads every row of the input CSV, profiles it, hashes each source row, finds exact
duplicate texts, selects the declared classification scope, and writes the pending
work queue into the SQLite state database.

Usage: python -m pipeline.ingest --input data/spotify_reviews_18months.csv --scope 100000
"""

import argparse
import sqlite3
from collections import Counter
from pathlib import Path

from .common import ARTIFACTS, STATE_DIR, VALID_RATINGS, csv_rows, profile, row_sha, sample_rank, sha, text_sha, write_json

SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
  review_id TEXT PRIMARY KEY,
  row_idx INTEGER NOT NULL,
  source_sha256 TEXT NOT NULL,
  text_sha256 TEXT NOT NULL,
  review_text TEXT NOT NULL,
  review_rating TEXT, review_likes TEXT, app_version TEXT, review_timestamp TEXT,
  scope_rank INTEGER,              -- 1..N if inside the declared classification scope, else NULL
  pre_status TEXT NOT NULL,        -- pending | quarantined (decided by code before any model call)
  pre_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_reviews_text ON reviews(text_sha256);
CREATE INDEX IF NOT EXISTS idx_reviews_scope ON reviews(scope_rank);
"""


def db_path(run_name):
    return STATE_DIR / f"{run_name}.db"


def ingest(input_csv, scope, run_name, out_dir, fresh=False):
    input_csv = Path(input_csv)
    rows, ids = [], Counter()
    for idx, row in enumerate(csv_rows(input_csv)):
        ids[row["review_id"]] += 1
        rows.append((idx, row))

    # Eligible for classification: unique ID, nonempty text, valid star rating — same rule the
    # course used to draw its samples, so the golden 50 and dev checkpoints fall inside the scope.
    eligible = [(sample_rank(r["review_id"]), r["review_id"]) for _, r in rows
                if ids[r["review_id"]] == 1 and r["review_text"].strip() and r["review_rating"] in VALID_RATINGS]
    eligible.sort()
    in_scope = {rid: i + 1 for i, (_, rid) in enumerate(eligible[:scope])}

    STATE_DIR.mkdir(exist_ok=True)
    path = db_path(run_name)
    if fresh and path.exists():
        path.unlink()  # cold run: empty result cache
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.execute("DELETE FROM reviews")  # re-ingest keeps saved results/calls (warm run, resume)
    reasons = Counter()
    text_counts = Counter()
    for idx, r in rows:
        rid = r["review_id"]
        if not r["review_text"].strip():
            status, reason = "quarantined", "empty_review_text"
        elif ids[rid] > 1:
            status, reason = "quarantined", "duplicate_review_id"
        elif rid in in_scope:
            status, reason = "pending", None
            text_counts[r["review_text"]] += 1
        else:
            status, reason = "quarantined", "outside_declared_classification_scope"
        reasons[reason or "pending"] += 1
        con.execute("INSERT OR IGNORE INTO reviews VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (rid, idx, row_sha(r), text_sha(r["review_text"]), r["review_text"], r["review_rating"],
                     r["review_likes"], r["app_version"], r["review_timestamp"], in_scope.get(rid), status, reason))
    con.commit()
    con.close()

    all_nonempty_texts = {r["review_text"] for _, r in rows if r["review_text"].strip()}
    report = {
        "input_file": input_csv.name,
        "input_sha256": sha(input_csv),
        "input_bytes": input_csv.stat().st_size,
        "rows": len(rows),
        "unique_review_ids": len(ids),
        "duplicate_review_ids": sum(c - 1 for c in ids.values() if c > 1),
        "empty_review_text": sum(1 for _, r in rows if not r["review_text"].strip()),
        "missing_app_version": sum(1 for _, r in rows if not r["app_version"].strip()),
        "nonempty_rows": sum(1 for _, r in rows if r["review_text"].strip()),
        "distinct_nonempty_texts_full_file": len(all_nonempty_texts),
        "scope": {
            "declared_scope": scope,
            "selected": len(in_scope),
            "method": "Lowest SHA-256('berkeley-fall-2026-assignment-5-v1:' + review_id) among unique, nonempty, "
                      "valid-rating rows (the course's own sampling order), so the golden 50 and all dev checkpoints are included.",
            "distinct_texts_in_scope": len(text_counts),
            "exact_duplicate_rows_in_scope": len(in_scope) - len(text_counts),
        },
        "status_counts": dict(reasons),
        "accounting_check": sum(reasons.values()) == len(rows),
        "model_calls": 0,
    }
    out_dir = Path(out_dir)
    write_json(out_dir / "ingestion_report.json", report)
    (out_dir / "scope_ids.txt").write_text("\n".join(rid for _, rid in eligible[:scope]) + "\n")
    # The grader's deterministic full-file profile, produced by the provided helper.
    write_json(out_dir / "ingestion.json", profile(input_csv))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--scope", type=int, default=100_000)
    p.add_argument("--run", default=None, help="state DB name (default: input file stem)")
    a = p.parse_args()
    run = a.run or Path(a.input).stem
    report = ingest(a.input, a.scope, run, ARTIFACTS / run / "ingest")
    print({k: report[k] for k in ("rows", "empty_review_text", "missing_app_version", "duplicate_review_ids")}, report["scope"]["selected"], report["status_counts"])


if __name__ == "__main__":
    main()

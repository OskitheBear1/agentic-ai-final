"""Complaint-share trend for the top issues in comparable periods, with denominators (no model calls).

    python3 evals/trend_shares.py --csv data/spotify_reviews_18months.csv

Reads review timestamps from the source CSV and issue membership from grading/. Periods are full calendar
quarters-ish blocks of whole months; the partial first (2022-05) and last (2023-11) months are excluded.
Writes evals/results/trend_shares.md.
"""
import argparse
import csv
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from pipeline.common import COMPARABLE_PERIODS as PERIODS  # noqa: E402

ISSUES = ["billing.basic_features_behind_premium", "usability.ad_frequency_loudness", "playback.playback_interruptions"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "data" / "spotify_reviews_18months.csv"))
    args = ap.parse_args()
    csv.field_size_limit(sys.maxsize)
    classified = set()
    with gzip.open(ROOT / "grading" / "records.jsonl.gz", "rt") as f:
        for line in f:
            r = json.loads(line)
            if r["status"] == "completed":
                classified.add(r["review_id"])
    membership = {r["review_id"]: r["issue_id"] for r in csv.DictReader(open(ROOT / "grading" / "membership.csv"))}
    month = {}
    with open(args.csv, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["review_id"] in classified:
                month[r["review_id"]] = r["review_timestamp"][:7]
    reviews, complaints, by_issue = Counter(month.values()), Counter(), {i: Counter() for i in ISSUES}
    for rid, iid in membership.items():
        complaints[month[rid]] += 1
        if iid in by_issue:
            by_issue[iid][month[rid]] += 1
    lines = ["# Complaint share by period (classified 100,000-review scope)", "",
             "Share = issue complaints ÷ all complaint/cancellation reviews in the period. Partial months 2022-05 "
             f"({reviews['2022-05']:,} classified reviews) and 2023-11 ({reviews['2023-11']:,}) are excluded.", "",
             "| period | classified reviews | complaints (denominator) | " + " | ".join(ISSUES) + " |",
             "|---|---|---|" + "---|" * len(ISSUES)]
    for name, months in PERIODS:
        t = sum(reviews[m] for m in months)
        c = sum(complaints[m] for m in months)
        cells = [f"{sum(by_issue[i][m] for m in months):,} ({100 * sum(by_issue[i][m] for m in months) / c:.1f}%)"
                 for i in ISSUES]
        lines.append(f"| {name} | {t:,} | {c:,} | " + " | ".join(cells) + " |")
    out = ROOT / "evals" / "results" / "trend_shares.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

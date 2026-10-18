"""Stage 5 — Rank (code only, no model calls). Reproducible from saved records + membership.

priority_score(issue) = severity_sum(issue) = complaint_count × mean_severity (integer arithmetic).
Sort: descending score, then ascending issue_id. Means: 6 decimals, decimal half-up.

Offline replay: python -m pipeline.rank --records grading/records.jsonl.gz --membership grading/membership.csv --out /tmp/x
"""

import argparse
import csv
import gzip
import json
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path


def mean_string(total, n):
    return str((Decimal(total) / Decimal(n)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def read_records(path):
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as f:
        return {r["review_id"]: r for r in map(json.loads, f) if r.get("status") == "completed"}


def read_membership(path):
    with open(path, newline="") as f:
        return [(r["issue_id"], r["review_id"]) for r in csv.DictReader(f)]


def rank(records, membership):
    sev = defaultdict(list)
    for iid, rid in membership:
        r = records[rid]
        if r["intent"] in ("complaint", "cancellation"):
            sev[iid].append(r)
    rows = [{"issue_id": i, "complaint_count": len(rs), "severity_sum": sum(r["severity"] for r in rs),
             "mean_severity": mean_string(sum(r["severity"] for r in rs), len(rs)),
             "priority_score": sum(r["severity"] for r in rs)} for i, rs in sev.items()]
    rows.sort(key=lambda x: (-x["priority_score"], x["issue_id"]))
    for n, r in enumerate(rows, 1):
        r["rank"] = n
    total_complaints = sum(len(v) for v in sev.values())
    aggregates = []
    for r in rows:
        rs = sev[r["issue_id"]]
        aggregates.append({**r,
                           "share_of_complaints": f"{len(rs) / total_complaints:.4f}",
                           "cancellation_count": sum(x["intent"] == "cancellation" for x in rs),
                           "severity_4plus_count": sum(x["severity"] >= 4 for x in rs),
                           "needs_review_count": sum(bool(x["needs_review"]) for x in rs),
                           "mean_sentiment": f"{sum(x['sentiment'] for x in rs) / len(rs):.4f}",
                           "severity_histogram": json.dumps(dict(sorted(Counter(x['severity'] for x in rs).items())))})
    return rows, aggregates


RANK_COLS = ["rank", "issue_id", "complaint_count", "severity_sum", "mean_severity", "priority_score"]


def write(rows, aggregates, out_dir):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "ranking.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RANK_COLS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    with (out / "aggregates.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(aggregates[0]) if aggregates else RANK_COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(aggregates)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--records", required=True)
    p.add_argument("--membership", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    rows, aggs = rank(read_records(a.records), read_membership(a.membership))
    write(rows, aggs, a.out)
    print(f"ranked {len(rows)} issues -> {a.out}/ranking.csv (no model calls)")


if __name__ == "__main__":
    main()

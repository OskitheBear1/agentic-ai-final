"""Check that the deployed dashboard API serves exactly the saved pipeline results (no API key needed).

    python3 tests/check_dashboard.py https://<dashboard-url>      # or http://localhost:8765

Compares /api/ranking with artifacts/full/rank/aggregates.csv, /api/metrics with the memo evidence pack,
/api/recommendations with artifacts/full/memo/claims.csv + memo.json, and spot-checks review rows against
grading/records.jsonl.gz. Writes evals/results/dashboard_check.json.
"""
import csv
import gzip
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
A = ROOT / "artifacts" / "full"


def get(base, path):
    req = urllib.request.Request(base.rstrip("/") + path, headers={"User-Agent": "check_dashboard"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def main(base):
    checks = []

    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))

    ranking = get(base, "/api/ranking")
    saved = list(csv.DictReader(open(A / "rank" / "aggregates.csv")))
    check("ranking has every saved issue in the same order",
          [r["issue_id"] for r in ranking] == [r["issue_id"] for r in saved], f"{len(ranking)} issues")
    fields = ["rank", "complaint_count", "severity_sum", "priority_score", "cancellation_count", "severity_4plus_count",
              "needs_review_count"]
    bad = [(s["issue_id"], f) for api, s in zip(ranking, saved) for f in fields if int(api[f]) != int(s[f])]
    bad += [(s["issue_id"], f) for api, s in zip(ranking, saved) for f in ("mean_severity", "share_of_complaints",
            "mean_sentiment") if abs(float(api[f]) - float(s[f])) > 1e-6]
    check("ranking numbers equal aggregates.csv", not bad, f"{len(bad)} mismatches" if bad else "all fields")
    official = list(csv.DictReader(open(ROOT / "grading" / "ranking.csv")))
    check("ranking equals grading/ranking.csv", all(
        o["issue_id"] == a["issue_id"] and int(o["priority_score"]) == a["priority_score"] for o, a in zip(official, ranking))
        and len(official) == len(ranking))

    m = get(base, "/api/metrics")
    pack = json.loads((A / "memo" / "evidence_pack.json").read_text())
    check("topic/intent totals equal evidence pack", m["totals"] == pack["totals"])
    live = m["from_reviews_table"]
    check("reviews table holds the 100,000 classified reviews", live["classified"] == 100000, str(live["classified"]))
    check("grouped complaints in DB equal evidence pack",
          live["complaints"] == pack["totals"]["complaint_or_cancellation_reviews"], str(live["complaints"]))

    rec = get(base, "/api/recommendations")
    memo = json.loads((A / "memo" / "memo.json").read_text())
    check("memo text and recommendation equal memo.json",
          rec["markdown"] == memo["memo_markdown"] and rec["recommended_issue_id"] == memo["recommended_issue_id"])
    claims = {c["claim_id"]: c["value"] for c in csv.DictReader(open(A / "memo" / "claims.csv"))}
    extra = A / "memo" / "extra_claims.csv"
    if extra.exists():
        claims |= {c["claim_id"]: c["value"] for c in csv.DictReader(open(extra))}
    check("every memo claim (claims.csv + extra_claims.csv) served and matches the database",
          {c["claim_id"]: c["value"] for c in rec["claims"]} == claims and all(c["matches_ranking"] for c in rec["claims"]),
          f"{len(claims)} claims")
    check("every cited review is served", {r["review_id"] for r in rec["cited"]} ==
          {c["review_id"] for c in memo["cited_reviews"]}, f"{len(rec['cited'])} reviews")

    sample, n = [], 0
    with gzip.open(ROOT / "grading" / "records.jsonl.gz", "rt") as f:
        for line in f:
            r = json.loads(line)
            if r["status"] == "completed":
                n += 1
                if n % 20000 == 1:
                    sample.append(r)
    mism = []
    for r in sample:
        api = get(base, "/api/reviews/" + r["review_id"])
        for k in ("topic", "intent", "severity", "evidence_quote", "needs_review"):
            if api[k] != r[k]:
                mism.append((r["review_id"], k))
        if abs(float(api["sentiment"]) - r["sentiment"]) > 1e-9:
            mism.append((r["review_id"], "sentiment"))
    check("sampled review labels equal records.jsonl.gz", not mism, f"{len(sample)} reviews")

    out = {"base_url": base, "passed": all(c["ok"] for c in checks), "checks": checks}
    path = ROOT / "evals" / "results" / "dashboard_check.json"
    path.write_text(json.dumps(out, indent=2) + "\n")
    print(("ALL PASS" if out["passed"] else "FAILURES") + f" -> {path.relative_to(ROOT)}")
    return 0 if out["passed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8765"))

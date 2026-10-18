"""Load a finished run's saved outputs into Supabase Postgres for the dashboard (0 model calls).

    .venv/bin/python -m pipeline.export_db --run full

Reads only files on disk (grading/, artifacts/<run>/, evals/results/) plus the local state DB for review text,
then (re)creates the tables in dashboard/schema.sql and bulk-inserts. Needs SUPABASE_DB_URL in .env.
"""
import argparse
import csv
import gzip
import json
import os
import ssl
import time
from urllib.parse import unquote, urlparse

from .common import ARTIFACTS, ROOT, load_env
from .state import connect

ROWS_PER_INSERT = 1000
CA_FILE = ROOT / "dashboard" / "api" / "supabase-prod-ca-2021.crt"


def supabase_ssl():
    # Full verification (chain + hostname) against Supabase's published root CA, bundled next to the API.
    # Python 3.13+ X509_STRICT rejects that 2021 root for lacking a key-usage field, so only that flag is relaxed.
    ctx = ssl.create_default_context(cafile=str(CA_FILE))
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


def pg_connect(url):
    import pg8000.native
    u = urlparse(url)
    return pg8000.native.Connection(user=unquote(u.username), password=unquote(u.password or ""), host=u.hostname,
                                    port=u.port or 5432, database=(u.path or "/postgres").lstrip("/") or "postgres",
                                    ssl_context=supabase_ssl(), timeout=120)


def bulk_insert(db, table, cols, rows):
    for i in range(0, len(rows), ROWS_PER_INSERT):
        chunk = rows[i:i + ROWS_PER_INSERT]
        params, values = {}, []
        for j, row in enumerate(chunk):
            names = []
            for c, v in zip(cols, row):
                k = f"{c}_{j}"
                params[k] = v
                names.append(f":{k}")
            values.append("(" + ", ".join(names) + ")")
        db.run(f"INSERT INTO {table} ({', '.join(cols)}) VALUES {', '.join(values)}", **params)


def read_json(path):
    return json.loads(open(path).read())


def gather(run):
    a = ARTIFACTS / run
    grading = ROOT / "grading" if run == "full" else a / "grading"
    pack = read_json(a / "memo" / "evidence_pack.json")
    by_month = {i["issue_id"]: i.get("complaints_by_month", {}) for i in pack["top_issues"]}
    meta_issues = {i["issue_id"]: i for i in read_json(a / "group" / "issues.json")}
    membership = {r["review_id"]: r["issue_id"] for r in csv.DictReader(open(a / "group" / "membership.csv"))}

    # complaints_by_month only exists in the evidence pack for top issues; compute it for every issue from records.
    con = connect(run)
    src = {r[0]: r[1:] for r in con.execute(
        "SELECT review_id, scope_rank, review_text, review_rating, review_timestamp, app_version FROM reviews "
        "WHERE scope_rank IS NOT NULL")}
    con.close()
    reviews, month_counts, cache_reuses, status = [], {}, 0, {}
    with gzip.open(grading / "records.jsonl.gz", "rt") as f:
        for line in f:
            r = json.loads(line)
            status[r["status"]] = status.get(r["status"], 0) + 1
            if r["status"] != "completed":
                continue
            cache_reuses += bool(r.get("cache_source_id"))
            rank, text, rating, ts, ver = src[r["review_id"]]
            iid = membership.get(r["review_id"])
            if iid and ts:
                m = month_counts.setdefault(iid, {})
                m[ts[:7]] = m.get(ts[:7], 0) + 1
            reviews.append((r["review_id"], rank, text, rating, ts, ver, r["topic"], r["intent"], int(r["severity"]),
                            float(r["sentiment"]), r["evidence_quote"], json.dumps(r.get("entities", [])),
                            bool(r["needs_review"]), r.get("cache_source_id"), iid))

    issues = []
    for row in csv.DictReader(open(a / "rank" / "aggregates.csv")):
        iid = row["issue_id"]
        months = dict(sorted(month_counts.get(iid, {}).items()))
        if iid in by_month:
            assert {k: v for k, v in by_month[iid].items() if v} == {k: v for k, v in months.items() if v}, iid
        issues.append((iid, int(row["rank"]), iid.split(".")[0], meta_issues[iid]["name"],
                       meta_issues[iid]["description"], int(row["complaint_count"]), int(row["severity_sum"]),
                       float(row["mean_severity"]), int(row["priority_score"]), float(row["share_of_complaints"]),
                       int(row["cancellation_count"]), int(row["severity_4plus_count"]), int(row["needs_review_count"]),
                       float(row["mean_sentiment"]), row["severity_histogram"], json.dumps(months)))

    memo = read_json(a / "memo" / "memo.json")
    memo_summary = read_json(a / "run_summary_memo.json")
    claims = [(c["claim_id"], c["issue_id"], c["metric"], c["value"]) for c in csv.DictReader(open(a / "memo" / "claims.csv"))]

    costs, calls = {}, {}
    for line in open(grading / "calls.jsonl"):
        c = json.loads(line)
        costs[c["role"]] = costs.get(c["role"], 0.0) + (c.get("cost_usd") or 0.0)
        calls[c["role"]] = calls.get(c["role"], 0) + 1
    ingestion = read_json(grading / "ingestion.json")
    verify = read_json(a / "run_summary_verify.json")["verify"]
    golden_path = ROOT / "evals" / "results" / "golden_eval_final" / "golden_eval.json"
    golden = read_json(golden_path) if golden_path.exists() else None
    meta = {
        "run": read_json(grading / "run.json"),
        "coverage": {"records_total": sum(status.values()), "records_by_status": status,
                     "classified": len(reviews), "exact_text_cache_reuses": cache_reuses,
                     "issues": len(issues), "complaints_grouped": len(membership)},
        "ingestion": ingestion,
        "totals": pack["totals"],
        "scope_note": pack.get("scope_note"),
        "cost_usd_by_role": {k: round(v, 4) for k, v in costs.items()},
        "calls_by_role": calls,
        "verifier": {"sample": verify.get("declared_sample_size"), "agreement": verify["agreement"]},
        "golden": golden and {"n_cases": golden["n_cases"], "agreement": golden["agreement"],
                              "severity_mae": golden["severity_mae"]},
        "memo_model": memo_summary.get("memo", {}).get("model") or "claude-sonnet-5-5",
        "loaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return meta, issues, reviews, memo, claims


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", default="full")
    args = ap.parse_args()
    load_env()
    url = os.environ.get("SUPABASE_DB_URL")
    if not url:
        raise SystemExit("SUPABASE_DB_URL is not set in .env")
    t0 = time.monotonic()
    meta, issues, reviews, memo, claims = gather(args.run)
    print(f"[export_db] gathered {len(issues)} issues, {len(reviews)} reviews, {len(claims)} claims")
    db = pg_connect(url)
    db.run("BEGIN")
    for stmt in open(ROOT / "dashboard" / "schema.sql").read().split(";\n"):
        if stmt.strip() and not all(l.strip().startswith("--") or not l.strip() for l in stmt.splitlines()):
            db.run(stmt)
    bulk_insert(db, "run_meta", ["key", "value"], [(k, json.dumps(v)) for k, v in meta.items()])
    bulk_insert(db, "issues", ["issue_id", "rank", "topic", "name", "description", "complaint_count", "severity_sum",
                               "mean_severity", "priority_score", "share_of_complaints", "cancellation_count",
                               "severity_4plus_count", "needs_review_count", "mean_sentiment", "severity_histogram",
                               "complaints_by_month"], issues)
    bulk_insert(db, "reviews", ["review_id", "scope_rank", "review_text", "review_rating", "review_timestamp",
                                "app_version", "topic", "intent", "severity", "sentiment", "evidence_quote", "entities",
                                "needs_review", "cache_source_id", "issue_id"], reviews)
    bulk_insert(db, "memo", ["id", "recommended_issue_id", "markdown", "cited_reviews", "model"],
                [(1, memo["recommended_issue_id"], memo["memo_markdown"], json.dumps(memo["cited_reviews"]),
                  meta["memo_model"])])
    bulk_insert(db, "claims", ["claim_id", "issue_id", "metric", "value"], claims)
    db.run("COMMIT")
    counts = {t: db.run(f"SELECT count(*) FROM {t}")[0][0] for t in ("run_meta", "issues", "reviews", "memo", "claims")}
    db.close()
    print(f"[export_db] loaded {counts} in {time.monotonic() - t0:.1f}s")


if __name__ == "__main__":
    main()

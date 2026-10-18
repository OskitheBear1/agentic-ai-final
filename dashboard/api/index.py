"""Dashboard backend: a read-only FastAPI app that serves saved pipeline results from Supabase Postgres.

Vercel detects FastAPI and runs this app as one Python function for every route. It never calls a model; every number it returns
is read from the database that `python -m pipeline.export_db` loaded from the run's saved outputs.
Locally: `SUPABASE_DB_URL=... uvicorn api.index:app --reload` from the dashboard/ folder.
"""
import json
import os
import ssl
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import unquote, urlparse

import pg8000.native
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

app = FastAPI(title="Spotify review issues API", docs_url="/api/docs", openapi_url="/api/openapi.json")
CA_FILE = Path(__file__).with_name("supabase-prod-ca-2021.crt")
PAGE = Path(__file__).resolve().parent.parent / "public" / "index.html"


def supabase_ssl():
    # Full verification (chain + hostname) against Supabase's published root CA, bundled next to the API.
    # Python 3.13+ X509_STRICT rejects that 2021 root for lacking a key-usage field, so only that flag is relaxed.
    ctx = ssl.create_default_context(cafile=str(CA_FILE))
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx

ISSUE_COLS = ("issue_id, rank, topic, name, description, complaint_count, severity_sum, mean_severity, priority_score, "
              "share_of_complaints, cancellation_count, severity_4plus_count, needs_review_count, mean_sentiment")
REVIEW_COLS = ("review_id, review_text, review_rating, review_timestamp, app_version, topic, intent, severity, "
               "sentiment, evidence_quote, entities, needs_review, cache_source_id, issue_id")


@contextmanager
def db():
    u = urlparse(os.environ["SUPABASE_DB_URL"])
    con = pg8000.native.Connection(user=unquote(u.username), password=unquote(u.password or ""), host=u.hostname,
                                   port=u.port or 5432, database=(u.path or "/postgres").lstrip("/") or "postgres",
                                   ssl_context=supabase_ssl(), timeout=20)
    try:
        yield con
    finally:
        con.close()


def rows(con, sql, **params):
    out = con.run(sql, **params)
    names = [c["name"] for c in con.columns]
    return [dict(zip(names, (float(v) if type(v).__name__ == "Decimal" else v for v in r))) for r in out]


def cached(data, seconds=300):
    # Saved results only change when the loader reruns, so let Vercel's CDN cache responses briefly.
    return JSONResponse(data, headers={"Cache-Control": f"public, s-maxage={seconds}, stale-while-revalidate=600"})


@app.get("/api/health")
def health():
    with db() as con:
        return {"ok": True, "reviews": con.run("SELECT count(*) FROM reviews")[0][0]}


@app.get("/api/metrics")
def metrics():
    with db() as con:
        meta = {r["key"]: r["value"] for r in rows(con, "SELECT key, value FROM run_meta")}
        live = rows(con, "SELECT count(*) AS classified, count(*) FILTER (WHERE issue_id IS NOT NULL) AS complaints, "
                         "count(*) FILTER (WHERE needs_review) AS needs_review, "
                         "round(avg(sentiment)::numeric, 4) AS mean_sentiment FROM reviews")[0]
    meta["from_reviews_table"] = live  # recomputed from the stored rows, so the page can show they agree
    return cached(meta)


@app.get("/api/ranking")
def ranking():
    with db() as con:
        return cached(rows(con, f"SELECT {ISSUE_COLS} FROM issues ORDER BY rank"))


@app.get("/api/issues/{issue_id}")
def issue(issue_id: str, limit: int = Query(15, ge=1, le=50)):
    with db() as con:
        found = rows(con, f"SELECT {ISSUE_COLS}, severity_histogram, complaints_by_month FROM issues "
                          "WHERE issue_id = :i", i=issue_id)
        if not found:
            raise HTTPException(404, "unknown issue")
        found[0]["reviews"] = rows(con, f"SELECT {REVIEW_COLS} FROM reviews WHERE issue_id = :i "
                                        "ORDER BY severity DESC, sentiment ASC, review_id LIMIT :n", i=issue_id, n=limit)
    return cached(found[0])


@app.get("/api/reviews/{review_id}")
def review(review_id: str):
    with db() as con:
        found = rows(con, f"SELECT {REVIEW_COLS} FROM reviews WHERE review_id = :i", i=review_id)
    if not found:
        raise HTTPException(404, "review not in the classified scope")
    return cached(found[0])


@app.get("/api/recommendations")
def recommendations():
    with db() as con:
        memo = rows(con, "SELECT recommended_issue_id, markdown, cited_reviews, model FROM memo WHERE id = 1")[0]
        claims = rows(con, "SELECT c.claim_id, c.issue_id, c.metric, c.value, "
                           "CASE c.metric WHEN 'complaint_count' THEN i.complaint_count::text "
                           "WHEN 'severity_sum' THEN i.severity_sum::text WHEN 'mean_severity' THEN i.mean_severity::text "
                           "WHEN 'priority_score' THEN i.priority_score::text END AS db_value "
                           "FROM claims c JOIN issues i USING (issue_id) ORDER BY length(c.claim_id), c.claim_id")
        extra = rows(con, "SELECT claim_id, issue_id, metric, period, value, numerator, denominator, source FROM extra_claims")
        months = {r["issue_id"]: r for r in rows(con, "SELECT issue_id, complaint_count, cancellation_count, "
                                                       "severity_4plus_count, complaints_by_month FROM issues")}
        periods = dict(rows(con, "SELECT value FROM run_meta WHERE key = 'comparable_periods'")[0]["value"])
        ids = [c["review_id"] for c in memo["cited_reviews"]]
        cited = rows(con, f"SELECT {REVIEW_COLS} FROM reviews WHERE review_id = ANY(CAST(:ids AS text[]))",
                     ids="{" + ",".join(ids) + "}")
    for c in claims:  # a claim is supported when the memo's number equals the stored ranking value
        try:
            c["matches_ranking"] = float(c["value"]) == float(c["db_value"])
        except (TypeError, ValueError):
            c["matches_ranking"] = False
    total_complaints = sum(i["complaint_count"] for i in months.values())
    for c in extra:  # recompute each extra claim from the stored issue rows, not from the claim file
        i = months[c["issue_id"]]
        if c["metric"] in ("cancellation_count", "severity_4plus_count"):
            c["db_value"] = str(i[c["metric"]])
        elif c["metric"] == "share_of_complaints_pct":
            c["db_value"] = f"{100 * i['complaint_count'] / total_complaints:.1f}%"
        elif c["period"] in periods:
            mine = sum(i["complaints_by_month"].get(m, 0) for m in periods[c["period"]])
            every = sum(x["complaints_by_month"].get(m, 0) for x in months.values() for m in periods[c["period"]])
            c["db_value"] = str(mine) if c["metric"] == "period_complaints" else f"{100 * mine / every:.1f}%"
        else:
            c["db_value"] = None
        c["matches_ranking"] = c["db_value"] == c["value"]
    claims += extra
    claims.sort(key=lambda c: int(c["claim_id"].lstrip("C")))
    memo["claims"] = claims
    memo["cited"] = cited
    return cached(memo)


@app.get("/", include_in_schema=False)
def page():
    # The dashboard page; on Vercel the CDN also serves public/ directly.
    return FileResponse(PAGE, headers={"Cache-Control": "public, s-maxage=300"})

"""Offline tests (no API key, no model calls). Run: .venv/bin/python -m tests.test_offline"""

import filecmp
import json
import re
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_golden_labels_never_reach_model_code():
    """Human golden labels live only in evals/; no model-calling module or prompt may reference them."""
    bad = []
    for p in list((ROOT / "pipeline").glob("*.py")) + [q for q in (ROOT / "prompts").glob("*") if q.is_file()]:
        t = p.read_text()
        if re.search(r"golden_50_labeled|gold_benchmark|golden_50_labeling", t):
            bad.append(p.name)
    assert not bad, bad


def test_enrich_only_dispatches_declared_scope():
    src = (ROOT / "pipeline" / "enrich.py").read_text()
    assert "WHERE r.pre_status='pending'" in src
    db = ROOT / "state" / "full.db"
    if db.exists():
        con = sqlite3.connect(db)
        n = con.execute("SELECT COUNT(*) FROM reviews WHERE pre_status='pending'").fetchone()[0]
        out = con.execute("SELECT COUNT(*) FROM reviews WHERE pre_status='pending' AND scope_rank IS NULL").fetchone()[0]
        assert n == 100_000 and out == 0, (n, out)


def test_rank_reproduces_saved_ranking():
    from pipeline.rank import rank, read_membership, read_records, write
    for run in ("pilot", "dev500", "dev10k", "full"):
        g = ROOT / "artifacts" / run / "grading"
        rec = g / "records.jsonl.gz" if (g / "records.jsonl.gz").exists() else g / "records.jsonl"
        if not (g / "ranking.csv").exists():
            continue
        with tempfile.TemporaryDirectory() as d:
            rows, aggs = rank(read_records(rec), read_membership(g / "membership.csv"))
            write(rows, aggs, d)
            assert filecmp.cmp(Path(d) / "ranking.csv", g / "ranking.csv", shallow=False), run


def test_quotes_are_exact_substrings():
    from pipeline.features import evidence_quote
    samples = ["Great", "  spaced  ", "A" * 300 + ". The ads are terrible! " + "B" * 50, "line one\nline two with lyrics missing\n" * 20]
    for s in samples:
        for t in ("usability", "catalog", "other"):
            q = evidence_quote(s, t)
            assert q and q in s


def test_cost_math_scales_with_rates():
    from pipeline.ledger import call_cost
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000}
    rates = {("claude-haiku-5-5", "input_tokens"): 0.10 / 1e6, ("claude-haiku-5-5", "output_tokens"): 0.50 / 1e6}
    one = call_cost("claude-haiku-5-5", usage, rates)
    two = call_cost("claude-haiku-5-5", usage, {k: v * 2 for k, v in rates.items()})
    assert abs(one - 0.60) < 1e-9 and abs(two - 2 * one) < 1e-9


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                fails += 1
                print("FAIL", name, e)
    sys.exit(1 if fails else 0)

"""Run state: SQLite tables for results, the call log and stage invocations.

All writes for one enrichment batch happen in a single transaction, so an interruption can never
leave a half-saved batch or double-count a result.
"""

import json
import sqlite3
import time

from .common import STATE_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
  review_id TEXT PRIMARY KEY, status TEXT NOT NULL, topic TEXT, intent TEXT, sentiment REAL, severity INTEGER,
  entities TEXT, evidence_quote TEXT, needs_review INTEGER, label_config TEXT, cache_source_id TEXT,
  attempts INTEGER, reason TEXT, confidence TEXT, batch_no INTEGER, phase TEXT, completed_at REAL
);
CREATE TABLE IF NOT EXISTS calls (
  request_id TEXT PRIMARY KEY, run TEXT, role TEXT, review_ids TEXT, model TEXT, phase TEXT, outcome TEXT,
  label_config TEXT, input_tokens INTEGER, output_tokens INTEGER, cache_read_input_tokens INTEGER,
  cache_creation_input_tokens INTEGER, cost_usd REAL, started_at REAL, duration_s REAL, attempt INTEGER,
  error TEXT, fault_injected INTEGER, invocation INTEGER, artifacts TEXT
);
CREATE TABLE IF NOT EXISTS invocations (
  inv_id INTEGER PRIMARY KEY AUTOINCREMENT, stage TEXT, phase TEXT, started_at REAL, ended_at REAL,
  status TEXT, args TEXT, summary TEXT
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


def connect(run):
    con = sqlite3.connect(STATE_DIR / f"{run}.db", timeout=60, isolation_level=None)  # autocommit; explicit BEGIN
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def start_invocation(con, stage, phase, args):
    cur = con.execute("INSERT INTO invocations(stage, phase, started_at, status, args) VALUES (?,?,?,?,?)",
                      (stage, phase, time.time(), "running", json.dumps(args, default=str)))
    return cur.lastrowid


def end_invocation(con, inv_id, status, summary):
    con.execute("UPDATE invocations SET ended_at=?, status=?, summary=? WHERE inv_id=?",
                (time.time(), status, json.dumps(summary, default=str), inv_id))


def log_call(con, c):
    """c: dict matching the calls table. Caller controls the transaction."""
    cols = ["request_id", "run", "role", "review_ids", "model", "phase", "outcome", "label_config", "input_tokens",
            "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "cost_usd", "started_at",
            "duration_s", "attempt", "error", "fault_injected", "invocation", "artifacts"]
    row = {k: c.get(k) for k in cols}
    row["review_ids"] = json.dumps(row["review_ids"] or [])
    row["fault_injected"] = int(bool(row["fault_injected"]))
    con.execute(f"INSERT INTO calls({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", [row[k] for k in cols])

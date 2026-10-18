"""Editable rates, per-call cost, and the global spend ledger shared by every stage and run.

Cost of a call = sum over mutually exclusive billing items of (billed units × price per unit).
Before dispatching a call the orchestrator *reserves* a worst-case estimate; it refuses new work
when spent + reserved + next reservation would exceed the budget cap.
"""

import csv
import sqlite3
import threading
import time
from pathlib import Path

from .common import ROOT, STATE_DIR

RATES_CSV = ROOT / "cost" / "rates.csv"


class BudgetExceeded(RuntimeError):
    pass


def load_rates(path=RATES_CSV):
    rates = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rates[(r["model"], r["billing_item"])] = float(r["usd_per_million_units"]) / 1_000_000
    return rates


def rate_model(model):
    """Map a served model ID (e.g. 'jev-1.13.0') to its rates.csv row ('jev')."""
    return "jev" if model.startswith("jev") else model


def call_cost(model, usage, rates=None):
    """usage: dict with input_tokens/output_tokens and optional cache_* tokens (all mutually exclusive)."""
    rates = rates or load_rates()
    m = rate_model(model)
    total = 0.0
    for item in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens"):
        units = usage.get(item) or 0
        if units:
            if (m, item) not in rates:
                raise KeyError(f"No rate for {m}/{item}; add it to cost/rates.csv")
            total += units * rates[(m, item)]
    return total


class Ledger:
    """Process-wide, thread-safe spend ledger persisted in state/ledger.db (shared across runs)."""

    def __init__(self, budget_usd, path=None):
        STATE_DIR.mkdir(exist_ok=True)
        import os
        self.path = Path(path or os.environ.get("PIPELINE_LEDGER") or STATE_DIR / "ledger.db")
        self.budget = float(budget_usd)
        self.lock = threading.Lock()
        self.reserved = {}
        con = sqlite3.connect(self.path)
        con.execute("CREATE TABLE IF NOT EXISTS spend (request_id TEXT PRIMARY KEY, run TEXT, role TEXT, model TEXT, "
                    "cost_usd REAL, ts REAL)")
        con.commit()
        con.close()

    def spent(self):
        con = sqlite3.connect(self.path)
        v = con.execute("SELECT COALESCE(SUM(cost_usd),0) FROM spend").fetchone()[0]
        con.close()
        return v

    def reserve(self, key, est_usd):
        with self.lock:
            if self.spent() + sum(self.reserved.values()) + est_usd > self.budget:
                raise BudgetExceeded(f"budget ${self.budget:.2f} reached (spent ${self.spent():.4f})")
            self.reserved[key] = est_usd

    def settle(self, key, request_id, run, role, model, cost_usd):
        with self.lock:
            self.reserved.pop(key, None)
            if cost_usd:
                con = sqlite3.connect(self.path)
                con.execute("INSERT OR REPLACE INTO spend VALUES (?,?,?,?,?,?)", (request_id, run, role, model, cost_usd, time.time()))
                con.commit()
                con.close()

    def release(self, key):
        with self.lock:
            self.reserved.pop(key, None)

"""Shared constants and helpers used by every pipeline stage."""

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

# Reuse the course checker's exact CSV reader and row hash so our hashes match the grader's.
from check_submission import FIELDS, INTENTS, TOPICS, csv_rows, profile, row_sha, sha  # noqa: E402,F401

SAMPLE_SEED = "berkeley-fall-2026-assignment-5-v1"
VALID_RATINGS = {"1", "2", "3", "4", "5"}
STATE_DIR = ROOT / "state"
ARTIFACTS = ROOT / "artifacts"


def sample_rank(review_id):
    """Same ordering the course used to draw the golden/dev samples (prepare_dataset.py)."""
    return int.from_bytes(hashlib.sha256((SAMPLE_SEED + ":" + review_id).encode()).digest(), "big")


def text_sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)  # atomic


def load_env():
    """Load API keys from .env into the environment. Never print or log them."""
    env = ROOT / ".env"
    if env.exists():
        from dotenv import load_dotenv
        load_dotenv(env)


def fingerprint(*parts):
    """Stable hash of a stage's inputs + configuration, used to skip unchanged downstream work."""
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def cached_stage(stage_dir, fp):
    """Return the saved summary if this stage already ran with identical inputs/config, else None."""
    f = Path(stage_dir) / "fingerprint.json"
    if f.exists():
        saved = json.loads(f.read_text())
        if saved.get("fingerprint") == fp:
            return saved.get("summary")
    return None


def save_fingerprint(stage_dir, fp, summary):
    write_json(Path(stage_dir) / "fingerprint.json", {"fingerprint": fp, "summary": summary})

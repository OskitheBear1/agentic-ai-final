"""Compare pipeline predictions with the human-labeled golden 50 (no model calls).

The human labels are read only here, after predictions exist; no model-calling stage reads evals/.
Usage: python3 evals/golden_eval.py --records artifacts/golden/grading/records.jsonl --out evals/results/golden_eval_golden
"""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from check_submission import INTENTS, TOPICS  # noqa: E402

SENTIMENT_TOLERANCE = 0.5  # predeclared in prompts/labels_v1.md


def load_records(path):
    import gzip
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        return {r["review_id"]: r for r in map(json.loads, f)}


def confusion(pairs, labels):
    m = {a: Counter() for a in labels}
    for h, p in pairs:
        m[h][p] += 1
    return {h: {p: m[h][p] for p in labels if m[h][p]} for h in labels if m[h]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True)
    ap.add_argument("--gold", default=str(ROOT / "evals/gold_benchmark.json"))
    ap.add_argument("--gold-csv", default=str(ROOT / "evals/golden_50_labeled.csv"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    recs = load_records(a.records)
    gold = json.loads(Path(a.gold).read_text())["cases"]
    human = {r["review_id"]: r for r in csv.DictReader(open(a.gold_csv, encoding="utf-8"))}
    rows, tp, ip = [], [], []
    for g in gold:
        rid = g["review_id"]
        h, p = human[rid], recs.get(rid, {})
        ok = p.get("status") == "completed"
        text = h["review_text"]
        r = {"review_id": rid, "review_text": text, "prediction_status": p.get("status", "missing"),
             "human_topic": g["accepted_topic"][0], "pred_topic": p.get("topic"),
             "human_intent": g["accepted_intent"][0], "pred_intent": p.get("intent"),
             "human_severity": g["accepted_severity"][0], "pred_severity": p.get("severity"),
             "human_sentiment": g["sentiment"], "pred_sentiment": p.get("sentiment"),
             "human_needs_review": g["needs_review"], "pred_needs_review": p.get("needs_review"),
             "pred_evidence_quote": p.get("evidence_quote"), "human_evidence_quote": h["evidence_quote"],
             "pred_entities": p.get("entities"), "human_entities": json.loads(h["entities"] or "[]")}
        r["topic_ok"] = ok and p["topic"] in g["accepted_topic"]
        r["intent_ok"] = ok and p["intent"] in g["accepted_intent"]
        r["severity_ok"] = ok and p["severity"] in g["accepted_severity"]
        r["severity_abs_err"] = min(abs(p["severity"] - s) for s in g["accepted_severity"]) if ok else None
        r["sentiment_abs_err"] = round(abs(p["sentiment"] - g["sentiment"]), 4) if ok else None
        r["sentiment_ok"] = ok and r["sentiment_abs_err"] <= SENTIMENT_TOLERANCE
        r["quote_is_substring"] = ok and p["evidence_quote"] in text
        r["quote_is_full_review"] = ok and p["evidence_quote"] == text.strip()
        r["unsupported_entities"] = [e for e in (p.get("entities") or []) if e not in r["human_entities"]] if ok else None
        r["all_core_ok"] = r["topic_ok"] and r["intent_ok"] and r["severity_ok"]
        rows.append(r)
        if ok:
            tp.append((r["human_topic"], p["topic"]))
            ip.append((r["human_intent"], p["intent"]))
    n = len(rows)
    valid = [r for r in rows if r["prediction_status"] == "completed"]
    frac = lambda k: round(sum(bool(r[k]) for r in rows) / n, 4)  # noqa: E731  missing counts as wrong
    flagged = [r for r in valid if r["pred_needs_review"]]
    wrong = [r for r in valid if not r["all_core_ok"]]
    report = {
        "n_cases": n, "valid_predictions": len(valid), "missing_or_quarantined": n - len(valid),
        "ambiguous_cases_marked_by_human": sum(r["human_needs_review"] for r in rows),
        "agreement": {"topic": frac("topic_ok"), "intent": frac("intent_ok"), "severity_exact": frac("severity_ok"),
                      "sentiment_within_0.5": frac("sentiment_ok"), "all_three_core": frac("all_core_ok")},
        "severity_mae": round(sum(r["severity_abs_err"] for r in valid) / len(valid), 4) if valid else None,
        "sentiment_mae": round(sum(r["sentiment_abs_err"] for r in valid) / len(valid), 4) if valid else None,
        "evidence_quote": {"exact_substring": sum(r["quote_is_substring"] for r in valid),
                           "whole_review_used": sum(r["quote_is_full_review"] for r in valid)},
        "needs_review_as_prediction": {
            "flagged": len(flagged), "flagged_and_wrong": sum(not r["all_core_ok"] for r in flagged),
            "wrong_total": len(wrong), "wrong_but_unflagged": sum(not r["pred_needs_review"] for r in wrong),
            "agreement_with_human_flag": round(sum(r["pred_needs_review"] == r["human_needs_review"] for r in valid) / max(len(valid), 1), 4)},
        "per_topic_counts": {"human": dict(Counter(r["human_topic"] for r in rows)), "predicted": dict(Counter(r["pred_topic"] for r in valid))},
        "topic_confusion_human_to_pred": confusion(tp, TOPICS),
        "intent_confusion_human_to_pred": confusion(ip, INTENTS),
        "entities_predicted_not_in_human_list": sum(len(r["unsupported_entities"] or []) for r in valid),
        "note": "50 cases are a small diagnostic sample, not a population accuracy estimate. Golden labels were not used to tune prompts.",
    }
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "golden_eval.json").write_text(json.dumps(report, indent=2) + "\n")
    with (out / "golden_cases.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, list) else v for k, v in r.items()})
    with (out / "disagreements.md").open("w", encoding="utf-8") as f:
        f.write("# Golden-50 disagreements (human vs pipeline)\n\n| review | human t/i/s | pred t/i/s | flagged |\n|---|---|---|---|\n")
        for r in rows:
            if not r["all_core_ok"]:
                t = r["review_text"].replace("\n", " ").replace("|", "/")[:140]
                f.write(f"| {t} | {r['human_topic']}/{r['human_intent']}/{r['human_severity']} | "
                        f"{r['pred_topic']}/{r['pred_intent']}/{r['pred_severity']} | {r['pred_needs_review']} |\n")
    print(json.dumps({k: report[k] for k in ("valid_predictions", "agreement", "severity_mae", "sentiment_mae", "needs_review_as_prediction")}, indent=1))


if __name__ == "__main__":
    main()

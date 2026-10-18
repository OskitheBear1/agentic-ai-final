# Spotify Review Issues: a multi-agent review pipeline

**Live dashboard: https://agentic-ai-final-three.vercel.app** (public, no login, no API key needed).

**Question:** Spotify is at the end of this review window (May 2022 to Nov 2023). Where should next quarter's product effort go?
**Answer from the final run:** fix **`billing.basic_features_behind_premium`**, meaning basic controls such as skipping, choosing songs and queueing that are now locked behind Premium. It has 6,254 complaints and a severity sum of 17,653 [C1, C2]. Its share of all complaints rose from 5–7% per quarter to **28.7% in Sep–Oct 2023**. See the [memo](artifacts/full/memo/memo.md) and the [trend table](evals/results/trend_shares.md).

**Final run:** `full`, which classified a declared scope of **100,000** of the 660,622 reviews (the course's seeded first 100,000). All 660,622 source IDs are ingested and accounted for. The other 560,609 nonempty reviews are recorded as quarantined (`outside_declared_classification_scope`) and are **not** classified. The 13 empty texts are quarantined as `empty_review_text`. The downloadable grading export is in [`grading/`](grading/).

---

## Rubric → evidence map

| Rubric item | Evidence |
|---|---|
| **Deliverable quality** | |
| Accessible code, setup and artifacts | [Setup](#setup-and-commands) · [`requirements.txt`](requirements.txt) · [`.env.example`](.env.example) · [`.gitignore`](.gitignore) · [`pipeline/`](pipeline/) · [`grading/`](grading/) · [`artifacts/full/`](artifacts/full/) · clean-clone offline check ([below](#reproduce-without-an-api-key)) |
| Clear architecture, shared schema, provenance | [Architecture](#architecture) · [label definitions `prompts/labels_v1.md`](prompts/labels_v1.md) · [Jev questions `prompts/jev_questions_v1.py`](prompts/jev_questions_v1.py) · [frozen taxonomy](prompts/taxonomy_v1.json) · [`grading/run.json`](grading/run.json) · [ingestion report](artifacts/full/ingest/ingestion_report.json) · every record carries `source_sha256`, `label_config` and `cache_source_id` |
| Memo numbers linked to calculations and evidence | [memo.md](artifacts/full/memo/memo.md) cites claim IDs from [`grading/claims.csv`](grading/claims.csv), and each one equals [`grading/ranking.csv`](grading/ranking.csv) (checked by code, by the course checker and by the [dashboard check](evals/results/dashboard_check.json)) · [evidence pack](artifacts/full/memo/evidence_pack.json) · [traced review](#one-review-traced-end-to-end) |
| Coherent recommendation, alternatives, limitations | [Recommendation](#recommendation) · [memo](artifacts/full/memo/memo.md) · [trend shares](evals/results/trend_shares.md) · [Limitations](#limitations-and-known-issues) |
| **Testing & evaluation** | |
| 50 human labels, per-field comparison, error analysis | [golden labels](evals/golden_50_labeled.csv) · [final comparison](evals/results/golden_eval_final/golden_eval.json) · [per-case](evals/results/golden_eval_final/golden_cases.csv) · [disagreements](evals/results/golden_eval_final/disagreements.md) · [checker `--gold` output](#golden-set-50-human-labels) |
| Independent verification, planted errors, injection | [verifier disagreement report](artifacts/full/verify/disagreement_report.json) · [verifier predictions](artifacts/full/verify/verifier_predictions.jsonl) · [planted errors 30/30](evals/results/planted.json) · [injection tests](evals/results/injection.json) (+ [before the fix](evals/results/injection_jev-q1.json)) |
| Real 100-review cold/warm pilot, offline calculator, T3 controls | [cost report](cost/report.md) · [`cost/calculator.py`](cost/calculator.py) · [pilot records](cost/pilot_records.jsonl)/[calls](cost/pilot_calls.jsonl) · [usage](cost/usage.csv)/[rates](cost/rates.csv) · [T3 retry/spend/recovery](evals/results/t3.json) · [real credit-outage recovery](#one-failed-case-and-how-it-was-handled) |
| **Working result** | |
| Full ingestion, coverage, successful classification | [ingestion](grading/ingestion.json) · [records](grading/records.jsonl.gz) · [self-check results](#course-checker-self-check) (accounted 1.0, 100,000 valid completed, 0 failed) |
| Runnable staged program, bounded calls, saved handoffs, resume | [`pipeline/run.py`](pipeline/run.py) · [`grading/calls.jsonl`](grading/calls.jsonl) (121,447 calls, initial/resume phases) · checkpoints [before](grading/checkpoint_before.json)/[after](grading/checkpoint_after.json) · [interruption/resume](#interruption-and-resume) · [screen recording](https://github.com/OskitheBear1/agentic-ai-final/releases/download/p5-full-run/resume_recording_full_run.mov) |
| Reproducible ranking, deployed dashboard + backend + DB, grounded recommendation | `python -m pipeline.rank` reproduces [`ranking.csv`](grading/ranking.csv) byte for byte · [dashboard](https://agentic-ai-final-three.vercel.app) · [API](dashboard/api/index.py) · [DB schema](dashboard/schema.sql) · [loader](pipeline/export_db.py) · [live check 10/10](evals/results/dashboard_check.json) |

---

## Results summary

**Measured on the final run** (from `grading/` and `artifacts/full/`):

| | |
|---|---|
| Source rows ingested and profiled | **660,622**. 13 empty texts, 159,701 missing `app_version`, 0 duplicate IDs, 484,189 distinct nonempty texts, all matching `manifest.json` |
| Accounted for | **660,622 / 660,622** (1.0). Every source ID has exactly one record. |
| **Completed classifications** | **100,000** (the declared scope). 0 failed and 0 quarantined inside the scope. |
| Quarantined | 560,609 `outside_declared_classification_scope` (not classified) + 13 `empty_review_text` |
| Exact-text cache reuse | 21,901 of the 100,000 rows reused an identical text's labels (direct `cache_source_id`), so Jev was called for 78,099 distinct texts |
| Flagged `needs_review` | 22,208 (low model confidence). Kept in all totals and marked. |
| Complaint/cancellation reviews grouped | 45,084 reviews into 34 issues (8 topics) |
| Independent verifier (Claude Haiku, 1,000 random reviews) | Agreement: topic **82.6%**, intent **92.0%**, severity **86.3%** (±1: 98.9%), sentiment ±0.5 **95.9%**. 0 verifier failures. |
| Golden 50 (human labels) | Agreement: topic **82%**, intent **76%**, severity **82%** (MAE 0.20), sentiment ±0.5 **86%**. All 50 quotes are exact substrings. |
| Full-run API cost | **$4.94** (Jev enrich $4.05, grouping $0.80, verify $0.02, memo $0.07 for 2 generations). Whole project including pilot, dev runs and tests: **$5.65** by the spend ledger. |
| Full-run wall-clock (active) | **≈72 min**: enrich 53.1 min across 3 sessions (31.4 reviews/s, 4 workers), verify 2.2 min, group 16.1 min (incl. the outage retry), rank + memo + export under 1 min |
| Calls | 121,447 recorded (78,099 enrich, 43,306 group of which 2,916 failed with HTTP 402 and were retried, 40 verify, 2 memo) |

**Estimates (made before the run, in [`cost/report.md`](cost/report.md)):** 100k base **$4.79**, conservative $5.20, about 1.0 h at 4 workers. The measured $4.94 falls between them. A full-corpus run (484,189 distinct texts) would have cost about $29.32, more than the $12 budget, which is why the scope is 100,000.

**Measured 100-review pilot** ([`cost/report.md`](cost/report.md)): cold run 41.5 s and $0.0372 on an empty cache with 1 worker. Warm run 0.19 s, $0, 0 new calls in any stage.

---

## Recommendation

From [`artifacts/full/memo/memo.md`](artifacts/full/memo/memo.md), written by Claude Sonnet 5.5 from the saved [evidence pack](artifacts/full/memo/evidence_pack.json) only. Code rejects the memo unless every claim number, issue ID and review ID it cites exists in the saved calculations.

- **Priority:** `billing.basic_features_behind_premium`. 6,254 complaints [C1], severity sum 17,653 [C2], mean severity 2.822673 [C3]. 1,191 of these reviews express cancellation *intent* (not observed churn).
- **Why not #1?** The top score belongs to `other.general` (20,424 [C4]). That is a catch-all bucket of generic negative reviews with low severity (1.846321 [C5]) and no single problem to fix.
- **Alternatives:** `usability.ad_frequency_loudness` (5,120 complaints [C6], score 10,856 [C7], lower severity 2.120313 [C8]). `playback.playback_interruptions` (2,461 complaints [C9], highest severity 3.419342 [C10], score 8,415 [C11]), a strong reliability candidate with smaller reach.
- **Representative reviews:** `21f4f8cd-5846-44aa-9283-cfb3dc51e257`, `9321ddc2-a0ef-411a-b7e7-8437fc704d2f` (paywall), `1e4d3214-63de-4ba0-9870-a4ee8aa32942` (ads), `a3794dbd-4918-4f64-9307-22a49bf6fd5a` (playback).

**Trend in comparable periods** ([`evals/results/trend_shares.md`](evals/results/trend_shares.md), `python3 evals/trend_shares.py`). Share = issue complaints ÷ all complaint/cancellation reviews in the period. The partial months 2022-05 and 2023-11 are excluded.

| period | classified reviews | complaints | basic features behind Premium | ad frequency/loudness | playback interruptions |
|---|---|---|---|---|---|
| 2022-06..08 | 14,234 | 4,609 | 300 (6.5%) | 796 (17.3%) | 510 (11.1%) |
| 2022-09..11 | 12,251 | 3,568 | 258 (7.2%) | 739 (20.7%) | 262 (7.3%) |
| 2022-12..2023-02 | 12,261 | 4,055 | 221 (5.5%) | 688 (17.0%) | 508 (12.5%) |
| 2023-03..05 | 12,235 | 4,202 | 273 (6.5%) | 588 (14.0%) | 272 (6.5%) |
| 2023-06..08 | 21,685 | 11,098 | 527 (4.7%) | 993 (8.9%) | 362 (3.3%) |
| 2023-09..10 | 19,776 | 13,272 | **3,809 (28.7%)** | 937 (7.1%) | 361 (2.7%) |

The Premium paywall complaints are new and growing fast. Ad complaints are steady in count but shrinking as a share.

---

## Architecture

Code owns the order of stages, record accounting, validation, budgets, caching and all arithmetic. Models are used only where language judgment is needed. Every stage reads the previous stage's saved files and writes its own, so each handoff can be inspected.

```mermaid
flowchart TD
  CSV[(spotify_reviews_18months.csv<br/>660,622 rows)] --> P1

  subgraph P1["1. Prepare: code only"]
    I1[parse multiline CSV, hash each row,<br/>profile, find exact-duplicate texts,<br/>declare scope, quarantine empty texts]
  end
  P1 -->|state/full.db reviews<br/>artifacts/full/ingest/*| P2

  subgraph P2["2. Classify: Jev model + code"]
    O[orchestrator: batches of 50, 4 workers, 40 rps,<br/>spend ledger reserve/settle, exact-text cache] --> J[Jev Choice: topic, intent, severity<br/>Jev Score: sentiment<br/>1 review per request]
    J --> V1[code: schema check, allowed labels,<br/>ranges, exact quote, entities, needs_review]
    V1 -->|invalid: retry once<br/>API error: 2 retries, backoff + jitter| J
    V1 -->|still failing| Q[quarantine with reason + attempts]
  end
  P2 -->|records + calls, committed atomically per batch| P3

  subgraph P3["3. Verify: Claude Haiku + code"]
    H[Haiku relabels 1,000 random reviews,<br/>25 per request, never sees first labels] --> C3[code compares, confusion tables,<br/>disagreement report]
  end
  P2 --> P4
  subgraph P4["4. Group: frozen taxonomy + Jev + code"]
    T[taxonomy_v1.json<br/>proposed by Haiku on dev10k, edited and approved by a human] --> JG[Jev Choice picks 1 subtopic<br/>per distinct complaint text]
    JG -->|failure: code falls back to topic.general,<br/>rerun retries only failed texts| M[membership.csv]
  end
  P4 --> P5
  subgraph P5["5. Rank: code only"]
    R[severity_sum per issue, mean 6dp half-up,<br/>sort score desc then issue_id asc]
  end
  P5 -->|ranking.csv, aggregates.csv| P6
  subgraph P6["6. Memo: Claude Sonnet + code"]
    E[code builds bounded evidence pack:<br/>top issues, counts, quotes, review IDs] --> S[Sonnet writes memo + claims JSON]
    S --> CK[code rejects unknown IDs,<br/>numbers not in ranking; 1 retry]
  end
  P6 --> X[export: grading/ folder]
  X --> L[pipeline.export_db: code] --> DB[(Supabase Postgres<br/>run_meta, issues, reviews, memo, claims)]
  DB --> API[FastAPI on Vercel<br/>read-only, server-side DB URL] --> UI[Dashboard page<br/>metrics, ranking, AI memo + checked claims]
```

**Stop and retry paths** (all in [`pipeline/enrich.py`](pipeline/enrich.py) and [`pipeline/ledger.py`](pipeline/ledger.py)):
- **Invalid model output:** retried once, then the record is quarantined with a reason.
- **Temporary API errors and rate limits:** up to 2 retries (3 attempts in total) with exponential backoff and jitter.
- **Budget:** the ledger reserves each call's worst-case cost before dispatch and stops admitting work once spent + reserved would exceed `--budget`.
- **Stopping early:** Ctrl-C, `--max-batches` or `--time-limit` finish the current batch, save, and stop.
- **Resuming:** a rerun skips completed IDs.
- **Downstream stages:** skip when their input fingerprint is unchanged (this is how the warm run makes 0 calls).

### Why each model call is needed, and what code does instead

| Role | Model and settings | Why a model | What code does |
|---|---|---|---|
| Enrich | TypeSafe **Jev** (`jev-latest`, served `jev-1.13.0`). Choice for topic, intent and severity; Score for sentiment. Prompt `jev-q2`, schema `schema-v2`. | Reading messy, multilingual customer text against fixed definitions | Batching, cache lookup, schema and range checks, exact `evidence_quote` (deterministic: the whole review if short, else the best sentence), entities via a keyword lexicon, `needs_review` from confidence (< 0.7) |
| Verify | **Claude Haiku 5.5**, thinking disabled, structured output, `verify-v1` | An independent second reading | Random sample by SHA-256 order, comparison, confusion tables |
| Group | Taxonomy: **Claude Haiku 5.5** proposed it once on dev10k, then a human edited and froze it. Assignment: **Jev** Choice per distinct complaint text, `group-v1`. | Choosing the specific sub-problem a complaint describes | Membership file, fallback to `<topic>.general` on failure, counts |
| Rank | none | not needed | All arithmetic and ordering ([`pipeline/rank.py`](pipeline/rank.py)) |
| Memo | **Claude Sonnet 5.5**, adaptive thinking, effort low, structured output, `memo-v1` | Writing an argument and weighing alternatives | Builds the bounded evidence pack, then validates every claim, issue ID and review ID against saved files |

The label definitions shared by all roles and the human labeler are in [`prompts/labels_v1.md`](prompts/labels_v1.md). They follow `tools/GRADING_CONTRACT.md`, and their examples come from development files only. `label_config` on every record = `jev-1.13.0+jev-q2+schema-v2+quote-v1`. Changing any part changes the cache key.

### Dashboard, backend and database

- **Dashboard** ([`dashboard/public/index.html`](dashboard/public/index.html)), at https://agentic-ai-final-three.vercel.app:
  - overall metrics;
  - the AI recommendation, with a table checking each memo claim against the database value, and the cited reviews;
  - the full issue ranking (click an issue, or open `#issue/<issue_id>`, to see its monthly trend, severity mix and highest-severity reviews with the evidence quote highlighted);
  - topic and intent charts;
  - the label-quality checks.
- **Backend** ([`dashboard/api/index.py`](dashboard/api/index.py)): a read-only FastAPI app on Vercel with endpoints `/api/metrics`, `/api/ranking`, `/api/issues/{id}`, `/api/reviews/{id}`, `/api/recommendations` and `/api/health`. Interactive docs: [/api/docs](https://agentic-ai-final-three.vercel.app/api/docs). The database URL is a server-side Vercel environment variable and never reaches the browser. The TLS connection is verified against Supabase's root CA, which is bundled with the API.
- **Database** ([`dashboard/schema.sql`](dashboard/schema.sql)): Supabase Postgres. It stores the 100,000 classified reviews with source fields and labels, 34 issues with aggregates and monthly counts, the memo, its claims and run metrics. Row-level security is on with no policies, so Supabase's public REST API reads nothing. Load it with `python -m pipeline.export_db --run full` (about 2.5 min, 0 model calls).
- **Verified:** [`tests/check_dashboard.py`](tests/check_dashboard.py) compares the live API with the saved files: the ranking (all fields), totals, memo text, all 11 claims, the cited reviews and sampled labels. Result: **10/10 pass** ([`evals/results/dashboard_check.json`](evals/results/dashboard_check.json)). The page was also checked in a signed-out browser.

---

## One review traced end to end

Review **`c42b8c38-8258-4567-bbf6-0a5a6f331233`**: *"You can't listen to full songs on the app for free ,I'll use other apps"*

| Step | What happened | Where to see it |
|---|---|---|
| Source | Row 267,732, 1★, app 8.8.12.545, 2023-02-22 12:28:52. `source_sha256` `5eb9148c…cef41c`. Scope rank 71,423 (inside the first 100,000). | `grading/records.jsonl.gz` |
| Enrichment | Jev call `req_01a150ccc037706b8c1fb137cb608989`, phase **resume**, 1 attempt, 1,231 input + 198 output tokens, $0.0000517. Result: topic **billing**, intent **cancellation**, severity **3**, sentiment −0.585, `needs_review` false. Quote = whole review (exact substring). | `grading/calls.jsonl`, `grading/records.jsonl.gz` |
| Verification | In the 1,000-review sample. Haiku call `req_011CgAPoTmnZhMYnYrwufrXU` (25 reviews in the request) independently gave the same topic, intent and severity. | `artifacts/full/verify/verifier_predictions.jsonl` |
| Issue membership | Jev subtopic call `req_01a150e984667f39a1affb3098ad16be` → **`billing.basic_features_behind_premium`** | `grading/membership.csv` |
| Ranking | That issue is **rank 2** (6,254 complaints, severity sum 17,653, mean 2.822673). This review adds 3 to the severity sum and 1 to the cancellation count. | `grading/ranking.csv`, `artifacts/full/rank/aggregates.csv` |
| Memo claim | The memo recommends this issue, citing **C1** (complaint_count 6254) and **C2** (severity_sum 17653). The checker recomputes both from records + membership. | `grading/claims.csv`, `artifacts/full/memo/memo.md` |

### One failed case and how it was handled

Review **`3046d93b-9fcc-4a32-b689-297eb9fa3ce2`**: *"Worst experience, lot's of ad Play and specially vadakan songs."*

1. **The failure.** During grouping, the TypeSafe account ran out of prepaid credits. Starting at call 37,408 of 40,390, Jev returned `402 Your organization has no available TypeSafe API credits`. This review's subtopic call `failed-815efc55…` is recorded as `failed` in `grading/calls.jsonl`.
2. **Code's response.** The code put the review in the `usability.general` fallback, so no complaint was lost. It also logged the failure and refused to save the stage fingerprint, which marks the stage as incomplete.
3. **Why the budget control didn't catch it.** Our spend ledger caps *our* spend at $12, but it cannot see a provider's prepaid balance.
4. **The decision.** Don't accept a ranking with 2,916 complaints parked in fallback buckets. Top up the credits, then add resume to grouping ([`prior_assignments()` in `pipeline/group.py`](pipeline/group.py)): reuse the 37,474 succeeded choices and retry only the 2,916 failed texts.
5. **Recovery.** The rerun made 2,916 calls with 0 failures and cost $0.058. This review got call `req_01a150efe31c768092c0238c848af52a` → `usability.ad_frequency_loudness`. Rank, memo and export were then rerun. The failed calls stay in `calls.jsonl` as evidence.

**An ambiguous case:** golden review *"It's my best music app but now it's not...everything basic features is premium...."*. The human labeled it `other/complaint/2`; the pipeline gave `billing/complaint/3` and did not flag it. Both readings are defensible ("a paid-plan mention alone is not billing", but this one complains about a paywall). It is counted as a disagreement, not silently dropped ([disagreements](evals/results/golden_eval_final/disagreements.md)).

---

## Evaluation and system checks

### Golden set (50 human labels)
- **Labels.** The 50 reviews were labeled by hand before evaluation ([`evals/golden_50_labeled.csv`](evals/golden_50_labeled.csv), benchmark [`evals/gold_benchmark.json`](evals/gold_benchmark.json)). They were never used as model inputs, prompt examples or thresholds; `tests/test_offline.py::test_golden_labels_never_reach_model_code` enforces this. The two prompt changes (`jev-q2` anti-injection sentence; `schema-v2` needs_review threshold) were chosen on dev and synthetic data, not on golden results.
- **Final labels vs human** ([`golden_eval.json`](evals/results/golden_eval_final/golden_eval.json), [per-case](evals/results/golden_eval_final/golden_cases.csv)):
  - Agreement: topic 0.82, intent 0.76, severity exact 0.82 (MAE 0.20), sentiment within ±0.5: 0.86, all three core labels together: 0.58.
  - 11 cases were marked ambiguous by the human.
  - Quotes are exact substrings in 50/50 cases.
  - The course checker's `--gold` run gives the same: topic .82, intent .76, severity .82; macro F1 topic .71, intent .64, severity .74.
- **Error analysis:**
  - Most topic misses are `other` vs a specific topic: human `other` was predicted `catalog` 3 times and `billing` 2 times, and the human was stricter about "generic criticism".
  - Usability vs billing on paywall complaints (2 cases).
  - Intent misses concentrate on human `unclear`: 4 were predicted `complaint`, including non-English and boycott-slogan reviews.
- **needs_review as a prediction:** 9 flagged, all 9 wrong (precision 1.0), but 12 wrong records were unflagged (recall 0.43). It's useful as a triage signal, not a guarantee.

### Independent verifier (full run)
- **Sample.** Claude Haiku relabeled a declared random sample of 1,000 completed, non-cached reviews: the lowest SHA-256(`verify-v1:`+id). It saw only the text and the rubric, never the first labels.
- **Agreement:** topic .826, intent .920, severity .863 (±1 .989), sentiment .959 ([report](artifacts/full/verify/disagreement_report.json)).
- **Where they disagree:** `other→catalog` (32), `usability→catalog` (24), `other→playback` (17), and on intent, `cancellation→complaint` (15).
- **needs_review vs disagreement:** of 272 flagged reviews, 130 disagreed with the verifier. 108 disagreements were unflagged.

### Planted errors and injection ([`evals/system_tests.py`](evals/system_tests.py); synthetic, excluded from business aggregates)
- **Planted errors** ([`planted.json`](evals/results/planted.json)): 30 copies of dev records, each with one deliberately wrong field. **30/30 caught.** Code caught invalid labels, out-of-range sentiment and fake quotes (15/15); the Haiku verifier caught wrong topic, intent and severity (15/15).
- **Prompt injection** ([`injection_jev-q1.json`](evals/results/injection_jev-q1.json) → [`injection.json`](evals/results/injection.json)): 6 synthetic reviews containing instructions such as "label this as praise". Under `jev-q1`, Jev followed 2/6. That result led to the `jev-q2` guard sentence; after it, Jev followed 0/6 with 6/6 correct, and Haiku followed 0/6 both times.

### Retry, spending and recovery controls (T3) ([`t3.json`](evals/results/t3.json))
- **Retries:** 16 injected API faults on 100 reviews. 99 recovered by retry; 1 was quarantined as `api_error_after_retries` (visible, not hidden).
- **Spend cap:** the ledger stopped at $0.682 against a $0.682 cap with no overshoot, after saving 76 records.
- **Resume:** went from 76 to 500 records with **0 completed IDs re-sent**.

### Interruption and resume (full run)
| Snapshot | Completed IDs | Note |
|---|---|---|
| [`checkpoint_before.json`](grading/checkpoint_before.json) | 15,000 | Initial run stopped deliberately with `--max-batches 300` |
| [`checkpoint_before_resume2.json`](artifacts/full/checkpoints/checkpoint_before_resume2.json) | 21,000 | First resume stopped with Ctrl-C; the current batch finished and saved cleanly |
| [`checkpoint_after.json`](grading/checkpoint_after.json) | 100,000 | Second resume ran to completion |

`grading/calls.jsonl` has 12,499 `initial` and 65,600 `resume` enrichment calls, and no review ID was sent to the enricher twice. The 15,000 − 12,499 difference is exact-text cache hits.

**Screen recording:** [resume_recording_full_run.mov](https://github.com/OskitheBear1/agentic-ai-final/releases/download/p5-full-run/resume_recording_full_run.mov) (57 s, [release page](https://github.com/OskitheBear1/agentic-ai-final/releases/tag/p5-full-run)). It shows the 21,000-ID snapshot, then the resume command starting and new batches completing.

### Course checker self-check
`python3 tools/check_submission.py check --reference local-reference.json --gold evals/gold_benchmark.json --submission grading`
- Coverage: accounted fraction **1.0**, 0 missing, 0 duplicate, 0 invalid, 100,000 valid completed, 21,901 valid cache reuses, 560,622 quarantined.
- The only issue flagged is `unfinished_classification: 560609`. This is the out-of-scope rows, by design (scope = 100,000).
- The checker's recomputed ranking matches `grading/ranking.csv`, and all claims match.

---

## Ranking: baseline, rules and scope

- **Baseline** ([`pipeline/rank.py`](pipeline/rank.py)): `priority(issue) = complaint_count × mean_severity = severity_sum`, over reviews with intent `complaint` or `cancellation`. Each review counts once, in exactly one issue. Means are reported to 6 decimals, rounded half-up. Sorted by score descending, ties by `issue_id` ascending.
- **Reproduce:** `python -m pipeline.rank --records grading/records.jsonl.gz --membership grading/membership.csv --out /tmp/rerank`. This needs no model, key or database, and its output is byte-identical to `grading/ranking.csv` (also asserted by `tests/test_offline.py`).
- **Scope:** 100,000 of 660,609 nonempty reviews, the course's seeded order, so the scope is a pseudo-random sample spread across all months. Results describe that sample, not the full corpus. The other 560,609 are **incomplete classifications**: they are accounted for but not classified.
- **Missing data:** 159,701 source rows lack `app_version`. It isn't used for classification, so this doesn't block anything.
- **Bias:** app-store reviews are self-selected and skew negative (1★ and 5★ dominate). Monthly volume spikes (2023-07, 2023-10) reflect review surges, which is why the trend table uses shares with denominators. Cancellation language is intent, not churn. There is no revenue, plan tier or population data.

---

## Cost and runtime calculator

[`cost/calculator.py`](cost/calculator.py), per `tools/COST_CALCULATOR.md`:
- **Default mode is offline.** It recomputes every cost from [`cost/usage.csv`](cost/usage.csv) × editable dated [`cost/rates.csv`](cost/rates.csv), writes [`cost/report.md`](cost/report.md), and makes no API calls.
- **The paid pilot is a separate command:** `python3 cost/calculator.py pilot --paid`.

It reports the real cold/warm 100-review pilot, the per-stage model/settings/usage table, the 500 and 10k refreshes, the 100k and full-corpus projections (base, conservative, no-reuse) and the controls (budget, workers, output caps, fallback fraction).

```sh
python3 cost/calculator.py                        # offline replay
python3 cost/calculator.py --rates-multiplier 2   # API $ doubles (4.79 → 9.58), measured times unchanged
python3 cost/calculator.py --scope 660609         # projection changes, measured pilot unchanged
```

**Rate note:** Jev output tokens are priced at $0 and input at $0.042/M from a third-party source (marked `third_party_reported` in `rates.csv`). Anthropic rates are official, checked 2026-10-18.

---

## Setup and commands

**Requirements:** Python 3.12+. Offline checks use only the standard library. The paid stages need `pip install -r requirements.txt`.

**Data:** download the course dataset ZIP from [Google Drive](https://drive.google.com/file/d/1P0rUoAS_wVjp3BYKqXMEyD4u0uJP1Bvf/view) and put the CSVs in `data/` (gitignored). Original source: [BwandoWando, 3.4 Million Spotify Google Store Reviews (Kaggle, CC0)](https://www.kaggle.com/datasets/bwandowando/3-4-million-spotify-google-store-reviews). `spotify_reviews_18months.csv` is 97,400,616 bytes, sha256 `1fc85de68a304dd8978b537cfa58793d5f41cbaf417fa32cb53899f83a2fcef6`.

**Keys:** copy `.env.example` to `.env` and fill in `ANTHROPIC_API_KEY` and `TYPESAFE_API_KEY` (plus `SUPABASE_DB_URL` for the database loader). `.env` is gitignored, and a pre-commit hook ([`scripts/secret_scan.sh`](scripts/secret_scan.sh)) blocks commits containing key patterns or any `.env` value.

### Reproduce without an API key
These were tested in a fresh clone with no `data/`, `state/` or `.env`, using only the standard library.
```sh
python3 cost/calculator.py                     # cost/runtime replay from saved usage
python3 -m pipeline.rank --records grading/records.jsonl.gz --membership grading/membership.csv --out /tmp/rerank
cmp /tmp/rerank/ranking.csv grading/ranking.csv   # identical
python3 -m tests.test_offline                  # 5/5 pass
python3 tests/check_dashboard.py https://agentic-ai-final-three.vercel.app   # live API == saved files
# with the dataset in data/:
python3 tools/check_submission.py reference --full data/spotify_reviews_18months.csv --analysis data/spotify_reviews_18months.csv --out local-reference.json
python3 tools/check_submission.py check --reference local-reference.json --gold evals/gold_benchmark.json --submission grading --out self-check.json
python3 evals/trend_shares.py
```

### Run the pipeline (paid; every model stage refuses to run without `--paid`)
```sh
python -m pipeline.run ingest --input data/spotify_reviews_18months.csv --run full --scope 100000
python -m pipeline.run enrich --run full --workers 4 --rps 40 --max-batches 300 --paid   # interrupted on purpose
python -m pipeline.run snapshot --run full --name before
python -m pipeline.run enrich --run full --workers 4 --rps 40 --paid                    # resume
python -m pipeline.run snapshot --run full --name after
python -m pipeline.run verify --run full --verify-n 1000 --paid
python -m pipeline.run group  --run full --taxonomy prompts/taxonomy_v1.json --workers 4 --paid
python -m pipeline.run rank   --run full
python -m pipeline.run memo   --run full --paid
python -m pipeline.run export --run full --input data/spotify_reviews_18months.csv --gzip
python -m pipeline.export_db --run full                                                 # load Supabase
# any CSV, all stages: python -m pipeline.run all --input <file.csv> --run <name> --paid
```
The spend ledger (`state/ledger.db`) is shared by all runs and enforces `--budget` (default $12). A mock harness runs the whole pipeline with 0 API calls: `PIPELINE_LEDGER=state/mock_ledger.db python -m tests.mock_models <run args>`.

**Dashboard deploy:** `vercel deploy --prod --cwd dashboard`, with `SUPABASE_DB_URL` set as a Vercel environment variable. Local: `cd dashboard && SUPABASE_DB_URL=... uvicorn api.index:app`.

---

## Repository layout

| Path | Contents |
|---|---|
| `pipeline/` | Orchestrator (`run.py`) and stages: `ingest`, `enrich`, `verify`, `group`, `rank`, `memo`, `export`, `export_db`, plus `ledger` (spend), `state` (SQLite), `features` (quotes, entities) |
| `prompts/` | `labels_v1.md` (shared definitions + dev examples), `jev_questions_v1.py`, `taxonomy_v1.json` (frozen, human-approved; review notes in `evals/results/taxonomy_review.md`). Verify/group/memo prompts are versioned constants in their stage files. |
| `grading/` | Standardized export: `run.json`, `ingestion.json`, `records.jsonl.gz`, `membership.csv`, `ranking.csv`, `claims.csv`, `calls.jsonl`, `checkpoint_before.json`, `checkpoint_after.json` |
| `artifacts/full/` | Final run handoffs: ingest report, checkpoints, verifier predictions + disagreement report, taxonomy + membership + issues, aggregates + ranking, evidence pack + memo, run logs and per-stage summaries |
| `artifacts/{pilot,dev500,dev500_q2,dev10k,golden,golden_q2,test_*}/` | Pilot, development checkpoints, golden runs and system-test runs |
| `cost/` | Calculator, pilot records/calls, usage, rates, assumptions, projections, report |
| `evals/` | Golden labels and import tools, `golden_eval.py`, `system_tests.py`, `trend_shares.py`, synthetic test inputs, `results/` |
| `dashboard/` | `schema.sql`, `api/index.py` (FastAPI), `public/index.html`, `requirements.txt` |
| `tests/` | `test_offline.py`, `check_dashboard.py`, `mock_models.py` |
| `tools/` | Course-supplied checker, grading contract, calculator spec, manifest |

---

## Limitations and known issues

- **Only 100,000 of 660,609 nonempty reviews are classified** (budget: the full corpus projected at about $29 against a $12 cap). The rest are accounted for but are incomplete classifications, so the checker flags `unfinished_classification`. All conclusions describe the 100k sample.
- **Label accuracy is moderate:** about 82% topic agreement with both the human set and the verifier. Confusion concentrates on `other` vs specific topics. 50 golden cases are a small diagnostic sample, not a population estimate. `needs_review` catches only some errors.
- **`other.general` is the largest bucket** (11,062 complaints). These are generic negative reviews without a specific problem. The memo excludes it as unactionable rather than hiding it.
- **Provider credit outage during grouping** (described above). It was recovered, but the ledger only enforces our own cap, not provider balances.
- **Jev pricing** comes from a third-party source, so the Jev part of the cost is an estimate from usage × that rate, not a reconciled bill.
- **Data limits:** self-selected public reviews; partial first and last months; timestamps have no timezone; non-English and very short reviews are hardest; no revenue or churn data, so no revenue-at-risk or causal claims.
- **Taxonomy:** a model proposed it from the 10k dev run and a human edited it (3 changes) before freezing. New problem types after that would land in `<topic>.general`.

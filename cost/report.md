# 100-review cost & runtime calculator — report

_Generated offline by `python3 cost/calculator.py` from saved evidence (no API calls). Rates multiplier: **1.0**. Currency: USD._

## 1. Measured pilot (real calls)

- Input: `cost_100.csv` sha256 `c884ac3b9be5066995d5063f96ad9af6e5e082975788c1684c4f6b6ea661dd0e` · 100 rows · 100 distinct texts
- Records: **100 completed**, 0 quarantined/failed · result-cache hits 0
- Cold run (empty result cache, 1 worker): **41.5 s wall-clock**, API **$0.03720** · Warm run (saved cache): **0.19 s**, API $0.00000, **0 new enrichment calls**, 0 downstream calls (verify/group/memo reused by input fingerprint)
- Cost per 1,000 input rows (cold): **$0.3720** · per completed record: $0.000372
- Throughput (cold, enrichment, 1 worker): 8.88 reviews/s · stage seconds: ingest 0.00, enrich 11.26, verify 4.34, group 13.62, rank 0.01, memo 12.24, export 0.01
- Summed call durations are not wall-clock; the wall-clock above is measured end-to-end by the orchestrator.

| run | stage | provider · model | settings | requests | failed | retries | input tok | cache-read | output tok | API $ |
|---|---|---|---|---|---|---|---|---|---|---|
| cold | enrich | typesafe · jev | jev-latest (served jev-1.13.0), no thinking control (fixed-choice model) | 100 | 0 | 0 | 117387 | 0 | 19649 | 0.004930 |
| cold | verify | anthropic · claude-haiku-5-5 | claude-haiku-5-5, thinking disabled, effort low, structured output | 1 | 0 | 0 | 555 | 0 | 721 | 0.000775 |
| cold | group | anthropic · claude-haiku-5-5 | claude-haiku-5-5 taxonomy (thinking disabled) + jev-latest subtopic choice | 1 | 0 | 0 | 2017 | 0 | 1382 | 0.000971 |
| cold | group | typesafe · jev | claude-haiku-5-5 taxonomy (thinking disabled) + jev-latest subtopic choice | 51 | 0 | 0 | 24431 | 0 | 3480 | 0.001026 |
| cold | memo | anthropic · claude-sonnet-5-5 | claude-sonnet-5-5, adaptive thinking, effort low, structured output | 1 | 0 | 0 | 4833 | 0 | 1729 | 0.029496 |
| warm | (all) | — | saved result cache | 0 | 0 | 0 | 0 | 0 | 0 | 0.000000 |

Prompt/schema versions: {"enrich": "jev-q1+schema-v1+quote-v1", "verify": "verify-v1", "group": "group-v1", "memo": "memo-v1"} · enrichment batch size 50 reviews (1 review per Jev request) · workers 1.

Unresolved billing items (no rate): none. Local compute (M2 Pro laptop, electricity) is **unknown, not $0**; no local inference is used. Hosting (Supabase/Vercel free tiers) is outside API spend.

## 2. Rates used (editable: `cost/rates.csv`)

| model | billing item | $ / 1M units (after multiplier) | status | source | checked |
|---|---|---|---|---|---|
| jev | input_tokens | 0.0420 | third_party_reported | [link](https://www.layer3labs.io/guides/jev-pricing) | 2026-10-18 |
| jev | output_tokens | 0.0000 | third_party_reported | [link](https://www.layer3labs.io/guides/jev-pricing) | 2026-10-18 |
| claude-haiku-5-5 | input_tokens | 0.1000 | official | [link](https://platform.claude.com/docs/en/about-claude/pricing) | 2026-10-18 |
| claude-haiku-5-5 | cache_read_input_tokens | 0.0100 | official_assumed_10pct | [link](https://platform.claude.com/docs/en/about-claude/pricing) | 2026-10-18 |
| claude-haiku-5-5 | cache_creation_input_tokens | 0.1250 | official_assumed_125pct | [link](https://platform.claude.com/docs/en/about-claude/pricing) | 2026-10-18 |
| claude-haiku-5-5 | output_tokens | 0.5000 | official | [link](https://platform.claude.com/docs/en/about-claude/pricing) | 2026-10-18 |
| claude-sonnet-5-5 | input_tokens | 2.0000 | official | [link](https://platform.claude.com/docs/en/about-claude/pricing) | 2026-10-18 |
| claude-sonnet-5-5 | cache_read_input_tokens | 0.2000 | official | [link](https://platform.claude.com/docs/en/about-claude/pricing) | 2026-10-18 |
| claude-sonnet-5-5 | cache_creation_input_tokens | 2.5000 | official_assumed_125pct | [link](https://platform.claude.com/docs/en/about-claude/pricing) | 2026-10-18 |
| claude-sonnet-5-5 | output_tokens | 10.0000 | official | [link](https://platform.claude.com/docs/en/about-claude/pricing) | 2026-10-18 |

Formula: `item_cost = billed_units × price_per_unit` (price per 1M ÷ 1,000,000); `total = Σ item_cost`. Input, cache-read, cache-write and output tokens are mutually exclusive in the usage logs. Standard tier only (no Batch API used).

## 3. Full-run projection — 100,000 classified rows

Per-unit inputs (refreshed from dev run 'dev10k' (8448 enrich calls)): Jev 1174 input + 196 output tokens per call; verify $0.000039/review; subtopic assignment $0.000020/complaint text; taxonomy $0.0010 once; memo $0.0295 once; complaint share 0.51. Throughput used: 33.5 reviews/s at 4 workers [measured (4_workers_dev10k)] (measured so far: {'1_worker_pilot': 8.88, '4_workers_dev10k': 33.48}).

| scenario | texts sent | enrich calls | enrich $ | fallback $ | verify $ | group $ | memo $ | **API total $** | est. hours | budget |
|---|---|---|---|---|---|---|---|---|---|---|
| base (exact-text reuse) | 78,099 | 79,270 | 3.91 | 0.00 | 0.039 | 0.81 | 0.031 | **4.79** | 1.02 | ok |
| conservative (reuse) | 78,099 | 83,566 | 4.12 | 0.16 | 0.041 | 0.84 | 0.035 | **5.20** | 1.06 | ok |
| base, no reuse | 100,000 | 101,500 | 5.01 | 0.00 | 0.039 | 1.04 | 0.031 | **6.11** | 1.30 | ok |
| reference: full corpus 660,609, reuse (484,189 texts) | 484,189 | 491,452 | 24.24 | 0.00 | 0.039 | 5.02 | 0.031 | **29.32** | 6.16 | **EXCEEDS BUDGET** |

Fallback $ is declared headroom for a capped stronger-model re-label (max_fallback_fraction); the current pipeline quarantines instead of escalating, so measured fallback spend is $0.

All 660,622 source rows are accounted for: 100,000 classified, 13 empty-text quarantines, and the remaining 560,609 quarantined as `outside_declared_classification_scope`. Fixed overhead (taxonomy, memo, ingest) is added once, not per review.

## 4. Controls (editable: `cost/assumptions.json`)

- `budget_usd` = 12.0
- `max_workers` = 4
- `rps_cap` = 40
- `output_token_cap_verify_per_review` = 60
- `output_token_cap_memo` = 4000
- `max_fallback_fraction` = 0.02
- `invalid_output_retries` = 1
- `transient_api_retries` = 2

- Scaling decision: Scope fixed at 100,000 classified rows (course minimum). Jev enrichment with exact-text reuse; 1 worker for the pilot, chosen concurrency set after measuring 2-4 workers on the 500/10k dev runs. The ledger hard-stops new calls at the budget cap.

## 5. How to recheck

```sh
python3 cost/calculator.py                        # offline replay (default)
python3 cost/calculator.py --rates-multiplier 2   # API subtotal doubles; times unchanged
python3 cost/calculator.py --scope 660609         # projection changes; measured pilot unchanged
```


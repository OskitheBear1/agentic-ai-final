# Issue taxonomy review (human-in-the-loop), 2026-10-18

The source is `artifacts/dev10k/group/taxonomy.json`. Claude Haiku 5.5 proposed it from a bounded pack of up to 30 complaint quotes per topic in the 10k development set.
The student approved the frozen version, `prompts/taxonomy_v1.json`, which is used with `--taxonomy` in the final 100k run.

| Edit | Reason |
|---|---|
| `usability.skip_and_playback_control_limits` renamed to `usability.playback_controls_and_queue` | It overlapped `billing.basic_features_behind_premium`, and the grading contract puts explicitly Premium-only controls under billing. The usability bucket now covers control problems that are *not* described as Premium-only. |
| Removed `other.general_dissatisfaction` | It duplicated the code-added `other.general` catch-all. |
| Added `billing.price_and_value` | "Too expensive" and price-increase complaints had no specific home. |

The golden-50 labels were not used to design or edit the taxonomy.

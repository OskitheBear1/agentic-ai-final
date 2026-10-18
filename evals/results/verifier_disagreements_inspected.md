# Verifier disagreements: inspected sample (full run)

**Sample:** 20 of the 333 reviews where the Haiku verifier disagreed with the Jev enricher on topic, intent or severity
(out of 1,000 verified). They were chosen deterministically, lowest SHA-256(`inspect-v1:`+review_id); the source is
`artifacts/full/verify/verifier_predictions.jsonl`.

**Who judged:** the developer's AI coding assistant (Claude), applying `prompts/labels_v1.md` and
`tools/GRADING_CONTRACT.md`. This was **not** a human review. Treat the verdicts as a structured second opinion.

| # | review (start) | enricher t/i/s | verifier t/i/s | closer to contract | note |
|---|---|---|---|---|---|
| 1 | Could improve the random play list | usability/request/1 | catalog/request/1 | ambiguous | shuffle control (usability) vs recommendations (catalog) |
| 2 | very good app… you do have to pay for no ads but it's very much worth it | billing/praise/1 | usability/praise/1 | ambiguous | praised feature is ad-free Premium: billing entitlement or ads |
| 3 | They are forcing us to buy premium | billing/complaint/2 | billing/complaint/3 | enricher | no restricted function named, so generic criticism = 2 |
| 4 | …play my liked songs it randomly shuffle… | usability/complaint/3 | usability/complaint/2 | enricher | "shuffle forced" is the contract's severity-3 example |
| 5 | Uninstalled after new update | other/cancellation/4 | other/cancellation/2 | verifier | no blocked task described; cancellation does not raise severity |
| 6 | press on one of your playlists it just plays random songs | usability/complaint/3 | usability/complaint/2 | enricher | forced shuffle = 3 |
| 7 | If I can't turn of shuffle… GUYS JUST USE Y… | usability/cancellation/3 | usability/complaint/3 | ambiguous | text cut off; telling others to switch, not clearly leaving |
| 8 | What happened to the widget? | other/unclear/1 | usability/unclear/1 | verifier | about a UI element |
| 9 | Full of bugs, switching from mobile to TV… offline mode… | usability/complaint/4 | playback/complaint/3 | verifier (topic) | device switching is a playback topic; severity ambiguous |
| 10 | restricts the basic features of a music app | billing/complaint/3 | usability/complaint/3 | enricher | paywall restriction is billing per the contract |
| 11 | Doesn't work | other/complaint/4 | playback/complaint/4 | ambiguous | no detail; severity 4 is generous for either |
| 12 | Wouldn't let me play the song I wanted | playback/complaint/3 | playback/complaint/4 | enricher | restricted, not fully blocked |
| 13 | Not downloading | downloads/complaint/4 | downloads/complaint/3 | ambiguous | blocked download vs degraded |
| 14 | 30 minutes of free listening for watching an ad | billing/praise/1 | usability/praise/1 | ambiguous | ads vs plan terms |
| 15 | Fraud app ever… Never come Cash back offers | billing/complaint/2 | billing/complaint/3 | enricher | "fraud" rhetoric alone does not raise severity |
| 16 | Thx for muoc | other/praise/1 | other/unclear/1 | enricher | reads as thanks for music |
| 17 | offline mode keep the app on force closing… | playback/complaint/4 | playback/complaint/3 | ambiguous | repeated crash while playing: 3 or 4 |
| 18 | Cost reduction has downgraded this… | billing/complaint/2 | other/complaint/2 | verifier | generic decline; no price/charge/paywall |
| 19 | …Unstall… Adds + Not Skippable… 10 Sec ka Ganna Free… | billing/cancellation/2 | usability/cancellation/2 | enricher | the most severe specific problem is the paywall (10 s free) |
| 20 | Just bought a premium… add free as well higher quality | usability/praise/1 | billing/praise/1 | verifier | praise for Premium entitlement |

**Tally:** enricher closer 8, verifier closer 5, ambiguous 7.

**Patterns:**
1. **Billing vs usability around ads and Premium** (2, 10, 14, 19, 20) is the main topic boundary problem. It matters for the
   recommended issue: some "basic features behind Premium" members could arguably be usability, and the reverse.
2. **Severity on short or generic reviews** (5, 11, 13, 17): the enricher sometimes inflates severity (e.g. 4 for "Uninstalled
   after new update").
3. **Many disagreements are genuinely ambiguous** under the contract, so the 82.6% topic agreement understates how often
   either label is acceptable. It is not proof that either model is wrong.

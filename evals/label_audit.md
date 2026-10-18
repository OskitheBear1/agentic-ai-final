# Golden-set label audit (v1 → v2)

**Why:** an external review found human labels that break the shared rules (praise/unclear rated severity 2; requests that report a failure). **Selection:** a code rule check over all 50 labels (intent praise/unclear or request with severity ≠ 1) found 15 cases. Model predictions were **not** shown during the audit. **Decisions:** the student, using `prompts/labels_v1.md`. The audit was prompted by reviewing disagreements, so v2 is not independent of the pipeline's results; both versions are reported.

**15 label changes across 15 reviews.** The v1 files are unchanged.

| review (start) | field | v1 → v2 | rule |
|---|---|---|---|
| Ads were okay, but limited functionality..it's just too much | severity | 2 → 1 | Intent is praise/unclear, but the severity rule says praise and unclear content = 1. |
| Duo Premium .... No ads at all! | severity | 2 → 1 | Intent is praise/unclear, but the severity rule says praise and unclear content = 1. |
| Update: I reached out to Spotify Support and with some help  | severity | 2 → 1 | Intent is praise/unclear, but the severity rule says praise and unclear content = 1. |
| Lhat ng song nasa spotify | severity | 2 → 1 | Intent is praise/unclear, but the severity rule says praise and unclear content = 1. |
| Avtar sungh | severity | 2 → 1 | Intent is praise/unclear, but the severity rule says praise and unclear content = 1. |
| asem, lirik nya kdang gaada kek mana?? | severity | 2 → 1 | Intent is praise/unclear, but the severity rule says praise and unclear content = 1. |
| We are boycotting Swedish app in our protest against Sweden  | severity | 2 → 1 | Intent is praise/unclear, but the severity rule says praise and unclear content = 1. |
| Please ye ads ko thoda kumm Karo harr ek song ke baad ad 🙏🙄 | severity | 2 → 1 | Intent is praise/unclear, but the severity rule says praise and unclear content = 1. |
| Bheekhmangon | severity | 2 → 1 | Intent is praise/unclear, but the severity rule says praise and unclear content = 1. |
| Unconditional love, Stoli Canales | severity | 2 → 1 | Intent is praise/unclear, but the severity rule says praise and unclear content = 1. |
| I hate this app and sweden .I love islam | severity | 2 → 1 | Intent is praise/unclear, but the severity rule says praise and unclear content = 1. |
| Beth, we all got to give me a free dollar to go with 3 month | severity | 2 → 1 | Intent is praise/unclear, but the severity rule says praise and unclear content = 1. |
| Are you out of your mind? This is dangerous! Listening to mu | severity | 3 → 1 | Intent is request, but request = asks for a change WITHOUT reporting a failure (severity 1). If it reports a failure, intent should be complaint. topic kept as usability (student, 2026-10-18); display column restored after a spreadsheet fill-down accident |
| 1-Lyrics not getting loaded, 2-can't go back to or start son | severity | 3 → 1 | Intent is request, but request = asks for a change WITHOUT reporting a failure (severity 1). If it reports a failure, intent should be complaint. |
| paying for subscribing but unable to play in offline mode re | severity | 3 → 1 | Intent is request, but request = asks for a change WITHOUT reporting a failure (severity 1). If it reports a failure, intent should be complaint. |

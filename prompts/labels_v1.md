# Label definitions — `labels_v1`

These definitions are shared by every model role (Jev enricher, Haiku verifier, subtopic assignment)
and by the human golden-set labeler. They follow `tools/GRADING_CONTRACT.md` exactly; examples below
come from the **development** files only (`analysis_10000.csv`), never from the golden 50.

Classify the **review text only**. Star rating, likes, app version and date are metadata for later
analysis and are never shown to a classifier.

## Topic (exactly one)

| topic | Use for | Not for |
|---|---|---|
| `access` | Login, signup, password, account access, being logged out, account hacked/locked | Paying for an account (billing) |
| `usability` | Navigation, controls, layout, shuffle/queue/playlist management, UI changes, **ad interruptions / too many ads** | Controls that are explicitly locked behind Premium (billing) |
| `playback` | Songs won't play, stops/pauses, crashes, lag, "no internet connection" errors, audio quality, battery/data/storage use | Offline/downloaded music (downloads) |
| `downloads` | Downloading, saved/offline music, downloads disappearing, offline mode | |
| `catalog` | Missing/removed songs or artists, search, discovery, recommendations, lyrics availability, podcasts/content choices | Lyrics locked behind Premium (billing) |
| `billing` | Price, charges, refunds, subscriptions, trials, paywalls, Premium entitlement not working, **features explicitly restricted to Premium** (skips limit, can't pick a song, lyrics/queue "premium only") | Merely mentioning that one has Premium |
| `support` | Contacting customer support and the response | |
| `other` | General praise or criticism with no specific feature, unrelated content, politics/boycott, meaningless text | |

Rules:
- Pick the problem with the **highest supported severity**; on a tie, the **first specific problem mentioned**.
- Positive review: the first specific praised feature; general praise ("great app", "love it") → `other`.
- A paid-plan mention alone is not `billing`. A subscription failing to activate is `billing`. Music crashing for a paying customer is `playback`.

## Intent (precedence: first that applies wins)

1. `cancellation` — explicitly leaving, uninstalling, cancelling, switching to a competitor, or threatening to.
2. `complaint` — any negative experience, including mixed praise + criticism. Generic "bad app" is a complaint.
3. `request` — asks for a change/feature without reporting a failure.
4. `praise` — positive only.
5. `unclear` — meaningless, unrelated, unsupported language, or a bare boycott slogan with no product complaint or personal departure.

## Severity (1–5)

| severity | Meaning |
|---|---|
| 1 | No reported problem: praise, neutral/unclear content, or a pure feature request |
| 2 | Dislike, generic criticism, minor annoyance, cosmetic issue — no supported functional loss (e.g., "too many ads", "bad app") |
| 3 | A degraded or restricted function; some use or workaround remains (e.g., only 6 skips, lyrics not loading, shuffle forced) |
| 4 | A clearly blocked core task (can't log in, can't play anything, downloads all gone) |
| 5 | Explicit serious financial, privacy or data harm (charged without consent, account hacked and charged, data loss of paid content). An expensive plan, a crash, or angry language alone is insufficient |

Cancellation intent does not raise severity by itself. If impact is unclear, choose the lower supported level and set `needs_review`.

## Sentiment

Number in [-1, 1]: -1 very negative, -0.5 negative, 0 neutral/mixed, 0.5 positive, 1 very positive.
Evaluation tolerance: |predicted − human| ≤ 0.5 counts as agreement; mean absolute error is also reported.

## Other fields

- `evidence_quote`: an **exact substring** of the review text that supports the topic/intent (code verifies membership).
- `entities`: product features explicitly named in the text (e.g., `ads`, `shuffle`, `lyrics`, `premium`, `offline`), from a fixed keyword list matched by code.
- `needs_review`: true when the classifier's confidence is low or the text is ambiguous/unsupported-language.

## Worked examples (development set)

| Review (abridged) | topic | intent | sev | why |
|---|---|---|---|---|
| "I love the mixes" | catalog | praise | 1 | first specific praised feature = recommendations/mixes |
| "Its very amazing" | other | praise | 1 | general praise |
| "Hateful app Waste of time" | other | complaint | 2 | generic criticism, no specific defect |
| "Too much adds" | usability | complaint | 2 | ad interruptions, annoyance |
| "Listen to my music almost everyday, this app is great. But … too many ads" | usability | complaint | 2 | mixed → complaint |
| "Why are lyrics premium!? … 1 star from me" | billing | complaint | 3 | feature explicitly premium-only, restricted function |
| "Nice app but why can't the lyrics of song on my playlist load?" | catalog | complaint | 3 | lyrics availability degraded |
| "I paid my subscription and im still getting a pause subscription screen and can't access my music" | billing | complaint | 4 | entitlement failure blocks core task |
| "The very second I signed up for premium it stopped letting me play anything… Fastest cancelation… Bye bye Spotify" | billing | cancellation | 4 | premium entitlement failure blocks playback; explicit departure |
| "Always say no internet connection. Most of my favourite Bollywood songs are not present" | playback | complaint | 4 | can't play (highest severity) beats missing songs |
| "offline mode USELESS, and moving storage failed and deleted everything" | downloads | complaint | 4 | downloads deleted |
| "Just need the download button on mobile to show for ever song" | downloads | request | 1 | pure feature request |
| "Could be doing with hi-res audio…" | playback | complaint | 2 | mixed: wish + mild annoyance at recommendations |
| "Great place for music. Bad for smaller artists and a platform for [podcasters] to spread their stupidity" | catalog | complaint | 2 | content choices, no functional loss |
| "Shame on you 😡😡" | other | unclear | 1 | no product complaint stated |
| "Thik thak hi hai" (Hindi: "it's okay") | other | praise | 1 | mild positive; non-English → needs_review |

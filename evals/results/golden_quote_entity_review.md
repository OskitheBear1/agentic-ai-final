# Golden 50: evidence-quote support and entity review

Source: `evals/results/golden_eval_final/golden_cases.csv` (final labels vs human labels). Inspected by the developer's
AI coding assistant (Claude) against `prompts/labels_v1.md`; not a human review.

## Evidence quotes

- **50/50 quotes are exact substrings** (checked in code). **47/50 are the whole review**, because `quote-v1` uses the full
  text for reviews of 200 characters or less. For those 47, "the quote supports the label" reduces to "the label fits the
  review", which the agreement numbers already measure. The substring check is trivially satisfied for them.
- **The 3 reviews where code picked one sentence:**

| review (start) | final label | quote | supports the label? |
|---|---|---|---|
| Update: I reached out to Spotify Support and with some help… Old Post: … keeps crashing | playback/complaint | "I tried to open it today, and it keeps crashing every time." | **Partly.** It supports a playback problem, but it comes from the *old* post; the update says support resolved it (human: support/unclear). The sentence picker ignores "Update:" context. |
| Deleting this App. The new update suck… pushing us to upgrade to Premium | billing/cancellation | "They are pushing us to upgrade to Premium subscription." | **Topic yes, intent no.** The cancellation evidence ("Deleting this App") is in a different sentence. |
| What is happening with Spotify?? Recently I'm trying to play a song but it doesn't working… | playback/complaint | "What is happening with Spotify??" | **No.** No sentence matched a playback keyword, so the picker fell back to the first sentence. |

**Takeaway:** for long reviews, the keyword-scored sentence picker can return a sentence that doesn't carry the label
(1 of 3 clearly unsupported, 2 partly). Quotes for short reviews are reliable but uninformative as a check.

## Entities (32 predicted, not in the human list)

Entities come from a keyword lexicon (`pipeline/features.py`), so every predicted entity matches words that are in the
review. None are invented. The 32 differences break down as:

| entity | count | assessment |
|---|---|---|
| ads | 8 | mentioned in the text; the human listed fewer entities (e.g. "No ads at all!") |
| update | 7 | mostly relevant ("new update"); at least 1 wrong sense ("I updated my phone") |
| premium, subscription, price | 7 | mentioned; relevant to billing/paywall reviews |
| playlist, recommendations, shuffle, lyrics, artists, offline, audio_quality | 8 | mentioned and on topic |
| crash, support | 2 | from the resolved "Old Post" review above; mentioned but describe a past state |

**Takeaway:** most "unsupported" entities are real mentions that the human simply didn't list. The real error mode is
word-sense or context (an "update" of the phone, a crash that was later fixed), not hallucination.

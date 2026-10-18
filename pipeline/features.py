"""Deterministic (code-only) enrichment fields: evidence quote and entities. Version quote-v1."""

import re

FEATURE_VERSION = "quote-v1"
SHORT_REVIEW_CHARS = 240  # at or below this length the whole (stripped) review is the evidence quote

# entity name -> regex (case-insensitive). Matched entities are reported only if literally present.
ENTITY_PATTERNS = {
    "ads": r"\bad(s|vert\w*|vertis\w*)?\b|\badds\b|commercial",
    "premium": r"premium|prem\b",
    "shuffle": r"shuffl",
    "skips": r"\bskip",
    "queue": r"\bqueue",
    "playlist": r"playlist",
    "lyrics": r"lyric",
    "downloads": r"download",
    "offline": r"offline",
    "login": r"log ?in\b|sign ?in|password|logged out|log out",
    "account": r"\baccount",
    "podcasts": r"podcast",
    "price": r"price|expensive|\bcost|money|\bcharg|refund|\bpay",
    "subscription": r"subscri|\btrial",
    "update": r"\bupdat",
    "crash": r"crash|freez|hang",
    "search": r"\bsearch",
    "recommendations": r"recommend|algorithm|discover|\bmix",
    "support": r"customer (service|support)|\bsupport\b|contact",
    "audio_quality": r"sound quality|audio quality|\bvolume|\bbass|hi-?fi|hi-?res",
    "connection": r"internet|connection|network|\bwifi|\bwi-fi",
    "battery": r"battery",
    "car_bluetooth": r"bluetooth|android auto|\bcar\b",
    "artists": r"\bartist",
}
_COMPILED = {k: re.compile(v, re.I) for k, v in ENTITY_PATTERNS.items()}

TOPIC_ENTITIES = {
    "access": ["login", "account"],
    "usability": ["ads", "shuffle", "queue", "playlist", "update", "skips"],
    "playback": ["crash", "connection", "audio_quality", "battery", "car_bluetooth"],
    "downloads": ["downloads", "offline"],
    "catalog": ["lyrics", "search", "recommendations", "podcasts", "artists"],
    "billing": ["premium", "price", "subscription", "skips", "lyrics"],
    "support": ["support"],
    "other": [],
}

_SENTENCE = re.compile(r"[^.!?\n]+[.!?]*")


def entities(text):
    return [name for name, rx in _COMPILED.items() if rx.search(text)]


def evidence_quote(text, topic):
    """Return an exact substring of `text` that supports the topic (code-verified membership)."""
    stripped = text.strip()
    if len(stripped) <= SHORT_REVIEW_CHARS:
        return stripped
    wanted = [_COMPILED[e] for e in TOPIC_ENTITIES.get(topic, [])]
    best, best_score = None, -1
    for m in _SENTENCE.finditer(text):
        s = m.group(0).strip()
        if len(s) < 3:
            continue
        score = sum(bool(rx.search(s)) for rx in wanted)
        if score > best_score:
            best, best_score = s, score
    quote = best or stripped[:SHORT_REVIEW_CHARS].strip()
    assert quote and quote in text
    return quote

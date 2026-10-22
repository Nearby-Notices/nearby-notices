"""How far a search has got, so the page can show a real progress bar while the request is still running.

A search is one request that can take 5 to 20 seconds on a new place: find the place, ask the Gazette in each
category, fetch the full text of short notices, then check where each notice is filed. search.find reports each
step here; the page polls /progress while it waits. Entries are keyed by a hash of the place, never the words
typed, live only in memory, and are dropped two minutes after their last step.
"""
from __future__ import annotations

import hashlib
import threading
import time

TTL = 120  # seconds an entry is kept after its last step

# Each stage owns a slice of the bar; its own count fills the slice. "done" is the page being built.
STAGES = {"place": (0, 5), "feed": (5, 45), "text": (45, 45), "points": (45, 95), "done": (100, 100)}
LABELS = {
    "place": "Finding the place",
    "feed": "Searching The Gazette: {done} of {total} kinds of notice",
    "text": "Fetching notices: {done} of {total}",
    "points": "Checking where each notice is: {done} of {total}",
    "done": "Preparing your results",
}

_lock = threading.Lock()
_entries: dict[str, dict] = {}


def key(place: str) -> str:
    """The same key for the same place however it was typed; the words themselves are not kept."""
    return hashlib.sha256(" ".join(place.lower().split()).encode()).hexdigest()[:32]


def percent(stage: str, done: int = 0, total: int = 0) -> int:
    lo, hi = STAGES[stage]
    share = done / total if total else 0
    return round(lo + (hi - lo) * min(max(share, 0), 1))


def step(k: str, stage: str, done: int = 0, total: int = 0) -> None:
    now = time.monotonic()
    with _lock:
        _entries[k] = {"stage": stage, "done": done, "total": total, "percent": percent(stage, done, total),
                       "label": LABELS[stage].format(done=done, total=total), "at": now}
        for old in [x for x, e in _entries.items() if now - e["at"] > TTL]:
            del _entries[old]


def get(k: str) -> dict | None:
    with _lock:
        e = _entries.get(k)
        if e is None or time.monotonic() - e["at"] > TTL:
            return None
        return {x: e[x] for x in ("stage", "done", "total", "percent", "label")}


def clear(place: str) -> None:
    """Forget a search once its page is built, so a repeat search of the same place starts its bar from zero."""
    with _lock:
        _entries.pop(key(place), None)


def reporter(place: str):
    """A step function bound to one search, for search.find."""
    k = key(place)
    return lambda stage, done=0, total=0: step(k, stage, done, total)

"""A per-minute limit per client that keeps no addresses.

The privacy page promises that no IP address is stored or logged. So the counter is keyed by a salted hash of the
address, the salt is random per process and never written anywhere, the map lives in memory only, and every entry
is forgotten a minute after its last request. There is nothing to read back and nothing to subpoena.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time

_SALT = os.urandom(16)
_lock = threading.Lock()
_hits: dict[str, list[float]] = {}
WINDOW_S = 60.0


def _key(address: str) -> str:
    return hashlib.sha256(_SALT + address.encode("utf-8", "replace")).hexdigest()[:24]


def allow(address: str, limit: int, now: float | None = None) -> bool:
    """True if this client has made fewer than `limit` requests in the last minute; records the request either way."""
    now = time.monotonic() if now is None else now
    k = _key(address or "unknown")
    with _lock:
        recent = [t for t in _hits.get(k, []) if now - t < WINDOW_S]
        ok = len(recent) < limit
        recent.append(now)
        _hits[k] = recent
        if len(_hits) > 5000:        # forget anything idle; the map never grows without bound
            for key in [key for key, ts in _hits.items() if not ts or now - ts[-1] >= WINDOW_S]:
                del _hits[key]
    return ok

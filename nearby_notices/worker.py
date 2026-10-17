"""One background thread reads notices through the model, one at a time, so a search page can return at once
and the local model is never hit by a burst. The page shows "reading" for notices still in the queue."""
from __future__ import annotations

import queue
import threading

from . import config, extract, store

_q: queue.Queue[str] = queue.Queue()
_pending: set[str] = set()
_lock = threading.Lock()
_thread: threading.Thread | None = None


def _run() -> None:
    while True:
        nid = _q.get()
        try:
            with store.db() as con:       # a short read, then the connection is released before the model is called
                row = None if store.get_extraction(con, nid, config.MODEL) is not None else store.get_notice(con, nid)
            if row:
                r = extract.extract(row["text"])
                with store.db() as con:
                    store.put_extraction(con, nid, config.MODEL, r.to_dict(), len(r.summary), len(r.removed), r.seconds)
        except Exception as e:  # noqa: BLE001 the worker must survive any single failure; the page shows "reading" until retried
            with store.db() as con:
                store.put_extraction(con, nid, config.MODEL, {"error": f"model unavailable: {type(e).__name__}", "summary": [], "removed": [],
                                                              "places": [], "dropped_places": []}, 0, 0, 0.0)
        finally:
            with _lock:
                _pending.discard(nid)
            _q.task_done()


def start() -> None:
    global _thread
    config.discover_model()
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_run, name="notice-reader", daemon=True)
        _thread.start()


def enqueue(ids: list[str]) -> None:
    start()
    with _lock:
        for nid in ids:
            if nid not in _pending:
                _pending.add(nid)
                _q.put(nid)


def warm_up(limit: int = 60) -> int:
    """At startup, queue the notices of every cached search that lack a plain-English version under the current
    model, so a restart (or a model change) never leaves a page of "reading..." for a place someone has searched."""
    import json

    ids: list[str] = []
    with store.db() as con:
        for row in con.execute("SELECT payload FROM feed_cache ORDER BY fetched_at DESC"):
            for nid in json.loads(row["payload"]):
                if nid not in ids and store.get_extraction(con, nid, config.MODEL) is None and store.get_notice(con, nid):
                    ids.append(nid)
                if len(ids) >= limit:
                    break
            if len(ids) >= limit:
                break
    enqueue(ids)
    return len(ids)


def is_pending(nid: str) -> bool:
    with _lock:
        return nid in _pending

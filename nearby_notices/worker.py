"""Background writers that make each notice's simple summary, several side by side, so a search page returns at
once and the cards fill in as summaries are ready. Summaries are written on demand, in order of need: a notice
on someone's screen (or whose pin was opened) first, then the first few of a new search, then warm-up work.
Each summary is written once, kept, and shown to everyone after, so nothing is paid for twice."""
from __future__ import annotations

import itertools
import queue
import threading

from . import config, extract, search, store

NOW, SOON, LATER = 0, 1, 2          # on screen; first few of a search; warm-up after a restart

_q: queue.PriorityQueue[tuple[int, int, str]] = queue.PriorityQueue()
_order = itertools.count()           # first come, first served within a priority
_pending: dict[str, int] = {}        # notice id -> the most urgent priority it has been queued at
_lock = threading.Lock()
_threads: list[threading.Thread] = []


def _run() -> None:
    while True:
        _, _, nid = _q.get()
        try:
            with store.db() as con:       # a short read, then the connection is released before the model is called
                row = None if store.get_extraction(con, nid, config.MODEL) is not None else store.get_notice(con, nid)
            if row:
                r = extract.extract(search.full_text_for(row))     # the full text, fetched now if the feed held a summary
                with store.db() as con:
                    store.put_extraction(con, nid, config.MODEL, r.to_dict(), len(r.summary), len(r.removed), r.seconds)
        except Exception as e:  # noqa: BLE001 the worker must survive any single failure; the page shows "reading" until retried
            with store.db() as con:
                store.put_extraction(con, nid, config.MODEL, {"error": f"model unavailable: {type(e).__name__}", "summary": [], "removed": [],
                                                              "places": [], "dropped_places": []}, 0, 0, 0.0)
        finally:
            with _lock:
                _pending.pop(nid, None)
            _q.task_done()


def start() -> None:
    config.discover_model()
    with _lock:
        _threads[:] = [t for t in _threads if t.is_alive()]
        while len(_threads) < max(1, config.READERS):
            t = threading.Thread(target=_run, name=f"summary-writer-{len(_threads) + 1}", daemon=True)
            t.start()
            _threads.append(t)


def enqueue(ids: list[str], priority: int = SOON) -> None:
    """Queue notices for a summary. A notice already queued is moved up if it is now needed sooner; a notice
    that is queued twice is written once (the writer skips one that already has a summary)."""
    start()
    with _lock:
        for nid in ids:
            if nid not in _pending or priority < _pending[nid]:
                _pending[nid] = priority
                _q.put((priority, next(_order), nid))


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
    enqueue(ids, LATER)
    return len(ids)


def is_pending(nid: str) -> bool:
    with _lock:
        return nid in _pending

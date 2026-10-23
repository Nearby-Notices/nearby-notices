"""SQLite cache and counters. Stores notices (public record), extractions, and anonymous feedback counts.

It never stores what a user typed, and it refuses any notice outside the allowed categories.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import time
from contextlib import contextmanager

from . import config
from .categories import is_allowed

SCHEMA = """
CREATE TABLE IF NOT EXISTS notices (
  id TEXT PRIMARY KEY, title TEXT, category TEXT, notice_code INTEGER, published TEXT,
  text TEXT, url TEXT, fetched_at REAL, lat REAL, lon REAL, points TEXT);
CREATE TABLE IF NOT EXISTS extractions (
  notice_id TEXT PRIMARY KEY, model TEXT, payload TEXT, kept INTEGER, removed INTEGER,
  seconds REAL, created_at REAL);
CREATE TABLE IF NOT EXISTS feed_cache (key TEXT PRIMARY KEY, payload TEXT, fetched_at REAL);
CREATE TABLE IF NOT EXISTS feedback (notice_id TEXT, up INTEGER DEFAULT 0, down INTEGER DEFAULT 0, PRIMARY KEY (notice_id));
CREATE TABLE IF NOT EXISTS counters (day TEXT, name TEXT, n INTEGER DEFAULT 0, PRIMARY KEY (day, name));
CREATE TABLE IF NOT EXISTS kind_checks (at REAL, notice_id TEXT, model_kind TEXT, llm_kind TEXT, agree INTEGER);
"""


@contextmanager
def db():
    """A connection in WAL mode with a generous busy timeout: the web requests, the background reader and the MCP
    server all write to this file, and readers must never block on a writer. Keep network and model calls OUTSIDE
    the block; a transaction held across a 30 s model call is how "database is locked" happens."""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        # WAL needs shared memory, which a network file share (Azure Files) cannot give; there, NN_DB_JOURNAL=DELETE.
        con.execute(f"PRAGMA journal_mode={config.DB_JOURNAL}")
        con.execute("PRAGMA busy_timeout=30000")
        con.executescript(SCHEMA)
        _migrate(con)
        yield con
        con.commit()
    finally:
        con.close()


def _migrate(con: sqlite3.Connection) -> None:
    """Databases made before 17/10/2026 lack the coordinate columns; add them and forget cached feeds so notices refetch with them."""
    cols = {r["name"] for r in con.execute("PRAGMA table_info(notices)")}
    if "lat" not in cols:
        con.execute("ALTER TABLE notices ADD COLUMN lat REAL")
        con.execute("ALTER TABLE notices ADD COLUMN lon REAL")
        con.execute("DELETE FROM feed_cache")
    if "points" not in cols:
        con.execute("ALTER TABLE notices ADD COLUMN points TEXT")
        con.execute("DELETE FROM feed_cache")
    # Before 19/10/2026 the feed cache was keyed on the searched postcode. Keys are now one-way codes; drop any old ones.
    con.execute("DELETE FROM feed_cache WHERE key NOT LIKE 'h:%'")


def put_notice(con: sqlite3.Connection, n) -> None:
    if not is_allowed(n.notice_code):
        raise ValueError(f"refused: notice code {n.notice_code} is outside the allowed categories")
    con.execute(
        "INSERT OR REPLACE INTO notices VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (n.id, n.title, n.category, n.notice_code, n.published, n.text, n.url, time.time(), n.lat, n.lon,
         json.dumps(n.points) if n.points else None),
    )


def put_text(con: sqlite3.Connection, nid: str, text: str) -> None:
    con.execute("UPDATE notices SET text=? WHERE id=?", (text, nid))


def put_points(con: sqlite3.Connection, nid: str, points: list[dict]) -> None:
    con.execute("UPDATE notices SET points=? WHERE id=?", (json.dumps(points), nid))


def get_notice(con: sqlite3.Connection, nid: str) -> dict | None:
    row = con.execute("SELECT * FROM notices WHERE id=?", (nid,)).fetchone()
    if not row:
        return None
    d = dict(row)
    d["points"] = json.loads(d["points"]) if d.get("points") else []
    return d


RETRY_FAILED_AFTER_S = 600   # a summary that failed because the model was busy or down is tried again after this


def get_extraction(con: sqlite3.Connection, nid: str, model: str) -> dict | None:
    """The stored summary, or None if there is none yet. A summary that failed because the model service was busy
    or unavailable counts as none once it is ten minutes old, so it is written again the next time it is needed."""
    row = con.execute("SELECT * FROM extractions WHERE notice_id=? AND model=?", (nid, model)).fetchone()
    if not row:
        return None
    payload = json.loads(row["payload"])
    if str(payload.get("error") or "").startswith("model unavailable") and time.time() - (row["created_at"] or 0) > RETRY_FAILED_AFTER_S:
        return None
    return payload


def put_extraction(con: sqlite3.Connection, nid: str, model: str, payload: dict, kept: int, removed: int, seconds: float) -> None:
    con.execute(
        "INSERT OR REPLACE INTO extractions VALUES (?,?,?,?,?,?,?)",
        (nid, model, json.dumps(payload), kept, removed, seconds, time.time()),
    )


_KEY_SALT = os.urandom(32)   # new on every start: a key cannot be turned back into a postcode, even with the database


def feed_key(postcode: str, radius: int, since_days: int | None = None) -> str:
    """The cache key for a feed lookup: a keyed one-way code of the postcode, never the postcode itself."""
    code = hmac.new(_KEY_SALT, (postcode or "").upper().replace(" ", "").encode(), hashlib.sha256).hexdigest()[:32]
    return f"h:{code}|g{radius}" + (f"|d{since_days}" if since_days else "")


def cached_feed(con: sqlite3.Connection, key: str) -> list | None:
    row = con.execute("SELECT payload, fetched_at FROM feed_cache WHERE key=?", (key,)).fetchone()
    if row and time.time() - row["fetched_at"] < config.FEED_CACHE_SECONDS:
        return json.loads(row["payload"])
    return None


def put_feed(con: sqlite3.Connection, key: str, ids: list[str]) -> None:
    now = time.time()
    con.execute("DELETE FROM feed_cache WHERE fetched_at < ?", (now - config.FEED_CACHE_SECONDS,))
    con.execute("INSERT OR REPLACE INTO feed_cache VALUES (?,?,?)", (key, json.dumps(ids), now))


def bump(con: sqlite3.Connection, name: str) -> int:
    day = time.strftime("%Y-%m-%d")
    con.execute("INSERT INTO counters (day, name, n) VALUES (?,?,1) ON CONFLICT(day, name) DO UPDATE SET n=n+1", (day, name))
    return con.execute("SELECT n FROM counters WHERE day=? AND name=?", (day, name)).fetchone()["n"]


def feedback(con: sqlite3.Connection, nid: str, up: bool) -> None:
    con.execute("INSERT OR IGNORE INTO feedback (notice_id) VALUES (?)", (nid,))
    con.execute(f"UPDATE feedback SET {'up' if up else 'down'} = {'up' if up else 'down'} + 1 WHERE notice_id=?", (nid,))


def stats(con: sqlite3.Connection) -> dict:
    out = {"notices": con.execute("SELECT COUNT(*) FROM notices").fetchone()[0],
           "extractions": con.execute("SELECT COUNT(*) FROM extractions").fetchone()[0],
           "sentences_kept": con.execute("SELECT COALESCE(SUM(kept),0) FROM extractions").fetchone()[0],
           "sentences_removed": con.execute("SELECT COALESCE(SUM(removed),0) FROM extractions").fetchone()[0],
           "feedback_up": con.execute("SELECT COALESCE(SUM(up),0) FROM feedback").fetchone()[0],
           "feedback_down": con.execute("SELECT COALESCE(SUM(down),0) FROM feedback").fetchone()[0]}
    out["searches_by_day"] = [dict(r) for r in con.execute("SELECT day, n FROM counters WHERE name='search' ORDER BY day DESC LIMIT 30")]
    return out

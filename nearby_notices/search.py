"""The search pipeline shared by the web app and the MCP server: resolve the place, ask the Gazette for the
smallest radius it honours that covers the distance, measure every candidate against the nearest postcode it is
filed under, and describe what is left. Nothing typed by the user is stored."""
from __future__ import annotations

import datetime
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import httpx

from . import config, counter, extract, gazette, geo, groups, kinds, places, store

MAX_POINT_FETCHES = 40     # linked-data lookups per search, nearest first, so one search can never hammer the Gazette
TOLERANCE = 1.02           # measured distance may exceed the asked distance by 2% plus 50 m before a notice is dropped
SHORT_WORDS = 60           # a feed entry shorter than this is a summary; its full text is fetched before it is read


@dataclass
class Found:
    where: places.Place
    distance: int
    unit: str
    asked_m: float
    since_days: int = 30
    results: list[dict] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)   # notice ids with no plain-English version yet


# A notice is often filed under an office far from the place it is about: a Scottish wind farm under its developer's
# London office, so it appeared 0.2 miles from Trafalgar Square (22/10/2026). The notice's own law says where it
# applies, so a notice made under Scottish or Northern Irish law is shown only for places in that country, and one
# under an England-and-Wales-only Act only for places there. A notice with markers of more than one, or none, is kept.
_SCOTLAND = re.compile(r"\(Scotland\)|Scottish Ministers|Scottish Government|Scottish Executive|Energy Consents Unit|"
                       r"Court of Session|Sheriff Court|Edinburgh Gazette", re.IGNORECASE)
_NORTHERN_IRELAND = re.compile(r"\(Northern Ireland\)|Northern Ireland Executive|Belfast Gazette|Department for Infrastructure", re.IGNORECASE)
_ENGLAND_WALES = re.compile(r"Town and Country Planning Act 1990|Highways Act 1980|Planning Act 2008|\((?:England|Wales|England and Wales)\)|"
                            r"Greater London Authority|London Borough of|Welsh Ministers", re.IGNORECASE)
_COUNTRY_GROUP = {"England": "England and Wales", "Wales": "England and Wales", "Scotland": "Scotland", "Northern Ireland": "Northern Ireland"}


def jurisdiction(text: str) -> str | None:
    """Where a notice's law applies, read from its own words: Scotland, Northern Ireland, England and Wales, or None."""
    found = {name for name, rx in (("Scotland", _SCOTLAND), ("Northern Ireland", _NORTHERN_IRELAND), ("England and Wales", _ENGLAND_WALES))
             if rx.search(text or "")}
    return found.pop() if len(found) == 1 else None


def same_country(row: dict, where: places.Place) -> bool:
    group = _COUNTRY_GROUP.get(where.country or "")
    law = jurisdiction(f"{row.get('title') or ''} {row.get('text') or ''}")
    return group is None or law is None or law == group


def within(m: float | None, asked_m: float) -> bool:
    return m is None or m <= asked_m * TOLERANCE + 50


def _quiet(stage: str, done: int = 0, total: int = 0) -> None:
    """The default progress reporter: the MCP server and the tests do not show a bar."""


def choose_since(days: int | None) -> int:
    """The time window in days: one of the offered choices, the default when none or an odd value is asked."""
    return days if days in config.SINCE_CHOICES else config.DEFAULT_SINCE_DAYS


def candidates(con, where: places.Place, radius: int, report=_quiet, since_days: int | None = None) -> list[str]:
    """Every notice the Gazette lists within one of its honoured radii and published within the window, cached for
    an hour under that radius and window so a change of distance or unit within it needs no new feed call."""
    since_days = choose_since(since_days)
    key = store.feed_key(where.postcode, radius, since_days)
    ids = store.cached_feed(con, key)
    if ids is not None:
        return ids
    # All network first, then one short burst of writes: a transaction must never wait on the Gazette.
    with httpx.Client() as client:
        report("feed", 0, len(gazette.ALLOWED))
        since = (datetime.date.today() - datetime.timedelta(days=since_days)).isoformat()
        notices = gazette.search_near(where.postcode, radius, client=client, since=since,
                                      on_category=lambda d, t: report("feed", d, t))
        # Most feed entries are short summaries. Their full texts are NOT fetched here: the search does not need
        # them, and fetching 20 to 30 of them was most of a first search's wait. The background reader fetches
        # each one just before reading it (full_text_for), and the card is swapped in when it is ready.
    ids = []
    for n in notices:
        cached = store.get_notice(con, n.id)
        if cached and cached["points"]:
            n.points = cached["points"]
        if cached and len(cached["text"]) > len(n.text):      # never replace a fetched full text with the summary
            n.text = cached["text"]
        store.put_notice(con, n)
        ids.append(n.id)
    store.put_feed(con, key, ids)
    con.commit()
    return ids


def filed_points(row: dict) -> list[dict]:
    return row["points"] or ([{"postcode": None, "lat": row["lat"], "lon": row["lon"]}] if row.get("lat") is not None else [])


def select(con, where: places.Place, ids: list[str], asked_m: float, report=_quiet) -> list[str]:
    """Measure each candidate against the nearest postcode it is filed under and keep those inside the asked distance."""
    if where.lat is None or where.lon is None:
        return list(ids)
    rows = {nid: row for nid in ids if (row := store.get_notice(con, nid))}

    def measured(row: dict) -> dict | None:
        return geo.nearest(filed_points(row), where.lat, where.lon)

    # The feed's single point is often a correspondence address; before dropping a notice, look up every
    # postcode it is filed under (one small request each, a few side by side, kept with the notice for good).
    unsure = [nid for nid, row in rows.items() if not row["points"] and (near := measured(row)) and not within(near["m"], asked_m)]
    if unsure:
        unsure.sort(key=lambda nid: measured(rows[nid])["m"])     # nearest first: those most likely to be inside
        ask = unsure[:MAX_POINT_FETCHES]
        fetched = []
        report("points", 0, len(ask))
        with httpx.Client() as client, ThreadPoolExecutor(max_workers=gazette.PARALLEL) as pool:
            for nid, pts in zip(ask, pool.map(lambda i: _points_or_none(i, client), ask)):
                fetched.append((nid, pts))
                report("points", len(fetched), len(ask))
        for nid, pts in fetched:          # writes only after every lookup has returned
            if pts:
                store.put_points(con, nid, pts)
                rows[nid]["points"] = pts
        con.commit()
    kept = [nid for nid, row in rows.items()
            if ((near := measured(row)) is None or within(near["m"], asked_m)) and same_country(row, where)]
    return kept


def _points_or_none(nid: str, client: httpx.Client) -> list[dict]:
    """A notice's filed postcodes, or none if the Gazette is slow or fails: the notice is then measured by the
    feed's own point, which only risks keeping one that is a little further away. It never fails the search."""
    try:
        return gazette.points(nid, client)
    except (httpx.HTTPError, ValueError):
        return []


def full_text_for(row: dict) -> str:
    """The notice's full text: fetched once from the Gazette when the feed held only a short summary, then kept.
    Called by the background reader before a notice is read, and by read(); on any failure the summary stands."""
    if len(row["text"].split()) >= SHORT_WORDS:
        return row["text"]
    try:
        text = gazette.full_text(row["id"])
    except (httpx.HTTPError, ValueError):
        return row["text"]
    if len(text) > len(row["text"]):
        with store.db() as con:
            store.put_text(con, row["id"], text)
        return text
    return row["text"]


def describe(con, row: dict, where: places.Place | None, unit: str, asked_m: float | None) -> dict:
    """One notice as the pages and the tools see it: record, plain-English version, group, feedback counts, where it sits."""
    ex = extract.refilter(store.get_extraction(con, row["id"], config.MODEL))
    fb = con.execute("SELECT up, down FROM feedback WHERE notice_id=?", (row["id"],)).fetchone()
    pts = filed_points(row)
    near = geo.nearest(pts, where.lat, where.lon) if where and where.lat is not None and where.lon is not None and pts else None
    kind = ex.get("kind") if ex and not ex.get("error") else None
    return {"n": row, "x": ex, "group": groups.group_of(row["notice_code"]), "fb": dict(fb) if fb else {"up": 0, "down": 0},
            "kind": kind, "kind_source": "summary" if kind else None,
            "near": near, "dist": geo.fmt(near["m"], unit) if near else None,
            "outside": bool(near and asked_m is not None and not within(near["m"], asked_m))}


def find(place_query: str, distance: float | None, unit: str, report=_quiet, since_days: int | None = None) -> Found | None:
    """Every notice near a postcode or town, within the distance and published within the window, newest first.
    None when the place is not found.
    report(stage, done, total) is told each step, for the page's progress bar (see progress.py)."""
    unit = geo.unit_key(unit)
    distance = geo.choose_distance(distance if distance is not None else config.DEFAULT_DISTANCE_MILES, unit)
    report("place")
    where = places.resolve(place_query)
    if not where:
        return None
    asked_m = geo.to_metres(distance, unit)
    with store.db() as con:
        store.bump(con, "search")
        counter.count("search")
        con.commit()                      # the counter is its own tiny transaction; nothing waits behind it
        since_days = choose_since(since_days)
        found_ids = candidates(con, where, geo.gazette_radius(geo.to_miles(distance, unit)), report, since_days)
        ids = select(con, where, found_ids, asked_m, report)
        report("done")
        results = [describe(con, row, where, unit, asked_m) for nid in ids if (row := store.get_notice(con, nid))]
        need = [r for r in results if not r["kind"]]
        if need and kinds.status(con)["on"]:      # off when live agreement with the language model has fallen (kinds.py)
            for r, k in zip(need, kinds.predict([r["n"] for r in need])):
                r["kind"], r["kind_source"] = k, "model" if k else None
    return Found(where, distance, unit, asked_m, since_days, results, [r["n"]["id"] for r in results if r["x"] is None])


def read(notice_id: str, make_now: bool = False) -> tuple[dict, dict | None] | None:
    """A stored notice and its plain-English version. With make_now, the version is made on the spot if missing."""
    with store.db() as con:
        row = store.get_notice(con, notice_id)
        if not row:
            return None
        ex = extract.refilter(store.get_extraction(con, notice_id, config.MODEL))
    if ex is None and make_now:
        row = {**row, "text": full_text_for(row)}
        r = extract.extract(row["text"])      # outside any transaction: this can take half a minute
        ex = r.to_dict()
        with store.db() as con:
            store.put_extraction(con, notice_id, config.MODEL, ex, len(r.summary), len(r.removed), r.seconds)
            kinds.record(con, row, r.kind)
    return row, ex

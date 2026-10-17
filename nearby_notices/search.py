"""The search pipeline shared by the web app and the MCP server: resolve the place, ask the Gazette for the
smallest radius it honours that covers the distance, measure every candidate against the nearest postcode it is
filed under, and describe what is left. Nothing typed by the user is stored."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import httpx

from . import config, extract, gazette, geo, groups, places, store

MAX_POINT_FETCHES = 16     # linked-data lookups per search, so one search can never hammer the Gazette
PAGE_SIZE = 6              # latest notices per category asked of the Gazette; six categories, so at most 36 candidates
TOLERANCE = 1.02           # measured distance may exceed the asked distance by 2% plus 50 m before a notice is dropped


@dataclass
class Found:
    where: places.Place
    distance: int
    unit: str
    asked_m: float
    results: list[dict] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)   # notice ids with no plain-English version yet


def within(m: float | None, asked_m: float) -> bool:
    return m is None or m <= asked_m * TOLERANCE + 50


def candidates(con, where: places.Place, radius: int) -> list[str]:
    """Every notice the Gazette lists within one of its honoured radii, cached for an hour under that radius so a
    change of distance or unit within it needs no new feed call."""
    key = f"{where.postcode}|g{radius}"
    ids = store.cached_feed(con, key)
    if ids is not None:
        return ids
    # All network first, then one short burst of writes: a transaction must never wait on the Gazette.
    with httpx.Client() as client:
        notices = gazette.search_near(where.postcode, radius, page_size=PAGE_SIZE, client=client)
        for n in notices:
            if len(n.text.split()) < 60:
                n.text = gazette.full_text(n.id, client)
    ids = []
    for n in notices:
        cached = store.get_notice(con, n.id)
        if cached and cached["points"]:
            n.points = cached["points"]
        store.put_notice(con, n)
        ids.append(n.id)
    store.put_feed(con, key, ids)
    con.commit()
    return ids


def filed_points(row: dict) -> list[dict]:
    return row["points"] or ([{"postcode": None, "lat": row["lat"], "lon": row["lon"]}] if row.get("lat") is not None else [])


def select(con, where: places.Place, ids: list[str], asked_m: float) -> list[str]:
    """Measure each candidate against the nearest postcode it is filed under and keep those inside the asked distance."""
    if where.lat is None or where.lon is None:
        return ids[: config.MAX_RESULTS]
    rows = {nid: row for nid in ids if (row := store.get_notice(con, nid))}

    def measured(row: dict) -> dict | None:
        return geo.nearest(filed_points(row), where.lat, where.lon)

    # The feed's single point is often a correspondence address; before dropping a notice, look up every
    # postcode it is filed under (one small request each, a few side by side, kept with the notice for good).
    unsure = [nid for nid, row in rows.items() if not row["points"] and (near := measured(row)) and not within(near["m"], asked_m)]
    if unsure:
        with httpx.Client() as client, ThreadPoolExecutor(max_workers=gazette.PARALLEL) as pool:
            fetched = list(zip(unsure[:MAX_POINT_FETCHES], pool.map(lambda i: gazette.points(i, client), unsure[:MAX_POINT_FETCHES])))
        for nid, pts in fetched:          # writes only after every lookup has returned
            if pts:
                store.put_points(con, nid, pts)
                rows[nid]["points"] = pts
        con.commit()
    kept = [nid for nid, row in rows.items() if (near := measured(row)) is None or within(near["m"], asked_m)]
    return kept[: config.MAX_RESULTS]


def describe(con, row: dict, where: places.Place | None, unit: str, asked_m: float | None) -> dict:
    """One notice as the pages and the tools see it: record, plain-English version, group, feedback counts, where it sits."""
    ex = store.get_extraction(con, row["id"], config.MODEL)
    fb = con.execute("SELECT up, down FROM feedback WHERE notice_id=?", (row["id"],)).fetchone()
    pts = filed_points(row)
    near = geo.nearest(pts, where.lat, where.lon) if where and where.lat is not None and where.lon is not None and pts else None
    return {"n": row, "x": ex, "group": groups.group_of(row["notice_code"]), "fb": dict(fb) if fb else {"up": 0, "down": 0},
            "near": near, "dist": geo.fmt(near["m"], unit) if near else None,
            "outside": bool(near and asked_m is not None and not within(near["m"], asked_m))}


def find(place_query: str, distance: float | None, unit: str) -> Found | None:
    """Notices near a postcode or town, within the distance, newest first. None when the place is not found."""
    unit = geo.unit_key(unit)
    distance = geo.choose_distance(distance if distance is not None else config.DEFAULT_DISTANCE_MILES, unit)
    where = places.resolve(place_query)
    if not where:
        return None
    asked_m = geo.to_metres(distance, unit)
    with store.db() as con:
        store.bump(con, "search")
        con.commit()                      # the counter is its own tiny transaction; nothing waits behind it
        ids = select(con, where, candidates(con, where, geo.gazette_radius(geo.to_miles(distance, unit))), asked_m)
        results = [describe(con, row, where, unit, asked_m) for nid in ids if (row := store.get_notice(con, nid))]
    return Found(where, distance, unit, asked_m, results, [r["n"]["id"] for r in results if r["x"] is None])


def read(notice_id: str, make_now: bool = False) -> tuple[dict, dict | None] | None:
    """A stored notice and its plain-English version. With make_now, the version is made on the spot if missing."""
    with store.db() as con:
        row = store.get_notice(con, notice_id)
        if not row:
            return None
        ex = store.get_extraction(con, notice_id, config.MODEL)
    if ex is None and make_now:
        r = extract.extract(row["text"])      # outside any transaction: this can take half a minute
        ex = r.to_dict()
        with store.db() as con:
            store.put_extraction(con, notice_id, config.MODEL, ex, len(r.summary), len(r.removed), r.seconds)
    return row, ex

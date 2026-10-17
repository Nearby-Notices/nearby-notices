"""The web app: one search box, results as a list, grouped by kind, or on a map, with plain English beside the
verbatim notice, and a privacy page.

No cookies, no accounts. What the user types is used for the search and not stored. Access logs are off;
the only counters are daily totals with no identifiers. Notices are read by a background worker so the
page returns at once; a small script then asks /status every few seconds and swaps in each card as it is
ready, so the page never reloads under the reader.
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import httpx
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config, gazette, geo, groups, places, store, worker
from .categories import ALLOWED, EXCLUDED

logging.getLogger("uvicorn.access").disabled = True
ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="Nearby Notices", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")

DISCLAIMER = ("Not affiliated with The Gazette, the Government or any council. This tool shows public notices in plain "
              "English and does not give advice. Always read the notice itself. Notice data: The Gazette, "
              "Open Government Licence v3.")
MAX_POINT_FETCHES = 16     # linked-data lookups per search, so one search can never hammer the Gazette
PAGE_SIZE = 6              # latest notices per category asked of the Gazette; six categories, so at most 36 candidates
TOLERANCE = 1.02           # measured distance may exceed the asked distance by 2% plus 50 m before a notice is dropped
_ID = re.compile(r"^\d{1,12}$")


def nice_date(s: str) -> str:
    try:
        return date.fromisoformat(s[:10]).strftime("%-d %B %Y")
    except (ValueError, TypeError):
        return s or ""


templates.env.filters["nice_date"] = nice_date


def _ctx(request: Request, **kw) -> dict:
    return {"request": request, "disclaimer": DISCLAIMER, "allowed": ALLOWED, "excluded": EXCLUDED,
            "group_name": groups.group_name, "group_colour": groups.group_colour, "icons": groups.ICONS, "units": geo.UNITS,
            "unit_choices": {u: spec["choices"] for u, spec in geo.UNITS.items()}, **kw}


@app.on_event("startup")
def _startup() -> None:
    worker.start()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "home.html", _ctx(request, distance=config.DEFAULT_DISTANCE_MILES, unit="mi"))


def _within(m: float | None, asked_m: float) -> bool:
    return m is None or m <= asked_m * TOLERANCE + 50


def _candidates(con, where: places.Place, radius: int) -> list[str]:
    """Every notice the Gazette lists within one of its honoured radii, cached for an hour under that radius so a
    change of distance or unit within it needs no new feed call."""
    key = f"{where.postcode}|g{radius}"
    ids = store.cached_feed(con, key)
    if ids is not None:
        return ids
    ids = []
    with httpx.Client() as client:
        for n in gazette.search_near(where.postcode, radius, page_size=PAGE_SIZE, client=client):
            if len(n.text.split()) < 60:
                n.text = gazette.full_text(n.id, client)
            cached = store.get_notice(con, n.id)
            if cached and cached["points"]:
                n.points = cached["points"]
            store.put_notice(con, n)
            ids.append(n.id)
    store.put_feed(con, key, ids)
    return ids


def _select(con, where: places.Place, ids: list[str], asked_m: float) -> list[str]:
    """Measure each candidate against the nearest postcode it is filed under and keep those inside the asked distance."""
    if where.lat is None or where.lon is None:
        return ids[: config.MAX_RESULTS]
    rows = {nid: row for nid in ids if (row := store.get_notice(con, nid))}

    def filed_points(row: dict) -> list[dict]:
        return row["points"] or ([{"postcode": None, "lat": row["lat"], "lon": row["lon"]}] if row.get("lat") is not None else [])

    def measured(row: dict) -> dict | None:
        return geo.nearest(filed_points(row), where.lat, where.lon)

    # The feed's single point is often a correspondence address; before dropping a notice, look up every
    # postcode it is filed under (one small request each, a few side by side, kept with the notice for good).
    unsure = [nid for nid, row in rows.items() if not row["points"] and (near := measured(row)) and not _within(near["m"], asked_m)]
    if unsure:
        with httpx.Client() as client, ThreadPoolExecutor(max_workers=gazette.PARALLEL) as pool:
            for nid, pts in zip(unsure[:MAX_POINT_FETCHES], pool.map(lambda i: gazette.points(i, client), unsure[:MAX_POINT_FETCHES])):
                if pts:
                    store.put_points(con, nid, pts)
                    rows[nid]["points"] = pts
    kept = [nid for nid, row in rows.items() if (near := measured(row)) is None or _within(near["m"], asked_m)]
    return kept[: config.MAX_RESULTS]


def _result(con, row: dict, where: places.Place | None, unit: str, asked_m: float | None) -> dict:
    """One notice as the templates see it: record, extraction, group, feedback counts, and where it sits."""
    ex = store.get_extraction(con, row["id"], config.MODEL)
    fb = con.execute("SELECT up, down FROM feedback WHERE notice_id=?", (row["id"],)).fetchone()
    pts = row["points"] or ([{"postcode": None, "lat": row["lat"], "lon": row["lon"]}] if row.get("lat") is not None else [])
    near = geo.nearest(pts, where.lat, where.lon) if where and where.lat is not None and where.lon is not None and pts else None
    return {"n": row, "x": ex, "group": groups.group_of(row["notice_code"]), "fb": dict(fb) if fb else {"up": 0, "down": 0},
            "near": near, "dist": geo.fmt(near["m"], unit) if near else None,
            "outside": bool(near and asked_m is not None and not _within(near["m"], asked_m))}


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, place: str = "", distance: float | None = None, unit: str = "mi", view: str = "all"):
    unit = geo.unit_key(unit)
    distance = geo.choose_distance(distance if distance is not None else config.DEFAULT_DISTANCE_MILES, unit)
    where = places.resolve(place)
    if not where:
        return templates.TemplateResponse(request, "home.html", _ctx(
            request, distance=distance, unit=unit, error="I could not find that place. Try a full postcode or a town name."))
    asked_m = geo.to_metres(distance, unit)
    results, todo = [], []
    with store.db() as con:
        store.bump(con, "search")
        ids = _select(con, where, _candidates(con, where, geo.gazette_radius(geo.to_miles(distance, unit))), asked_m)
        for nid in ids:
            row = store.get_notice(con, nid)
            if not row:
                continue
            r = _result(con, row, where, unit, asked_m)
            if r["x"] is None:
                todo.append(nid)
            results.append(r)
    if todo:
        worker.enqueue(todo)
    counts = {g: sum(1 for r in results if r["group"] == g) for g in groups.ORDER}
    grouped = [(g, [r for r in results if r["group"] == g]) for g in groups.ORDER if counts[g]]
    points = [{"id": r["n"]["id"], "lat": r["near"]["lat"], "lon": r["near"]["lon"], "group": r["group"],
               "title": (r["x"]["what"] if r["x"] and r["x"].get("what") else r["n"]["title"]),
               "published": nice_date(r["n"]["published"]), "url": r["n"]["url"], "dist": r["dist"],
               "postcode": r["near"].get("postcode"), "outside": r["outside"]}
              for r in results if r["near"]]
    back = f"{request.url.path}?{request.url.query}"
    card_query = {"back": back, "unit": unit, "lat": where.lat, "lon": where.lon}
    return templates.TemplateResponse(request, "results.html", _ctx(
        request, place=where, distance=distance, unit=unit, distance_label=geo.fmt(asked_m, unit), asked_m=asked_m,
        results=results, grouped=grouped, counts=counts, pending_ids=todo, order=groups.ORDER, points=points,
        view=view if view in ("all", "grouped", "map") else "all", back=back, card_query=card_query,
        names={g: groups.group_name(g) for g in groups.ORDER}))


@app.get("/status")
def status(ids: str = ""):
    """Which of these notices now have a plain-English version. Polled by the results page instead of reloading it."""
    wanted = [i for i in ids.split(",") if _ID.match(i)][:60]
    ready = []
    with store.db() as con:
        for nid in wanted:
            if store.get_extraction(con, nid, config.MODEL) is not None:
                ready.append(nid)
    return {"ready": ready, "pending": [i for i in wanted if i not in ready]}


@app.get("/card/{notice_id}", response_class=HTMLResponse)
def card(request: Request, notice_id: str, back: str = "/", unit: str = "mi", lat: float | None = None, lon: float | None = None):
    """One notice's card, rendered by the same template as the results page, for the page to swap in."""
    if not _ID.match(notice_id):
        raise HTTPException(404)
    with store.db() as con:
        row = store.get_notice(con, notice_id)
        if not row:
            raise HTTPException(404)
        where = places.Place("", "", "", lat, lon) if lat is not None and lon is not None else None
        r = _result(con, row, where, geo.unit_key(unit), None)
    return templates.TemplateResponse(request, "card.html", _ctx(request, r=r, back=back if back.startswith("/") else "/"))


@app.post("/feedback")
def feedback(notice_id: str = Form(...), vote: str = Form(...), back: str = Form("/")):
    with store.db() as con:
        store.feedback(con, notice_id, vote == "up")
    return RedirectResponse(url=back if back.startswith("/") else "/", status_code=303)


@app.get("/privacy", response_class=HTMLResponse)
def privacy(request: Request):
    return templates.TemplateResponse(request, "privacy.html", _ctx(request))


@app.get("/about", response_class=HTMLResponse)
def about(request: Request):
    with store.db() as con:
        s = store.stats(con)
    return templates.TemplateResponse(request, "about.html", _ctx(request, stats=s, model=config.MODEL))


@app.get("/health")
def health():
    return {"ok": True}

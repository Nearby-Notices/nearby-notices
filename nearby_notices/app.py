"""The web app: one search box, results as a list, grouped by kind, or on a map, with plain English beside the
verbatim notice, and a privacy page.

No cookies, no accounts. What the user types is used for the search and not stored. Access logs are off;
the only counters are daily totals with no identifiers. Notices are read by a background worker so the
page returns at once; a small script then asks /status every few seconds and swaps in each card as it is
ready, so the page never reloads under the reader. The search itself lives in search.py, shared with the MCP server.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config, geo, groups, places, ratelimit, search, store, worker
from .categories import ALLOWED, EXCLUDED

logging.getLogger("uvicorn.access").disabled = True
ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="Nearby Notices", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")

# Searches cost Gazette and model calls; the rest is cheap. Limits per client per minute, with no address kept (see ratelimit.py).
LIMITS = {"/search": config.SEARCHES_PER_MINUTE, "/feedback": 30}


@app.middleware("http")
async def _limit(request: Request, call_next):
    limit = LIMITS.get(request.url.path)
    if limit is not None:
        forwarded = request.headers.get("x-forwarded-for", "")
        address = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "")
        if not ratelimit.allow(address, limit):
            return PlainTextResponse("Too many requests from your connection in the last minute. Please wait a moment and try again.",
                                     status_code=429, headers={"Retry-After": "60"})
    return await call_next(request)

DISCLAIMER = ("Not affiliated with The Gazette, the Government or any council. This tool shows public notices in plain "
              "English and does not give advice. Always read the notice itself. Notice data: The Gazette, "
              "Open Government Licence v3.")
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
    worker.warm_up()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "home.html", _ctx(request, distance=config.DEFAULT_DISTANCE_MILES, unit="mi"))


@app.get("/search", response_class=HTMLResponse)
def search_page(request: Request, place: str = "", distance: float | None = None, unit: str = "mi", view: str = "all"):
    unit = geo.unit_key(unit)
    distance = geo.choose_distance(distance if distance is not None else config.DEFAULT_DISTANCE_MILES, unit)
    found = search.find(place, distance, unit)
    if not found:
        return templates.TemplateResponse(request, "home.html", _ctx(
            request, distance=distance, unit=unit, error="I could not find that place. Try a full postcode or a town name."))
    if found.pending:
        worker.enqueue(found.pending)
    results, where = found.results, found.where
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
        request, place=where, distance=found.distance, unit=unit, distance_label=geo.fmt(found.asked_m, unit), asked_m=found.asked_m,
        results=results, grouped=grouped, counts=counts, pending_ids=found.pending, order=groups.ORDER, points=points,
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
        r = search.describe(con, row, where, geo.unit_key(unit), None)
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

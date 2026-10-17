"""The web app: one search box, results grouped by kind with plain English beside the verbatim notice, a privacy page.

No cookies, no accounts. What the user types is used for the search and not stored. Access logs are off;
the only counters are daily totals with no identifiers. Notices are read by a background worker so the
page returns at once and refreshes itself while any are still being read.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config, gazette, groups, places, store, worker
from .categories import ALLOWED, EXCLUDED

logging.getLogger("uvicorn.access").disabled = True
ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="Nearby Notices", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")

DISCLAIMER = ("Not affiliated with The Gazette, the Government or any council. This tool shows public notices in plain "
              "English and does not give advice. Always read the notice itself. Notice data: The Gazette, "
              "Open Government Licence v3.")


def nice_date(s: str) -> str:
    try:
        return date.fromisoformat(s[:10]).strftime("%-d %B %Y")
    except (ValueError, TypeError):
        return s or ""


templates.env.filters["nice_date"] = nice_date


def _ctx(request: Request, **kw) -> dict:
    return {"request": request, "disclaimer": DISCLAIMER, "allowed": ALLOWED, "excluded": EXCLUDED,
            "group_name": groups.group_name, "group_colour": groups.group_colour, **kw}


@app.on_event("startup")
def _startup() -> None:
    worker.start()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "home.html", _ctx(request, distance=config.DEFAULT_DISTANCE_MILES))


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, place: str = "", distance: int = config.DEFAULT_DISTANCE_MILES, view: str = "all"):
    distance = max(1, min(distance, 15))
    where = places.resolve(place)
    if not where:
        return templates.TemplateResponse(request, "home.html", _ctx(request, distance=distance, error="I could not find that place. Try a full postcode or a town name."))
    results, pending = [], 0
    with store.db() as con:
        key = f"{where.postcode}|{distance}"
        ids = store.cached_feed(con, key)
        if ids is None:
            store.bump(con, "search")
            notices = gazette.search_near(where.postcode, distance, page_size=max(3, config.MAX_RESULTS // len(ALLOWED) + 2))
            for n in notices:
                if len(n.text.split()) < 60:
                    n.text = gazette.full_text(n.id)
                store.put_notice(con, n)
            ids = [n.id for n in notices][: config.MAX_RESULTS]
            store.put_feed(con, key, ids)
        todo = []
        for nid in ids:
            row = store.get_notice(con, nid)
            if not row:
                continue
            ex = store.get_extraction(con, nid, config.MODEL)
            if ex is None:
                todo.append(nid)
                pending += 1
            fb = con.execute("SELECT up, down FROM feedback WHERE notice_id=?", (nid,)).fetchone()
            results.append({"n": dict(row), "x": ex, "group": groups.group_of(row["notice_code"]),
                            "fb": dict(fb) if fb else {"up": 0, "down": 0}})
    if todo:
        worker.enqueue(todo)
    counts = {g: sum(1 for r in results if r["group"] == g) for g in groups.ORDER}
    grouped = [(g, [r for r in results if r["group"] == g]) for g in groups.ORDER if counts[g]]
    return templates.TemplateResponse(request, "results.html", _ctx(
        request, place=where, distance=distance, results=results, grouped=grouped, counts=counts,
        pending=pending, view=view if view in ("all", "grouped") else "all", order=groups.ORDER))


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

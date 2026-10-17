"""The web app: one search box, results in plain English with the verbatim notice beside each, a privacy page.

No cookies, no accounts. What the user types is used for the search and not stored. Access logs are off;
the only counters are daily totals with no identifiers.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import config, extract, gazette, places, store
from .categories import ALLOWED, EXCLUDED

logging.getLogger("uvicorn.access").disabled = True
ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="Nearby Notices", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")

DISCLAIMER = ("Not affiliated with The Gazette, the Government or any council. This tool shows public notices in plain "
              "English and does not give advice. Always read the notice itself. Notice data: The Gazette, "
              "Open Government Licence v3.")


def _ctx(request: Request, **kw) -> dict:
    return {"request": request, "disclaimer": DISCLAIMER, "allowed": ALLOWED, "excluded": EXCLUDED, **kw}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "home.html", _ctx(request, distance=config.DEFAULT_DISTANCE_MILES))


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, place: str = "", distance: int = config.DEFAULT_DISTANCE_MILES):
    distance = max(1, min(distance, 15))
    where = places.resolve(place)
    if not where:
        return templates.TemplateResponse(request, "home.html", _ctx(request, distance=distance, error="I could not find that place. Try a full postcode or a town name."))
    results = []
    with store.db() as con:
        store.bump(con, "search")
        key = f"{where.postcode}|{distance}"
        ids = store.cached_feed(con, key)
        if ids is None:
            notices = gazette.search_near(where.postcode, distance, page_size=max(2, config.MAX_RESULTS // len(ALLOWED) + 1))
            for n in notices:
                if len(n.text.split()) < 60:
                    n.text = gazette.full_text(n.id)
                store.put_notice(con, n)
            ids = [n.id for n in notices][: config.MAX_RESULTS]
            store.put_feed(con, key, ids)
        for nid in ids:
            row = store.get_notice(con, nid)
            if not row:
                continue
            ex = store.get_extraction(con, nid, config.MODEL)
            if ex is None:
                r = extract.extract(row["text"])
                ex = r.to_dict()
                store.put_extraction(con, nid, config.MODEL, ex, len(r.summary), len(r.removed), r.seconds)
            fb = con.execute("SELECT up, down FROM feedback WHERE notice_id=?", (nid,)).fetchone()
            results.append({"n": dict(row), "x": ex, "fb": dict(fb) if fb else {"up": 0, "down": 0}})
    return templates.TemplateResponse(request, "results.html", _ctx(request, place=where, distance=distance, results=results))


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

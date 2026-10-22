"""Food hygiene ratings near a point, for the map's optional layer, from the Food Standards Agency's open API.

UK-wide: the 0 to 5 scheme in England, Wales and Northern Ireland (FHRS) and Pass / Improvement Required in Scotland
(FHIS). Only businesses with a published address are kept: the FSA withholds the address of food businesses run
from a private home, and those are left out entirely, as the service leaves out notices about individuals.
Results are kept for a day per point and distance, so a busy page never repeats the call.
"""
from __future__ import annotations

import threading
import time

import httpx

from . import config

API = "https://api.ratings.food.gov.uk/Establishments"
PAGE = "https://ratings.food.gov.uk/business/{id}"
MAX_RESULTS = 2000          # nearest first; a city centre at 3 miles can hold several thousand
CACHE_SECONDS = 24 * 3600
GOOD = {"5", "4", "Pass", "Pass and Eat Safe"}
FAIR = {"3"}
POOR = {"2", "1", "0", "Improvement Required"}

_lock = threading.Lock()
_cache: dict[tuple, tuple[float, list[dict]]] = {}


def band(rating: str) -> str:
    """good, fair or poor for a rating in either scheme; other for awaiting inspection, exempt and the like."""
    return "good" if rating in GOOD else "fair" if rating in FAIR else "poor" if rating in POOR else "other"


def slim(e: dict) -> dict | None:
    """What the map needs about one business, or None if it has no published address or no location."""
    lines = [e.get(f"AddressLine{i}") or "" for i in range(1, 5)]
    geo = e.get("geocode") or {}
    try:
        lat, lon = float(geo.get("latitude")), float(geo.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not any(x.strip() for x in lines):
        return None
    rating = str(e.get("RatingValue") or "")
    return {"id": e.get("FHRSID"), "name": e.get("BusinessName") or "", "type": e.get("BusinessType") or "",
            "address": ", ".join(x.strip() for x in [*lines, e.get("PostCode") or ""] if x and x.strip()),
            "rating": rating, "scheme": e.get("SchemeType") or "", "date": (e.get("RatingDate") or "")[:10],
            "band": band(rating), "lat": lat, "lon": lon, "url": PAGE.format(id=e.get("FHRSID"))}


def near(lat: float, lon: float, miles: float, client: httpx.Client | None = None) -> list[dict]:
    """Rated food businesses within the distance of the point, nearest first."""
    key = (round(lat, 3), round(lon, 3), round(miles, 1))
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
    own = client is None
    client = client or httpx.Client()
    try:
        r = client.get(API, params={"latitude": lat, "longitude": lon, "maxDistanceLimit": miles, "pageSize": MAX_RESULTS,
                                    "pageNumber": 1, "sortOptionKey": "distance"},
                       headers={"x-api-version": "2", "Accept": "application/json", "User-Agent": config.USER_AGENT}, timeout=20)
        r.raise_for_status()
        items = [s for e in (r.json().get("establishments") or []) if (s := slim(e))]
    finally:
        if own:
            client.close()
    with _lock:
        _cache[key] = (time.time(), items)
        for k in [k for k, (t, _) in _cache.items() if time.time() - t > CACHE_SECONDS]:
            del _cache[k]
    return items

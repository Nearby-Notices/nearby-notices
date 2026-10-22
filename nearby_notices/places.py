"""Turn what a person types (a postcode or a town) into a postcode the Gazette's location filter accepts.

postcodes.io is a free service over open data (ONS and Ordnance Survey, Open Government Licence).
Nothing typed by the user is stored by this tool; the lookup is a pass-through.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

from . import config

POSTCODE = re.compile(r"^[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}$", re.IGNORECASE)


@dataclass
class Place:
    query: str
    postcode: str
    name: str  # what we show back, for example "Dudley (St. James's ward), West Midlands"
    lat: float | None = None
    lon: float | None = None
    country: str | None = None   # England, Wales, Scotland or Northern Ireland (postcodes.io)


def _get(client: httpx.Client, path: str, params: dict | None = None) -> dict:
    r = client.get(f"{config.POSTCODES_BASE}{path}", params=params, timeout=15, headers={"User-Agent": config.USER_AGENT})
    if r.status_code == 404:
        return {}
    r.raise_for_status()
    return r.json()


def resolve(query: str, client: httpx.Client | None = None) -> Place | None:
    """A postcode is validated and described; a town name becomes its nearest postcode."""
    q = query.strip()
    if not q:
        return None
    own = client is None
    client = client or httpx.Client()
    try:
        if POSTCODE.match(q):
            d = _get(client, f"/postcodes/{q.replace(' ', '')}")
            res = d.get("result")
            if not res:
                return None
            return Place(q, res["postcode"], _describe(res), res.get("latitude"), res.get("longitude"), res.get("country"))
        d = _get(client, "/places", {"q": q, "limit": 1})
        places = d.get("result") or []
        if not places:
            return None
        p = places[0]
        near = _get(client, "/postcodes", {"lon": p["longitude"], "lat": p["latitude"], "limit": 1})
        res = (near.get("result") or [None])[0]
        if not res:
            return None
        label = p.get("name_1") or q
        return Place(q, res["postcode"], f"{label}, {p.get('county_unitary') or p.get('region') or ''}".strip(", "),
                     p.get("latitude"), p.get("longitude"), res.get("country"))
    finally:
        if own:
            client.close()


def _describe(res: dict) -> str:
    bits = [res.get("admin_district"), res.get("region")]
    ward = res.get("admin_ward")
    head = f"{bits[0]} ({ward} ward)" if ward and bits[0] else (bits[0] or "")
    return ", ".join(b for b in (head, bits[1]) if b)

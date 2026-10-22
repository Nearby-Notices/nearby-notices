"""The Gazette feed client: gentle, cached, and limited to the allowed categories.

Feed: /all-notices/notice/data.json with categorycode, location-postcode-1, location-distance-1 (miles; only
1, 5, 10, 15, 20, 25, 30 are honoured), sort-by=latest-date, results-page-size, results-page. Each entry
carries the notice's HTML in "content" and ONE geo:Point, although a notice is usually filed under several
postcodes (the affected street, the council, a consultant's office) and the Gazette's distance filter matches
on any of them. All of a notice's postcodes, with coordinates: /notice/{id}/data.jsonld.
Full text, if the feed's copy is short: /notice/{id}/data.xml. Checked live on 17/10/2026.
"""
from __future__ import annotations

import html
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import httpx

from . import config
from .categories import ALLOWED, is_allowed

POSTCODE_ID = "https://www.thegazette.co.uk/id/postcode/"
PARALLEL = 6   # requests side by side (six categories at once); the Gazette answers each in 2 to 4 s
PAGE_SIZE = 100   # notices per feed page, the most the Gazette gives in one answer
MAX_PAGES = 10    # per category and search: a safety limit for the Gazette's sake (1,000 notices of one kind), not a display cap

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_last_call = 0.0
_gap_lock = threading.Lock()


def clean_text(fragment: str) -> str:
    """HTML to plain text: paragraphs become line breaks, everything else is stripped."""
    s = re.sub(r"</(p|div|br|li|tr|h\d)\s*>", "\n", fragment, flags=re.IGNORECASE)
    s = re.sub(r"<(script|style).*?</\1>", "", s, flags=re.DOTALL | re.IGNORECASE)
    s = html.unescape(_TAG.sub(" ", s))
    s = "\n".join(_WS.sub(" ", line).strip() for line in s.splitlines())
    return re.sub(r"\n{2,}", "\n", s).strip()


@dataclass
class Notice:
    id: str
    title: str
    category: str
    notice_code: int
    published: str
    text: str
    url: str
    lat: float | None = None   # the feed's geo:Point: the first postcode the notice is filed under
    lon: float | None = None
    points: list[dict] = field(default_factory=list)  # every filed postcode: {"postcode", "lat", "lon"}; empty until fetched

    def all_points(self) -> list[dict]:
        if self.points:
            return self.points
        if self.lat is not None and self.lon is not None:
            return [{"postcode": None, "lat": self.lat, "lon": self.lon}]
        return []


def _geo(e: dict) -> tuple[float | None, float | None]:
    p = e.get("geo:Point") or {}
    try:
        return float(p.get("geo:lat")), float(p.get("geo:long"))
    except (TypeError, ValueError):
        return None, None


class GazetteUnavailable(RuntimeError):
    """Every category request failed: the Gazette is down or unreachable, so there is nothing to show."""


def _polite_get(client: httpx.Client, url: str, params: dict | None = None, timeout: float = 20) -> httpx.Response:
    """Fair use: requests start at most four a second across every thread, a named user agent, no retry storms."""
    global _last_call
    with _gap_lock:
        gap = time.monotonic() - _last_call
        if gap < 0.25:
            time.sleep(0.25 - gap)
        _last_call = time.monotonic()
    r = client.get(url, params=params, headers={"User-Agent": config.USER_AGENT}, timeout=timeout)
    r.raise_for_status()
    return r


def _entries(payload: dict) -> list[dict]:
    e = payload.get("entry") or []
    return e if isinstance(e, list) else [e]


def _parse_entry(e: dict) -> Notice | None:
    code = e.get("f:notice-code")
    if not is_allowed(code):
        return None
    nid = str(e.get("id", "")).rsplit("/", 1)[-1]
    link = e.get("link")
    url = ""
    if isinstance(link, list):
        for item in link:
            if item.get("@rel") == "alternate" and "htm" in (item.get("@type") or ""):
                url = item.get("@href", "")
    if not url:
        url = f"{config.GAZETTE_BASE}/notice/{nid}"
    cat = e.get("category") or {}
    lat, lon = _geo(e)
    # Only these fields are kept. The feed also carries the Gazette staff member's name on each entry
    # (f:name, f:familyName); it is personal data and is never read into this tool.
    return Notice(
        id=nid,
        title=str(e.get("title") or ""),
        category=str(cat.get("@term") if isinstance(cat, dict) else cat),
        notice_code=int(code),
        published=str(e.get("published") or "")[:10],
        text=clean_text(str(e.get("content") or "")),
        url=url,
        lat=lat,
        lon=lon,
    )


def search_near(postcode: str, distance_miles: int, page_size: int = PAGE_SIZE, client: httpx.Client | None = None,
                on_category=None, since: str | None = None, max_pages: int = MAX_PAGES) -> list[Notice]:
    """Every notice in every allowed category within the distance of the postcode (the Gazette's own filter),
    published on or after `since` (YYYY-MM-DD), newest first. All pages are read, up to max_pages per category.

    distance_miles must be one of the radii the Gazette honours (see geo.gazette_radius); others are silently rounded down by the Gazette.
    on_category(done, total) is called as each category's answer is taken in, for a progress bar."""
    own = client is None
    client = client or httpx.Client()

    failed: list[int] = []

    def one(cat: int) -> list[Notice]:
        params = {
            "categorycode": cat,
            "location-postcode-1": postcode,
            "location-distance-1": distance_miles,
            "sort-by": "latest-date",
            "results-page-size": page_size,
            "results-page": 1,
        }
        if since:
            params["start-publish-date"] = since
        found: list[Notice] = []
        try:
            payload = _polite_get(client, f"{config.GAZETTE_BASE}/all-notices/notice/data.json", params).json()
        except (httpx.HTTPError, ValueError):     # one slow or failed category is skipped, not the whole search
            failed.append(cat)
            return []
        found.extend(n for n in (_parse_entry(e) for e in _entries(payload)) if n)
        try:
            total = int(payload.get("f:total") or 0)
        except (TypeError, ValueError):
            total = 0
        pages = min(-(-total // page_size), max_pages)
        for page in range(2, pages + 1):         # later pages of a busy category; a failed page ends that category early
            try:
                payload = _polite_get(client, f"{config.GAZETTE_BASE}/all-notices/notice/data.json", {**params, "results-page": page}).json()
            except (httpx.HTTPError, ValueError):
                break
            found.extend(n for n in (_parse_entry(e) for e in _entries(payload)) if n)
        return found

    out: list[Notice] = []
    try:
        with ThreadPoolExecutor(max_workers=PARALLEL) as pool:
            for i, batch in enumerate(pool.map(one, ALLOWED), 1):
                out.extend(batch)
                if on_category:
                    on_category(i, len(ALLOWED))
    finally:
        if own:
            client.close()
    if len(failed) == len(ALLOWED):
        raise GazetteUnavailable(f"all {len(ALLOWED)} category requests failed")
    out.sort(key=lambda n: n.published, reverse=True)
    return out


def _postcode_label(node_id: str) -> str:
    """'https://www.thegazette.co.uk/id/postcode/B693DE' -> 'B69 3DE'."""
    raw = node_id.rsplit("/", 1)[-1].upper()
    return f"{raw[:-3]} {raw[-3:]}" if len(raw) > 3 else raw


def points_from_jsonld(payload: dict) -> list[dict]:
    """Every postcode node in a notice's linked-data record, as {"postcode", "lat", "lon"}. Nothing else is read."""
    out, seen = [], set()
    for node in payload.get("@graph") or [payload]:
        nid = str(node.get("@id", ""))
        if not nid.startswith(POSTCODE_ID) or nid in seen:
            continue
        try:
            out.append({"postcode": _postcode_label(nid), "lat": float(node["lat"]), "lon": float(node["long"])})
            seen.add(nid)
        except (KeyError, TypeError, ValueError):
            continue
    return out


def points(notice_id: str, client: httpx.Client | None = None) -> list[dict]:
    """All the postcodes a notice is filed under, with coordinates, from its linked-data record."""
    own = client is None
    client = client or httpx.Client()
    try:
        r = _polite_get(client, f"{config.GAZETTE_BASE}/notice/{notice_id}/data.jsonld", timeout=10)
        return points_from_jsonld(json.loads(r.text))
    finally:
        if own:
            client.close()


def full_text(notice_id: str, client: httpx.Client | None = None) -> str:
    """The notice's full text from its XML record, used when the feed's copy looks truncated."""
    own = client is None
    client = client or httpx.Client()
    try:
        r = _polite_get(client, f"{config.GAZETTE_BASE}/notice/{notice_id}/data.xml", timeout=15)
        m = re.search(r"<content[^>]*>(.*?)</content>", r.text, re.DOTALL | re.IGNORECASE)
        body = m.group(1) if m else r.text
        return clean_text(html.unescape(body))
    finally:
        if own:
            client.close()

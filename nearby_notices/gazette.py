"""The Gazette feed client: gentle, cached, and limited to the allowed categories.

Feed: /all-notices/notice/data.json with categorycode, location-postcode-1, location-distance-1,
sort-by=latest-date, results-page-size, results-page. Each entry carries the notice's HTML in "content".
Full text, if the feed's copy is short: /notice/{id}/data.xml. Checked live on 17/10/2026.
"""
from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass

import httpx

from . import config
from .categories import ALLOWED, is_allowed

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_last_call = 0.0


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


def _polite_get(client: httpx.Client, url: str, params: dict | None = None) -> httpx.Response:
    """Fair use: at most two requests a second, a named user agent, no retries storms."""
    global _last_call
    gap = time.monotonic() - _last_call
    if gap < 0.5:
        time.sleep(0.5 - gap)
    _last_call = time.monotonic()
    r = client.get(url, params=params, headers={"User-Agent": config.USER_AGENT}, timeout=30)
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
    return Notice(
        id=nid,
        title=str(e.get("title") or ""),
        category=str(cat.get("@term") if isinstance(cat, dict) else cat),
        notice_code=int(code),
        published=str(e.get("published") or "")[:10],
        text=clean_text(str(e.get("content") or "")),
        url=url,
    )


def search_near(postcode: str, distance_miles: int, page_size: int = 10, client: httpx.Client | None = None) -> list[Notice]:
    """Latest notices in every allowed category within the distance of the postcode (the Gazette's own filter)."""
    own = client is None
    client = client or httpx.Client()
    out: list[Notice] = []
    try:
        for cat in ALLOWED:
            params = {
                "categorycode": cat,
                "location-postcode-1": postcode,
                "location-distance-1": distance_miles,
                "sort-by": "latest-date",
                "results-page-size": page_size,
                "results-page": 1,
            }
            r = _polite_get(client, f"{config.GAZETTE_BASE}/all-notices/notice/data.json", params)
            for e in _entries(r.json()):
                n = _parse_entry(e)
                if n:
                    out.append(n)
    finally:
        if own:
            client.close()
    out.sort(key=lambda n: n.published, reverse=True)
    return out


def full_text(notice_id: str, client: httpx.Client | None = None) -> str:
    """The notice's full text from its XML record, used when the feed's copy looks truncated."""
    own = client is None
    client = client or httpx.Client()
    try:
        r = _polite_get(client, f"{config.GAZETTE_BASE}/notice/{notice_id}/data.xml")
        m = re.search(r"<content[^>]*>(.*?)</content>", r.text, re.DOTALL | re.IGNORECASE)
        body = m.group(1) if m else r.text
        return clean_text(html.unescape(body))
    finally:
        if own:
            client.close()

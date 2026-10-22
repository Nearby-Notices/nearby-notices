"""Daily totals that survive a restart: how many searches the service answered each day, and nothing else.

The local SQLite counter lives on the container's own disk, which is emptied whenever the service scales to zero,
so it cannot say how much the service is used. This keeps the same daily totals in an Azure Table instead: one row
per day and name, holding a number. No identifiers, no place, no time of day beyond the date, no address.

Configured by NN_COUNTER_URL, the table's address with a key that can reach that table only
(https://<account>.table.core.windows.net/<table>?<sas>). Without it, counting is off and nothing is sent.
Each count runs on one background thread, so a search never waits on it and two counts never race each other.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from . import config

log = logging.getLogger(__name__)
HEADERS = {"Accept": "application/json;odata=nometadata", "Content-Type": "application/json", "x-ms-version": "2019-02-02"}
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="counter")


def _parts(url: str) -> tuple[str, str] | None:
    if not url or "?" not in url:
        return None
    base, sas = url.split("?", 1)
    return base.rstrip("/"), sas


def increment(name: str, day: str, url: str, client: httpx.Client, tries: int = 4) -> int | None:
    """Add one to the day's total for this name and return the new total. Read, then write with the row's ETag, so
    a concurrent write from another replica makes this retry rather than lose a count."""
    parts = _parts(url)
    if not parts:
        return None
    base, sas = parts
    row = f"{base}(PartitionKey='{day}',RowKey='{name}')?{sas}"
    for _ in range(tries):
        r = client.get(row, headers=HEADERS)
        if r.status_code == 404:
            ins = client.post(f"{base}?{sas}", headers={**HEADERS, "Prefer": "return-no-content"},
                              json={"PartitionKey": day, "RowKey": name, "n": 1})
            if ins.status_code in (201, 204):
                return 1
            continue                                  # someone else created it first: read it again
        r.raise_for_status()
        n = int(r.json().get("n", 0)) + 1
        up = client.put(row, headers={**HEADERS, "If-Match": r.headers.get("ETag", "*")},
                        json={"PartitionKey": day, "RowKey": name, "n": n})
        if up.status_code in (200, 204):
            return n
        if up.status_code != 412:                     # 412: changed since read, so read again
            up.raise_for_status()
    return None


def _count(name: str, day: str) -> None:
    try:
        with httpx.Client(timeout=10) as client:
            increment(name, day, config.COUNTER_URL, client)
    except Exception as e:  # noqa: BLE001 - counting must never affect the service
        log.warning("counter %s not recorded: %s", name, type(e).__name__)


def count(name: str) -> None:
    """Count one event for today, in the background. A no-op unless NN_COUNTER_URL is set."""
    if config.COUNTER_URL:
        _pool.submit(_count, name, time.strftime("%Y-%m-%d"))

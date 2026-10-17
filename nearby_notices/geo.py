"""Distances, units and the Gazette's radius steps.

Checked live on 17/10/2026: the Gazette's location filter only honours 1, 5, 10, 15, 20, 25 and 30 miles
(its own form offers exactly those). Any other value behaves like the step below it: 2 and 3 miles returned
the same 34 notices as 1 mile near Dudley. So the tool asks the Gazette for the smallest honoured radius that
covers what the user chose, then measures each notice itself against the nearest postcode it is filed under.
"""
from __future__ import annotations

import math

MILE_M = 1609.344
KM_M = 1000.0
UNITS = {"mi": {"name": "miles", "one": "mile", "metres": MILE_M, "choices": [1, 3, 5, 10, 15]},
         "km": {"name": "km", "one": "km", "metres": KM_M, "choices": [2, 5, 10, 15, 25]}}
GAZETTE_RADII_MILES = (1, 5, 10, 15, 20, 25, 30)


def unit_key(unit: str | None) -> str:
    return unit if unit in UNITS else "mi"


def choose_distance(distance: float | None, unit: str) -> int:
    """The user's distance snapped to the offered choices for the unit (the nearest one, so odd values never 404)."""
    choices = UNITS[unit_key(unit)]["choices"]
    try:
        d = float(distance)
    except (TypeError, ValueError):
        return choices[1]
    return min(choices, key=lambda c: abs(c - d))


def to_miles(distance: float, unit: str) -> float:
    return distance * UNITS[unit_key(unit)]["metres"] / MILE_M


def to_metres(distance: float, unit: str) -> float:
    return distance * UNITS[unit_key(unit)]["metres"]


def gazette_radius(miles: float) -> int:
    """The smallest radius the Gazette honours that covers the asked distance (capped at its largest)."""
    for r in GAZETTE_RADII_MILES:
        if r >= miles - 1e-9:
            return r
    return GAZETTE_RADII_MILES[-1]


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (haversine, mean Earth radius)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def nearest(points: list[dict], lat: float, lon: float) -> dict | None:
    """The filed point closest to the search centre, with its distance in metres added as 'm'."""
    best = None
    for p in points:
        try:
            m = distance_m(lat, lon, float(p["lat"]), float(p["lon"]))
        except (KeyError, TypeError, ValueError):
            continue
        if best is None or m < best["m"]:
            best = {**p, "m": m}
    return best


def fmt(metres: float, unit: str) -> str:
    """'0.2 miles', '1 mile', '3.4 km', 'under 0.1 km': one decimal, no trailing .0, never a bare zero."""
    u = UNITS[unit_key(unit)]
    v = metres / u["metres"]
    if v < 0.05:
        return f"under 0.1 {u['name']}"
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    return f"{s} {u['one'] if s == '1' else u['name']}"

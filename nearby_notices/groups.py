"""Friendly groups for display, decided from the notice code family, so grouping never depends on the model."""
from __future__ import annotations

from .categories import category_of

GROUPS: dict[str, dict] = {
    "roads": {"name": "Roads and transport", "categories": {15}, "colour": "#b45309"},
    "planning": {"name": "Planning", "categories": {16}, "colour": "#1d4ed8"},
    "environment": {"name": "Environment and water", "categories": {18, 19, 20}, "colour": "#047857"},
    "energy": {"name": "Energy", "categories": {21}, "colour": "#6d28d9"},
}
ORDER = ["roads", "planning", "environment", "energy", "other"]

# One simple line icon per group (16 by 16, stroked, drawn here so no icon library is loaded): a road, a building,
# a leaf, a lightning bolt, a document. Used on map pins, filter chips and card tags so list and map match.
ICONS: dict[str, str] = {
    "roads": "M3 15L6.5 1M13 15L9.5 1M8 3v2M8 7v2M8 11v2",
    "planning": "M2 14.5h12M3 14.5V6.5l5-4.5 5 4.5v8M6.5 14.5V10h3v4.5",
    "environment": "M3 13C3 7 7 3 13 3C13 9 9 13 3 13ZM3 13l6-6",
    "energy": "M9 1.5L3.5 9h4l-1 5.5L12.5 7h-4z",
    "other": "M4 1.5h5.5l3 3v10H4zM9.5 1.5v3h3M6 8h4M6 11h4",
}


def group_of(notice_code: int | str | None) -> str:
    cat = category_of(notice_code)
    for key, g in GROUPS.items():
        if cat in g["categories"]:
            return key
    return "other"


def group_name(key: str) -> str:
    return GROUPS.get(key, {}).get("name", "Other")


def group_colour(key: str) -> str:
    return GROUPS.get(key, {}).get("colour", "#52525b")

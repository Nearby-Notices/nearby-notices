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

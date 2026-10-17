"""Which Gazette notice categories this tool may touch.

The Gazette's notice data is reusable under the Open Government Licence v3, which "does not cover the
re-use of personal data". So only categories published by public bodies and companies acting as
authorities are allowed, and the categories that name private individuals are refused at every layer:
the fetcher never requests them, the store refuses to insert them, and a test proves both.
Category codes were read from the live feed on 17/10/2026 (categorycode=NN, first entry's notice code).
"""
from __future__ import annotations

ALLOWED: dict[int, str] = {
    15: "Transport",
    16: "Town and Country Planning",
    18: "Environmental Protection",
    19: "Water Resources",
    20: "Forestry and Plant Health",
    21: "Electricity",
}

# Never fetched, never stored, never shown. Kept explicit so the rule is visible and testable.
EXCLUDED: dict[int, str] = {
    11: "State: commissions and appointments (names individuals)",
    12: "Parliament and assemblies",
    13: "Marriage Acts (names individuals)",
    14: "National Savings (names individuals)",
    17: "Medicines",
    22: "Royal Mail",
    23: "Other notices (mixed; may name individuals)",
    24: "Corporate insolvency (out of scope by rule)",
    25: "Personal insolvency (names individuals; out of scope by rule)",
    26: "Deceased estates and Trustee Act notices (names individuals)",
    27: "Partnerships (names individuals)",
}


def category_of(notice_code: int | str | None) -> int | None:
    """A notice code such as 1501 belongs to category 15."""
    if notice_code is None:
        return None
    try:
        return int(str(notice_code)[:2])
    except ValueError:
        return None


def is_allowed(notice_code: int | str | None) -> bool:
    cat = category_of(notice_code)
    return cat in ALLOWED and cat not in EXCLUDED

"""The pure check, with no Inspect dependency: is a model's claim grounded in the source by its own quotes?

A claim is kept only if the model says it is supported, it offers at least one quote, every span of every quote is
really in the source (whole words, case and punctuation ignored; "a ... b" is two spans, each checked on its own),
and every number in the claim also appears in the quotes. The last rule catches the commonest grounded-looking
error: a true quote ("68m") offered for a claim with a different number ("75m").
"""
from __future__ import annotations

import json
import re

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def norm(s: str) -> str:
    s = (s or "").lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def numbers(s: str) -> set[str]:
    """'29m' -> '29', '1,000' -> '1000', '9th October 2026' -> {'9', '2026'}."""
    return {n.replace(",", "") for n in _NUMBER.findall(s or "")}


def spans(quotes: list[str], min_words: int = 2) -> list[str]:
    return [p.strip() for q in quotes for p in re.split(r"\.{3}|…", q) if len(p.split()) >= min_words]


def parse(reply: str) -> dict:
    """The model's reply as {"supported": bool, "quotes": [...]}; anything unreadable counts as unsupported."""
    m = re.search(r"\{.*\}", re.sub(r"<think>.*?</think>", "", reply or "", flags=re.DOTALL), re.DOTALL)
    try:
        d = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}
    return d if isinstance(d, dict) else {}


def decide(source: str, reply: str | dict, claim: str = "", min_words: int = 2) -> tuple[bool, list[str], str]:
    """Return (kept, quotes, reason)."""
    d = parse(reply) if isinstance(reply, str) else reply
    quotes = d.get("quotes")
    if not isinstance(quotes, list):
        quotes = [d.get("quote")] if d.get("quote") else []
    quotes = [str(q) for q in quotes if str(q or "").strip()][:3]
    if not d.get("supported"):
        return False, quotes, "model says unsupported"
    parts = spans(quotes, min_words)
    if not parts:
        return False, quotes, "no usable quote"
    src = f" {norm(source)} "
    missing = [p for p in parts if f" {norm(p)} " not in src]
    if missing:
        return False, quotes, f"quote not in source: {missing[0][:60]}"
    if claim:
        absent = numbers(claim) - set().union(*(numbers(q) for q in quotes))
        if absent:
            return False, quotes, f"number not in quotes: {sorted(absent)[0]}"
    return True, quotes, "grounded"

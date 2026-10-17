"""Plain English from legal notices, with every claim checked against the notice's own words.

Two model calls per notice through LiteLLM:
1. extract: a JSON record (what is changing, places, dates, authority, how to object) plus a two-sentence
   plain-English summary. Every place name must appear in the notice text or it is dropped.
2. gate: each summary sentence is judged "supported by the notice?" and must come back with a quote that
   really is in the text; sentences that fail are removed and counted. The model never writes advice.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

import litellm

from . import config

litellm.suppress_debug_info = True

EXTRACT_SYSTEM = (
    "You read UK public notices and return JSON only. Never give advice. Never invent. "
    "If a field is not stated in the notice, use null. Quote places exactly as written in the notice."
)
EXTRACT_USER = """Notice text:
\"\"\"
{text}
\"\"\"

Return a JSON object with exactly these keys:
- "what": one plain-English sentence (max 30 words) saying what is changing or proposed, for a resident.
- "places": list of road or place names affected, each copied exactly as written in the notice (max 8).
- "authority": the body that published the notice, as written, or null.
- "starts": the start date as written in the notice, or null.
- "ends": the end date or duration as written, or null.
- "kind": one of "road closure", "parking or waiting restriction", "speed limit", "one way or turning restriction", "footpath or bridleway", "planning application", "planning permission or order", "environmental permit", "water or drainage", "tree or forestry", "electricity or energy", "other".
- "objection": the sentence in the notice that says how or by when people may object or comment, copied exactly, or null.
- "summary": two or three short plain-English sentences a resident could read in ten seconds, saying only what the notice says.
/no_think"""

GATE_SYSTEM = "You check whether a sentence is supported by a notice. Return JSON only."
GATE_USER = """Notice text:
\"\"\"
{text}
\"\"\"

Sentence: "{sentence}"

Is every claim in the sentence stated in the notice text? Return JSON: {{"supported": true or false, "quote": "the exact words from the notice that support it, copied verbatim, or an empty string"}}
/no_think"""

_calls_today: dict[str, int] = {}


@dataclass
class Result:
    what: str | None = None
    places: list[str] = field(default_factory=list)
    authority: str | None = None
    starts: str | None = None
    ends: str | None = None
    kind: str | None = None
    objection: str | None = None
    summary: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    dropped_places: list[str] = field(default_factory=list)
    seconds: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _norm(s: str) -> str:
    s = (s or "").lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _in_text(fragment: str, text_norm: str) -> bool:
    f = _norm(fragment)
    return bool(f) and f in text_norm


def _cap() -> None:
    day = time.strftime("%Y-%m-%d")
    _calls_today.setdefault(day, 0)
    if _calls_today[day] >= config.DAILY_CALL_CAP:
        raise RuntimeError("daily model-call cap reached")
    _calls_today[day] += 1


def _ask(system: str, user: str, max_tokens: int) -> str:
    _cap()
    r = litellm.completion(
        model=config.MODEL, api_base=config.MODEL_API_BASE, api_key=config.MODEL_API_KEY,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0, max_tokens=max_tokens,
    )
    return r.choices[0].message.content or ""


def _json(s: str) -> dict:
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.DOTALL)
    m = re.search(r"\{.*\}", s, re.DOTALL)
    return json.loads(m.group(0)) if m else {}


def _sentences(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"(?<=[.!?])\s+", text.strip()) if p.strip()]


def gate(text: str, sentence: str, ask=_ask) -> tuple[bool, str]:
    """True only if the model says supported AND its quote is really in the notice."""
    try:
        d = _json(ask(GATE_SYSTEM, GATE_USER.format(text=text[:6000], sentence=sentence.replace('"', "'")), 200))
    except Exception:  # noqa: BLE001 (any model failure degrades to "unsupported", never to a guess)
        return False, ""
    quote = str(d.get("quote") or "")
    ok = bool(d.get("supported")) and _in_text(quote, _norm(text))
    return ok, quote


def extract(text: str, ask=_ask) -> Result:
    """The whole pipeline for one notice. `ask` is injectable so tests use a fake model."""
    t0 = time.time()
    res = Result()
    if len(text.split()) < 30:
        res.error = "no usable text"
        res.seconds = time.time() - t0
        return res
    try:
        d = _json(ask(EXTRACT_SYSTEM, EXTRACT_USER.format(text=text[:6000]), 600))
    except Exception as e:  # noqa: BLE001 the page says "no plain-English version available" and shows the notice verbatim
        res.error = f"model unavailable: {type(e).__name__}"
        res.seconds = time.time() - t0
        return res
    tn = _norm(text)
    res.what = (d.get("what") or None)
    for p in d.get("places") or []:
        (res.places if _in_text(str(p), tn) else res.dropped_places).append(str(p))
    res.authority = d.get("authority") or None
    res.starts, res.ends, res.kind = d.get("starts") or None, d.get("ends") or None, d.get("kind") or None
    obj = str(d.get("objection") or "")
    res.objection = obj if _in_text(obj, tn) else None
    summary = d.get("summary")
    sentences = _sentences(summary if isinstance(summary, str) else " ".join(summary or []))
    for s in sentences[:4]:
        ok, _ = gate(text, s, ask)
        (res.summary if ok else res.removed).append(s)
    if res.what and not res.summary:
        ok, _ = gate(text, res.what, ask)
        if not ok:
            res.removed.append(res.what)
            res.what = None
    res.seconds = round(time.time() - t0, 2)
    return res

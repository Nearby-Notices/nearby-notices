"""The notice-kind classifier at run time: every notice gets its kind (road closure, parking or waiting restriction,
speed limit, planning application...) at search time, with no model call.

Only a notice that has been read has a kind from the language model. This small classifier (word and character
n-grams, logistic regression; trained and tested by evals/kinds/build.py, results in evals/kinds/RESULTS.md) gives
one to every notice, so results can be filtered by kind straight away. features() is shared with the training code,
so the model always sees exactly what it was trained on.

Monitoring: each time the language model writes a summary with a kind, record() compares it with the classifier's
kind for the same notice. status() turns the classifier off (WINDOW comparisons below FLOOR agreement), and the About
page says so, until it is retrained. Rules fixed before training in evals/kinds/PREREGISTRATION.md.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

MODEL_PATH = Path(__file__).parent / "models" / "kinds.joblib"
WINDOW, FLOOR = 50, 0.70
_lock = threading.Lock()
_loaded: dict | None = None


def features(n: dict) -> str:
    """What the model reads: the notice code and its category as tokens, the title, and the first 400 words of the
    scrubbed text. Shared with evals/kinds/build.py."""
    from .extract import scrub
    text, _ = scrub(n.get("text") or "")
    return f"code{n.get('notice_code')} cat{str(n.get('notice_code'))[:2]} {n.get('title') or ''} " + " ".join(text.split()[:400])


def _bundle() -> dict:
    global _loaded
    with _lock:
        if _loaded is None:
            if MODEL_PATH.exists():
                import joblib
                _loaded = joblib.load(MODEL_PATH)
            else:
                _loaded = {}
        return _loaded


def info() -> dict:
    """When the shipped model was trained, on how many notices, and its held-out accuracy."""
    b = _bundle()
    return {k: b.get(k) for k in ("trained", "train_size", "held_out_accuracy")} if b else {}


def predict(rows: list[dict]) -> list[str | None]:
    model = _bundle().get("model")
    if model is None or not rows:
        return [None] * len(rows)
    return [str(k) for k in model.predict([features(r) for r in rows])]


def record(con, row: dict, llm_kind: str | None) -> None:
    """Compare the classifier with the language model's kind for a notice that has just been read."""
    if not llm_kind:
        return
    mine = predict([row])[0]
    if mine is None:
        return
    con.execute("INSERT INTO kind_checks (at, notice_id, model_kind, llm_kind, agree) VALUES (?, ?, ?, ?, ?)",
                (time.time(), row["id"], mine, llm_kind, int(mine == llm_kind)))


def status(con) -> dict:
    """Live agreement with the language model: over the last WINDOW comparisons, and in all. Off below FLOOR."""
    last = [r[0] for r in con.execute("SELECT agree FROM kind_checks ORDER BY at DESC LIMIT ?", (WINDOW,))]
    total, agreed = con.execute("SELECT COUNT(*), COALESCE(SUM(agree), 0) FROM kind_checks").fetchone()
    on = bool(_bundle().get("model")) and (len(last) < WINDOW or sum(last) / len(last) >= FLOOR)
    return {"on": on, "recent": len(last), "recent_agree": sum(last), "total": total, "agreed": agreed, **info()}

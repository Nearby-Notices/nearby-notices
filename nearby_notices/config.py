"""Settings, all from environment variables with safe defaults. No secrets live in code."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MODEL = os.environ.get("NN_MODEL", "openai/local")
MODEL_API_BASE = os.environ.get("NN_MODEL_API_BASE", "http://127.0.0.1:8696/v1")
MODEL_API_KEY = os.environ.get("NN_MODEL_API_KEY", "local")
MODEL_API_VERSION = os.environ.get("NN_MODEL_API_VERSION", "")   # Azure OpenAI needs one, for example 2024-10-21
MODEL_DISCOVERED = False


def discover_model() -> str:
    """Name the model honestly. A local OpenAI-compatible server (llama-server, Ollama, a proxy) ignores the model
    field and serves whatever it has loaded, so unless NN_MODEL was set the name recorded with every plain-English
    version is read from the server's own model list (only when it lists exactly one). Called once at startup."""
    global MODEL, MODEL_DISCOVERED
    if MODEL_DISCOVERED or "NN_MODEL" in os.environ:
        MODEL_DISCOVERED = True
        return MODEL
    MODEL_DISCOVERED = True
    try:
        import httpx

        r = httpx.get(f"{MODEL_API_BASE.rstrip('/')}/models", headers={"Authorization": f"Bearer {MODEL_API_KEY}"}, timeout=2)
        items = r.json().get("data") or []
        if len(items) == 1 and items[0].get("id"):
            name = str(items[0]["id"]).replace("\\", "/").rsplit("/", 1)[-1]
            name = name[:-5] if name.lower().endswith(".gguf") else name
            MODEL = f"openai/{name}"
    except Exception as e:  # noqa: BLE001 no server, or not OpenAI-shaped: keep the configured name
        MODEL_DISCOVERY_NOTE = f"model name not discovered ({type(e).__name__}); using {MODEL}"
        globals()["MODEL_DISCOVERY_NOTE"] = MODEL_DISCOVERY_NOTE
    return MODEL
DAILY_CALL_CAP = int(os.environ.get("NN_DAILY_CALL_CAP", "2000"))

DB_PATH = Path(os.environ.get("NN_DB_PATH", ROOT / "data" / "notices.sqlite"))
DB_JOURNAL = "DELETE" if os.environ.get("NN_DB_JOURNAL", "WAL").upper() == "DELETE" else "WAL"
USER_AGENT = os.environ.get("NN_USER_AGENT", "NearbyNotices/0.1 (open-source civic tool; contact via the repository)")
GAZETTE_BASE = "https://www.thegazette.co.uk"
POSTCODES_BASE = "https://api.postcodes.io"
DEFAULT_DISTANCE_MILES = int(os.environ.get("NN_DEFAULT_DISTANCE", "3"))
# How far back a search looks. Every notice published in the window is shown; the default is what is current:
# most objection periods run three to four weeks, so a month covers the notices people can still act on.
SINCE_CHOICES = {7: "the past week", 30: "the past month", 90: "the past 3 months", 365: "the past year"}
DEFAULT_SINCE_DAYS = int(os.environ.get("NN_DEFAULT_SINCE_DAYS", "30"))
# Summaries are written on demand: the first few of a search at once, then each notice as it comes into view
# (or its pin is opened). Each summary is written once and kept for everyone, so nothing is paid for twice.
FIRST_SUMMARIES = int(os.environ.get("NN_FIRST_SUMMARIES", "6"))
READERS = int(os.environ.get("NN_READERS", "4"))   # summaries written side by side; set 1 for a single local model
FEED_CACHE_SECONDS = int(os.environ.get("NN_FEED_CACHE_SECONDS", "3600"))
SEARCHES_PER_MINUTE = int(os.environ.get("NN_SEARCHES_PER_MINUTE", "10"))   # per client; a public endpoint should keep this low
# The GitHub Pages front, which shows this site in a frame for networks that block newly registered domains.
# It is the only other site allowed to frame this one.
PAGES_FRONT = os.environ.get("NN_PAGES_FRONT", "https://nearby-notices.github.io")
COUNTER_URL = os.environ.get("NN_COUNTER_URL", "")   # daily totals that survive restarts (see counter.py); off when empty

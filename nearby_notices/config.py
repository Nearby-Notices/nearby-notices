"""Settings, all from environment variables with safe defaults. No secrets live in code."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MODEL = os.environ.get("NN_MODEL", "openai/qwen3.8-27b")
MODEL_API_BASE = os.environ.get("NN_MODEL_API_BASE", "http://127.0.0.1:8696/v1")
MODEL_API_KEY = os.environ.get("NN_MODEL_API_KEY", "local")
DAILY_CALL_CAP = int(os.environ.get("NN_DAILY_CALL_CAP", "2000"))

DB_PATH = Path(os.environ.get("NN_DB_PATH", ROOT / "data" / "notices.sqlite"))
USER_AGENT = os.environ.get("NN_USER_AGENT", "NearbyNotices/0.1 (open-source civic tool; contact via the repository)")
GAZETTE_BASE = "https://www.thegazette.co.uk"
POSTCODES_BASE = "https://api.postcodes.io"
DEFAULT_DISTANCE_MILES = int(os.environ.get("NN_DEFAULT_DISTANCE", "3"))
MAX_RESULTS = int(os.environ.get("NN_MAX_RESULTS", "12"))
FEED_CACHE_SECONDS = int(os.environ.get("NN_FEED_CACHE_SECONDS", "3600"))

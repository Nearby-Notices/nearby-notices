import pytest

from nearby_notices import app as webapp
from nearby_notices import ratelimit


@pytest.fixture(autouse=True)
def _fresh_rate_limit(monkeypatch):
    """Every test starts with an empty per-minute counter and a limit no test can hit by accident."""
    ratelimit._hits.clear()
    monkeypatch.setitem(webapp.LIMITS, "/search", 1000)
    yield
    ratelimit._hits.clear()

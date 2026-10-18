"""The per-minute limit keeps no addresses and forgets clients after a minute."""
from nearby_notices import ratelimit


def test_limit_counts_per_client_and_forgets_after_a_minute():
    t = 1000.0
    assert all(ratelimit.allow("203.0.113.5", 3, now=t + i) for i in range(3))
    assert not ratelimit.allow("203.0.113.5", 3, now=t + 3), "the fourth request in a minute is refused"
    assert ratelimit.allow("203.0.113.6", 3, now=t + 3), "another client is unaffected"
    assert ratelimit.allow("203.0.113.5", 3, now=t + 61), "a minute later the client is allowed again"


def test_no_address_is_stored():
    ratelimit.allow("198.51.100.7", 5)
    keys = " ".join(ratelimit._hits.keys())
    assert "198.51.100.7" not in keys and all(len(k) == 24 for k in ratelimit._hits)


def test_search_returns_429_when_over_the_limit(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from nearby_notices import app as webapp
    from nearby_notices import config, places, worker

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite")
    monkeypatch.setattr(worker, "enqueue", lambda ids: None)
    monkeypatch.setattr(worker, "warm_up", lambda limit=60: 0)
    monkeypatch.setattr(places, "resolve", lambda q, client=None: None)
    monkeypatch.setitem(webapp.LIMITS, "/search", 2)
    c = TestClient(webapp.app)
    assert c.get("/search", params={"place": "x"}).status_code == 200
    assert c.get("/search", params={"place": "x"}).status_code == 200
    r = c.get("/search", params={"place": "x"})
    assert r.status_code == 429 and r.headers["retry-after"] == "60"
    assert c.get("/health").status_code == 200, "other routes are not limited"

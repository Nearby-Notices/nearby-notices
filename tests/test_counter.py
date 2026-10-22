"""The daily counter: off unless configured, counts by reading then writing with the row's ETag, retries a race."""
import httpx

from nearby_notices import config, counter

URL = "https://acct.table.core.windows.net/counters?sv=x&sig=y"


def table(start=None, race=False):
    """A stand-in for the Azure Table: one row, ETags that change on every write, and an optional lost race."""
    state = {"n": start, "etag": 'W/"1"', "raced": not race}

    def handle(req: httpx.Request) -> httpx.Response:
        if req.method == "GET":
            if state["n"] is None:
                return httpx.Response(404)
            return httpx.Response(200, json={"n": state["n"]}, headers={"ETag": state["etag"]})
        if req.method == "POST":
            if state["n"] is not None:
                return httpx.Response(409)
            state["n"] = 1
            return httpx.Response(204)
        if req.method == "PUT":
            if not state["raced"]:                    # someone else wrote first: the ETag no longer matches
                state["raced"], state["n"], state["etag"] = True, state["n"] + 1, 'W/"race"'
                return httpx.Response(412)
            assert req.headers["If-Match"] == state["etag"]
            state["n"] = int(httpx.Response(200, content=req.content).json()["n"])
            state["etag"] = f'W/"{state["n"]}"'
            return httpx.Response(204)
        return httpx.Response(405)
    return state, httpx.Client(transport=httpx.MockTransport(handle))


def test_first_count_of_the_day_creates_the_row():
    state, client = table()
    assert counter.increment("search", "2026-10-22", URL, client) == 1 and state["n"] == 1


def test_later_counts_add_one():
    _, client = table(start=41)
    assert counter.increment("search", "2026-10-22", URL, client) == 42


def test_a_lost_race_is_retried_not_lost():
    _, client = table(start=10, race=True)
    assert counter.increment("search", "2026-10-22", URL, client) == 12   # the other writer's 11, then ours


def test_off_unless_configured(monkeypatch):
    monkeypatch.setattr(config, "COUNTER_URL", "")
    submitted = []
    monkeypatch.setattr(counter._pool, "submit", lambda *a: submitted.append(a))
    counter.count("search")
    assert submitted == [] and counter.increment("search", "2026-10-22", "", httpx.Client()) is None

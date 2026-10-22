"""Every notice in the chosen time window is shown, with no cap; summaries are written on demand (the first few
with the page, the rest as they come into view), several side by side, most urgent first."""
import datetime

import pytest
from fastapi.testclient import TestClient

from nearby_notices import app as webapp
from nearby_notices import config, gazette, places, worker

CENTRE = (52.5092, -2.0835)   # DY1 1HF
TEXT = "ROAD TRAFFIC REGULATION ACT 1984. " + "The Council has made an Order affecting Priory Road. " * 12


def notice(nid):
    return gazette.Notice(id=nid, title=f"Notice {nid}", category="Road Traffic Acts", notice_code=1501,
                          published=f"2026-10-{1 + int(nid) % 20:02d}", text=TEXT, url=f"https://example.invalid/{nid}",
                          lat=52.5122, lon=-2.0843)


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite")
    queued, asked = [], []
    monkeypatch.setattr(worker, "enqueue", lambda ids, priority=worker.SOON: queued.append((list(ids), priority)))
    monkeypatch.setattr(places, "resolve", lambda q, client=None: places.Place(q, "DY1 1HF", "Dudley, West Midlands", *CENTRE))
    feed = [notice(str(i)) for i in range(1, 31)]          # thirty notices, all within the distance
    monkeypatch.setattr(gazette, "search_near", lambda postcode, miles, client=None, on_category=None, **kw: asked.append(kw) or list(feed))
    c = TestClient(webapp.app)
    c.queued, c.asked = queued, asked
    return c


def test_every_notice_in_the_window_is_shown_with_no_cap(site):
    page = site.get("/search", params={"place": "Dudley", "distance": 3, "unit": "mi"}).text
    assert sum(f'id="n{i}"' in page for i in range(1, 31)) == 30, "all thirty notices are on the page"
    assert "published in the past month" in page
    month_ago = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    assert site.asked[-1]["since"] == month_ago, "the Gazette is asked only for notices published in the window"


def test_the_window_can_be_changed_and_an_odd_value_falls_back_to_a_month(site):
    page = site.get("/search", params={"place": "Dudley", "distance": 3, "unit": "mi", "since": 365}).text
    assert "published in the past year" in page and '<option value="365" selected>' in page
    year_ago = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()
    assert site.asked[-1]["since"] == year_ago
    assert "published in the past month" in site.get("/search", params={"place": "Dudley", "since": 12345}).text


def test_only_the_first_few_summaries_are_queued_with_the_page(site):
    site.get("/search", params={"place": "Dudley", "distance": 3, "unit": "mi"})
    ids, priority = site.queued[-1]
    assert len(ids) == config.FIRST_SUMMARIES and priority == worker.SOON, "the rest wait until someone looks at them"


def test_notices_on_screen_are_queued_first(site):
    assert site.get("/status", params={"ids": "1,2", "want": "7,8,bad;id"}).json() == {"ready": [], "pending": ["1", "2"]}
    assert site.queued[-1] == (["7", "8"], worker.NOW)


def test_a_queued_notice_moves_up_when_it_is_needed_sooner(monkeypatch):
    monkeypatch.setattr(worker, "start", lambda: None)
    monkeypatch.setattr(worker, "_q", worker.queue.PriorityQueue())
    monkeypatch.setattr(worker, "_pending", {})
    worker.enqueue(["a"], worker.LATER)
    worker.enqueue(["a"], worker.NOW)
    worker.enqueue(["a"], worker.SOON)          # already queued more urgently: nothing changes
    assert worker._pending == {"a": worker.NOW} and worker._q.qsize() == 2
    assert worker._q.get()[0] == worker.NOW


def test_the_gazette_client_reads_every_page_of_a_busy_category(monkeypatch):
    calls = []

    class Answer:
        def __init__(self, page):
            self.page = page

        def json(self):
            start = (self.page - 1) * 100
            n = min(100, 250 - start)
            return {"f:total": "250", "entry": [{"id": f"https://x/notice/{start + i}", "f:notice-code": "1501", "title": "t",
                                                 "published": "2026-10-01", "content": "<p>text</p>"} for i in range(n)]}

    def polite(client, url, params=None, timeout=20):
        calls.append((params["categorycode"], params["results-page"], params.get("start-publish-date")))
        return Answer(params["results-page"]) if params["categorycode"] == 15 else type("Empty", (), {"json": lambda self: {"f:total": "0"}})()

    monkeypatch.setattr(gazette, "_polite_get", polite)
    found = gazette.search_near("DY1 1HF", 5, client=object(), since="2026-09-22")
    assert len(found) == 250, "all three pages of the busy category are read"
    assert sorted(p for c, p, _ in calls if c == 15) == [1, 2, 3]
    assert all(s == "2026-09-22" for _, _, s in calls)


def test_a_summary_that_failed_when_the_model_was_busy_is_tried_again_later(tmp_path, monkeypatch):
    from nearby_notices import store
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite")
    with store.db() as con:
        store.put_extraction(con, "9", "m", {"error": "model unavailable: RateLimitError"}, 0, 0, 0.0)
        store.put_extraction(con, "8", "m", {"error": "no usable text"}, 0, 0, 0.0)
        assert store.get_extraction(con, "9", "m") is not None, "a fresh failure is shown as a failure"
        con.execute("UPDATE extractions SET created_at = created_at - 3600")
        assert store.get_extraction(con, "9", "m") is None, "an hour later it counts as not written, so it is written again"
        assert store.get_extraction(con, "8", "m") == {"error": "no usable text"}, "a notice with no usable text is not retried"


def test_a_notice_under_another_countrys_law_is_not_shown_for_a_place_it_was_only_filed_near():
    from nearby_notices import search
    london = places.Place("London", "WC2N 5DU", "London", 51.5074, -0.1278, "England")
    perth = places.Place("Perth", "PH1 5PH", "Perth", 56.3960, -3.4370, "Scotland")
    wind = {"title": "Electricity", "text": "ENERGIEKONTOR UK LTD ELECTRICITY ACT 1989 TOWN AND COUNTRY PLANNING (SCOTLAND) ACT 1997 ... the Scottish Ministers"}
    road = {"title": "Road Traffic Acts", "text": "Westminster City Council ... Road Traffic Regulation Act 1984"}
    planning = {"title": "Town and Country Planning", "text": "notice under section 247 of the Town and Country Planning Act 1990"}
    assert search.jurisdiction(wind["text"]) == "Scotland"
    assert not search.same_country(wind, london), "a Scottish wind farm filed under a London office stays out of a London search"
    assert search.same_country(wind, perth)
    assert search.same_country(road, london) and search.same_country(road, perth), "a UK-wide Act says nothing about the country"
    assert not search.same_country(planning, perth) and search.same_country(planning, london)
    assert search.same_country(wind, places.Place("x", "", "x", 1, 1)), "an unknown country filters nothing"

"""The pages, without the network: a search keeps only notices filed within the chosen distance, the status
and card endpoints let the page update without reloading, and the unit choice is honoured."""
import pytest
from fastapi.testclient import TestClient

from nearby_notices import app as webapp
from nearby_notices import config, gazette, geo, places, store, worker

CENTRE = (52.5092, -2.0835)   # DY1 1HF
NEAR_M = geo.distance_m(*CENTRE, 52.5097, -2.0879)   # to DY1 1RY, about 300 m
TEXT = "ROAD TRAFFIC REGULATION ACT 1984. " + "The Council has made an Order affecting Priory Road. " * 12


def notice(nid, lat, lon):
    return gazette.Notice(id=nid, title=f"Notice {nid}", category="Road Traffic Acts", notice_code=1501,
                          published="2026-10-01", text=TEXT, url=f"https://example.invalid/{nid}", lat=lat, lon=lon)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite")
    monkeypatch.setattr(worker, "enqueue", lambda ids: None)          # no model in tests
    monkeypatch.setattr(places, "resolve", lambda q, client=None: places.Place(q, "DY1 1HF", "Dudley, West Midlands", *CENTRE) if q else None)
    asked = []
    feed = [notice("1", 52.5122, -2.0843),      # filed 0.3 km away
            notice("2", 52.1853, -2.1797),      # feed point is a Worcester office, but also filed under a Dudley postcode
            notice("3", 52.0, -2.0)]            # genuinely far, nothing nearer
    monkeypatch.setattr(gazette, "search_near", lambda postcode, miles, page_size=10, client=None, on_category=None: asked.append(miles) or list(feed))
    jsonld = {"2": [{"postcode": "WR5 2QT", "lat": 52.1853, "lon": -2.1797}, {"postcode": "DY1 1RY", "lat": 52.5097, "lon": -2.0879}],
              "3": [{"postcode": "GL1 1AA", "lat": 52.0, "lon": -2.0}]}
    looked_up = []
    monkeypatch.setattr(gazette, "points", lambda nid, client=None: looked_up.append(nid) or jsonld[nid])
    c = TestClient(webapp.app)
    c.asked, c.looked_up = asked, looked_up
    return c


def test_search_asks_an_honoured_radius_then_keeps_only_notices_filed_within_the_distance(client):
    page = client.get("/search", params={"place": "Dudley", "distance": 3, "unit": "mi"}).text
    assert client.asked == [5], "3 miles is not a radius the Gazette honours; it must ask for 5 and measure"
    assert client.looked_up == ["2", "3"], "only notices whose feed point is outside the circle need the full record"
    assert 'id="n1"' in page and 'id="n2"' in page and 'id="n3"' not in page
    assert "Within 3 miles of DY1 1HF" in page
    assert f"{geo.fmt(NEAR_M, 'mi')} away (DY1 1RY)" in page
    assert 'http-equiv="refresh"' not in page


def test_kilometres_are_converted_and_shown(client):
    page = client.get("/search", params={"place": "Dudley", "distance": 5, "unit": "km"}).text
    assert client.asked == [5]                      # 5 km is 3.1 miles, so the Gazette is asked for 5 miles
    client.get("/search", params={"place": "Dudley", "distance": 3, "unit": "mi"})
    assert client.asked == [5] and client.looked_up == ["2", "3"], "a second distance inside the same Gazette radius reuses the cached feed and the stored points"
    assert "Within 5 km of DY1 1HF" in page and f"{geo.fmt(NEAR_M, 'km')} away (DY1 1RY)" in page
    assert '<option value="5" selected>5</option>' in page and '<option value="km" selected>km</option>' in page


def test_map_points_sit_at_the_nearest_filed_postcode(client):
    page = client.get("/search", params={"place": "Dudley", "distance": 3, "unit": "mi", "view": "map"}).text
    assert '"postcode": "DY1 1RY"' in page and "WR5 2QT" not in page, "the popup shows the nearest filed postcode only"
    assert '"outside": false' in page and '"outside": true' not in page
    assert "L.circle(centre, {radius: 4828.03" in page


def test_status_and_card_let_the_page_update_in_place(client):
    client.get("/search", params={"place": "Dudley", "distance": 3, "unit": "mi"})
    assert client.get("/status", params={"ids": "1,2,zz;drop"}).json() == {"ready": [], "pending": ["1", "2"]}
    with store.db() as con:
        store.put_extraction(con, "1", config.MODEL, {"what": "No waiting on Priory Road", "summary": ["One."], "removed": [], "places": ["Priory Road"],
                                                       "dropped_places": [], "authority": "Dudley Council"}, 1, 0, 1.0)
    assert client.get("/status", params={"ids": "1,2"}).json() == {"ready": ["1"], "pending": ["2"]}
    card = client.get("/card/1", params={"back": "/search?place=Dudley", "unit": "km", "lat": CENTRE[0], "lon": CENTRE[1]}).text
    assert card.startswith(("\n<article", "<article"))
    assert "No waiting on Priory Road" in card and 'value="/search?place=Dudley"' in card
    assert f"{geo.fmt(geo.distance_m(*CENTRE, 52.5122, -2.0843), 'km')} away" in card
    assert client.get("/card/999").status_code == 404 and client.get("/card/not-an-id").status_code == 404


def test_unknown_place_shows_the_form_again(client):
    page = client.get("/search", params={"place": ""}).text
    assert "I could not find that place" in page


def test_warm_up_queues_cached_searches_that_lack_plain_english(client, monkeypatch):
    client.get("/search", params={"place": "Dudley", "distance": 3, "unit": "mi"})
    queued = []
    monkeypatch.setattr(worker, "enqueue", lambda ids: queued.extend(ids))
    assert worker.warm_up() == 3 and sorted(queued) == ["1", "2", "3"], "every notice of a cached search lacks a version, including the one outside this distance"
    with store.db() as con:
        store.put_extraction(con, "1", config.MODEL, {"what": "x", "summary": [], "removed": []}, 0, 0, 0.0)
    queued.clear()
    assert worker.warm_up() == 2 and sorted(queued) == ["2", "3"]


def test_the_map_is_the_default_view(client):
    page = client.get("/search", params={"place": "Dudley", "distance": 3, "unit": "mi"}).text
    assert 'id="map"' in page and "L.map('map'" in page, "no view parameter means the map view"
    assert 'id="n1"' in page, "the list still follows the map"
    assert 'id="map"' not in client.get("/search", params={"place": "Dudley", "distance": 3, "unit": "mi", "view": "all"}).text


def test_progress_reports_each_step_without_keeping_what_was_typed(client):
    from nearby_notices import progress
    assert client.get("/progress", params={"place": "nowhere yet"}).json() == {"stage": None}
    r = client.get("/search", params={"place": "DY1 1HF", "distance": 3, "unit": "mi"})
    assert r.status_code == 200
    assert client.get("/progress", params={"place": "DY1 1HF"}).json() == {"stage": None}   # cleared once the page is built
    report = progress.reporter("DY1 1HF")
    report("text", 3, 6)
    s = client.get("/progress", params={"place": "  dy1   1hf "}).json()      # same place however it is typed
    assert s["stage"] == "text" and s["label"] == "Fetching notices: 3 of 6" and s["percent"] == 50
    assert all("DY1" not in k.upper() for k in progress._entries)            # only a hash is kept


def test_progress_percent_fills_each_stage_in_order():
    from nearby_notices import progress
    assert progress.percent("place") == 0
    assert progress.percent("feed", 3, 6) == 22
    assert progress.percent("text", 0, 0) == 40 and progress.percent("points", 4, 4) == 95
    assert progress.percent("done") == 100

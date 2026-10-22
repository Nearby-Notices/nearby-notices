"""The food hygiene layer: both rating schemes banded, private-home businesses left out, the endpoint guarded."""
import httpx

from nearby_notices import food


def business(rating, scheme="FHRS", address="1 High Street", lat="56.39", lon="-3.43"):
    return {"FHRSID": 1, "BusinessName": "Cafe", "BusinessType": "Restaurant/Cafe/Canteen", "AddressLine1": address,
            "AddressLine2": "", "AddressLine3": "", "AddressLine4": "", "PostCode": "PH1 5AA", "RatingValue": rating,
            "SchemeType": scheme, "RatingDate": "2026-01-02T00:00:00", "geocode": {"latitude": lat, "longitude": lon}}


def test_both_schemes_are_banded():
    assert [food.band(r) for r in ("5", "4", "3", "2", "0")] == ["good", "good", "fair", "poor", "poor"]
    assert [food.band(r) for r in ("Pass", "Improvement Required", "Awaiting Inspection", "Exempt")] == ["good", "poor", "other", "other"]


def test_private_home_businesses_and_unlocated_ones_are_left_out():
    assert food.slim(business("5"))["address"] == "1 High Street, PH1 5AA"
    assert food.slim(business("5", address="")) is None                 # the FSA withholds a private home's address
    assert food.slim(business("5", lat=None)) is None


def test_near_asks_the_fsa_once_per_point_and_keeps_the_answer(monkeypatch):
    calls = []

    def handle(req):
        calls.append(req)
        assert req.headers["x-api-version"] == "2"
        return httpx.Response(200, json={"establishments": [business("Pass", "FHIS"), business("1", address="")]})
    client = httpx.Client(transport=httpx.MockTransport(handle))
    food._cache.clear()
    first = food.near(56.3950, -3.4308, 3, client)
    again = food.near(56.3950, -3.4308, 3, client)
    assert len(first) == 1 and first[0]["band"] == "good" and again == first and len(calls) == 1


def test_endpoint_refuses_points_outside_the_uk_and_reports_an_fsa_outage(monkeypatch):
    from fastapi.testclient import TestClient

    from nearby_notices import app as webapp
    c = TestClient(webapp.app)
    assert c.get("/food", params={"lat": 48.85, "lon": 2.35}).status_code == 400
    monkeypatch.setattr(food, "near", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("down")))
    r = c.get("/food", params={"lat": 56.395, "lon": -3.43, "distance": 3, "unit": "mi"})
    assert r.status_code == 503 and r.json()["items"] == []

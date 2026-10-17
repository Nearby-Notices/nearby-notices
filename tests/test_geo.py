"""Distances and units: the Gazette only honours certain radii, so the tool rounds up and measures for itself."""
from nearby_notices import gazette, geo


def test_gazette_radius_rounds_up_to_an_honoured_step():
    assert [geo.gazette_radius(m) for m in (1, 3, 5, 6.2, 15, 40)] == [1, 5, 5, 10, 15, 30]
    assert geo.gazette_radius(geo.to_miles(2, "km")) == 5     # 2 km is 1.24 miles, so the Gazette is asked for 5


def test_choose_distance_snaps_to_the_offered_choices():
    assert geo.choose_distance("3", "mi") == 3
    assert geo.choose_distance(3, "km") == 2
    assert geo.choose_distance(None, "km") == 5
    assert geo.choose_distance("abc", "mi") == 3
    assert geo.choose_distance(3, "furlongs") == 3        # unknown unit falls back to miles


def test_format_and_convert():
    assert geo.fmt(321, "mi") == "0.2 miles"
    assert geo.fmt(1609.344, "mi") == "1 mile"
    assert geo.fmt(1000, "km") == "1 km"
    assert geo.fmt(3400, "km") == "3.4 km"
    assert geo.fmt(30, "mi") == "under 0.1 miles"
    assert abs(geo.to_metres(3, "mi") - 4828.03) < 0.1 and geo.to_metres(5, "km") == 5000


def test_distance_is_great_circle():
    km = geo.distance_m(51.5074, -0.1278, 48.8566, 2.3522) / 1000   # London to Paris
    assert 340 < km < 347


JSONLD = {"@graph": [
    {"@id": "https://www.thegazette.co.uk/id/notice/1#notifiableThing", "@type": ["transport:TransportThing"],
     "postcode": ["https://www.thegazette.co.uk/id/postcode/B693DE", "https://www.thegazette.co.uk/id/postcode/DY11RY"]},
    {"@id": "https://www.thegazette.co.uk/id/postcode/B693DE", "lat": "52.504007", "long": "-2.009055"},
    {"@id": "https://www.thegazette.co.uk/id/postcode/DY11RY", "lat": "52.509746", "long": "-2.087869"},
    {"@id": "https://www.thegazette.co.uk/id/postcode/DY11RY", "lat": "52.509746", "long": "-2.087869"},   # duplicate node
    {"@id": "https://www.thegazette.co.uk/id/postcode/BROKEN", "lat": "n/a"},
    {"@id": "http://www.legislation.gov.uk/id/ukpga/1980/66", "label": "Highways Act 1980"},
]}


def test_points_from_jsonld_reads_every_filed_postcode_and_nothing_else():
    pts = gazette.points_from_jsonld(JSONLD)
    assert [p["postcode"] for p in pts] == ["B69 3DE", "DY1 1RY"]
    assert pts[1]["lat"] == 52.509746 and pts[1]["lon"] == -2.087869
    assert all(set(p) == {"postcode", "lat", "lon"} for p in pts)


def test_nearest_point_wins_and_the_feed_point_is_the_fallback():
    pts = gazette.points_from_jsonld(JSONLD)
    near = geo.nearest(pts, 52.5092, -2.0835)                   # Dudley town centre
    assert near["postcode"] == "DY1 1RY" and near["m"] < 400
    n = gazette.Notice(id="1", title="t", category="c", notice_code=1501, published="2026-01-01", text="x", url="u", lat=52.504007, lon=-2.009055)
    assert n.all_points() == [{"postcode": None, "lat": 52.504007, "lon": -2.009055}]
    n.points = pts
    assert n.all_points() is pts


def test_every_group_has_an_icon():
    from nearby_notices import groups
    assert set(groups.ICONS) == set(groups.ORDER)
    assert all(d.startswith("M") for d in groups.ICONS.values())

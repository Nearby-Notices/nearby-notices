"""The MCP server exposes the same index under the same rules: find near a place, read one notice with its verbatim
text and checked plain English, say what is covered and refused. No network, no model."""
import asyncio
import inspect

import pytest

from nearby_notices import config, extract, gazette, mcp_server, places, store, worker

CENTRE = (52.5092, -2.0835)
TEXT = "ROAD TRAFFIC REGULATION ACT 1984. " + "The Council has made an Order affecting Priory Road. " * 12


def notice(nid, lat, lon):
    return gazette.Notice(id=nid, title=f"Notice {nid}", category="Road Traffic Acts", notice_code=1501,
                          published="2026-10-01", text=TEXT, url=f"https://example.invalid/{nid}", lat=lat, lon=lon)


@pytest.fixture
def offline(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.sqlite")
    monkeypatch.setattr(worker, "enqueue", lambda ids: None)
    monkeypatch.setattr(worker, "is_pending", lambda nid: False)
    monkeypatch.setattr(places, "resolve", lambda q, client=None: places.Place(q, "DY1 1HF", "Dudley, West Midlands", *CENTRE) if q != "nowhere" else None)
    monkeypatch.setattr(gazette, "search_near", lambda postcode, miles, page_size=10, client=None, on_category=None: [notice("1", 52.5122, -2.0843), notice("3", 52.0, -2.0)])
    monkeypatch.setattr(gazette, "points", lambda nid, client=None: [{"postcode": "GL1 1AA", "lat": 52.0, "lon": -2.0}])
    calls = []
    monkeypatch.setattr(extract, "extract", lambda text, ask=None: calls.append(text) or extract.Result(
        what="No waiting on Priory Road", places=["Priory Road"], authority="Dudley Council", kind="parking restriction",
        objection="Objections may be sent to the Council within 21 days of this notice.", summary=["No waiting on Priory Road."],
        removed=["There will be fireworks."], seconds=1.0))
    return calls


def test_find_returns_only_notices_inside_the_distance_with_no_personal_fields(offline):
    out = mcp_server.find_notices_near("Dudley", 3, "mi")
    assert out["postcode"] == "DY1 1HF" and out["within"] == "3 miles" and out["count"] == 1
    n = out["notices"][0]
    assert n["notice_id"] == "1" and n["kind"] == "Roads and transport" and n["plain_english_ready"] is False
    assert n["url"].startswith("https://") and n["distance"].endswith("miles") and n["filed_postcode"] is None
    assert set(n) == {"notice_id", "kind", "category", "published", "title", "distance", "filed_postcode", "plain_english_ready", "url"}
    assert mcp_server.find_notices_near("nowhere")["notices"] == [] and "error" in mcp_server.find_notices_near("nowhere")


def test_read_makes_the_plain_english_now_and_keeps_the_record(offline):
    mcp_server.find_notices_near("Dudley", 3, "mi")
    out = mcp_server.read_notice("1")
    assert offline == [TEXT], "the model is asked once, with the notice text"
    assert out["as_published"] == TEXT and out["url"] == "https://example.invalid/1"
    pe = out["plain_english"]
    assert pe["what"] == "No waiting on Priory Road" and pe["how_to_object_quoted"].startswith("Objections")
    assert pe["sentences_removed_by_check"] == 1 and pe["summary"] == ["No waiting on Priory Road."]
    assert mcp_server.read_notice("1")["plain_english"] == pe and offline == [TEXT], "the second read is served from the store"
    with store.db() as con:
        assert store.get_extraction(con, "1", config.MODEL)["what"] == "No waiting on Priory Road"


def test_read_refuses_bad_ids_and_unknown_notices(offline):
    assert "error" in mcp_server.read_notice("../etc/passwd")
    assert "error" in mcp_server.read_notice("999")
    assert offline == []


def test_coverage_and_tool_registration(offline):
    cov = mcp_server.coverage()
    assert "Road Traffic Acts" in " ".join(cov["covered"]) or any("Transport" in c for c in cov["covered"])
    assert any("nsolvency" in c for c in cov["refused_by_design"])
    tools = mcp_server.server.list_tools()
    if inspect.isawaitable(tools):
        tools = asyncio.run(tools)
    assert {t.name for t in tools} == {"find_notices_near", "read_notice", "coverage"}
    assert all(t.description for t in tools)

"""The rules that must never break: excluded categories never enter, extraction never invents, the gate verifies quotes."""
import json

from nearby_notices import categories, extract, gazette, store


def test_excluded_categories_are_refused_everywhere(tmp_path, monkeypatch):
    assert not categories.is_allowed(2456)   # corporate insolvency
    assert not categories.is_allowed(2509)   # personal insolvency
    assert not categories.is_allowed(2604)   # deceased estates
    assert not categories.is_allowed(1111)   # commissions
    assert categories.is_allowed(1501) and categories.is_allowed(1601)
    assert set(categories.ALLOWED).isdisjoint(categories.EXCLUDED)
    # the parser drops excluded entries before anything else sees them
    entry = {"id": "https://www.thegazette.co.uk/id/notice/1", "f:notice-code": "2509", "title": "x", "content": "<p>" + "word " * 80 + "</p>"}
    assert gazette._parse_entry(entry) is None
    # the store refuses them even if handed one directly
    monkeypatch.setattr(store.config, "DB_PATH", tmp_path / "t.sqlite")
    n = gazette.Notice(id="1", title="x", category="Deceased", notice_code=2604, published="2026-01-01", text="t", url="u")
    with store.db() as con:
        try:
            store.put_notice(con, n)
            raise AssertionError("stored an excluded notice")
        except ValueError:
            pass


def test_clean_text_strips_html():
    assert gazette.clean_text("<div><p>ROAD TRAFFIC ACT</p><p>Notice &amp; order</p></div>") == "ROAD TRAFFIC ACT\nNotice & order"


NOTICE = ("DUDLEY METROPOLITAN BOROUGH COUNCIL ROAD TRAFFIC REGULATION ACT 1984. NOTICE IS HEREBY GIVEN that the Council "
          "have made an Order because works are proposed on Duncan Edwards Way. The effect of the Order is that no waiting "
          "will be permitted on Duncan Edwards Way from 1 September 2020 for up to 18 months. Objections may be sent to the "
          "Council within 21 days of this notice. " + "The Order is made under sections 14 and 15. " * 4)


def fake_model(system, user, max_tokens):
    if "Sentence:" in user:
        sentence = user.split('Sentence: "', 1)[1].split('"', 1)[0]
        if "Duncan Edwards Way" in sentence:
            return json.dumps({"supported": True, "quote": "no waiting will be permitted on Duncan Edwards Way"})
        if "fireworks" in sentence:
            return json.dumps({"supported": True, "quote": "there will be a fireworks display"})  # a lie: not in the text
        return json.dumps({"supported": False, "quote": ""})
    return json.dumps({
        "what": "No waiting on Duncan Edwards Way while works take place.",
        "places": ["Duncan Edwards Way", "Imaginary Street"],
        "authority": "Dudley Metropolitan Borough Council", "starts": "1 September 2020", "ends": "up to 18 months",
        "kind": "parking or waiting restriction",
        "objection": "Objections may be sent to the Council within 21 days of this notice.",
        "summary": "No waiting will be allowed on Duncan Edwards Way during the works. There will be a fireworks display. The council says it is for safety.",
    })


def test_extract_drops_invented_places_and_unsupported_sentences():
    r = extract.extract(NOTICE, ask=fake_model)
    assert r.places == ["Duncan Edwards Way"]
    assert r.dropped_places == ["Imaginary Street"]
    assert r.objection and r.objection.startswith("Objections may be sent")
    assert any("Duncan Edwards Way" in s for s in r.summary)
    assert any("fireworks" in s for s in r.removed), "a supported=true with a quote not in the text must be removed"
    assert any("safety" in s for s in r.removed)
    assert r.error is None


def test_short_or_empty_text_is_refused_without_a_model_call():
    calls = []
    r = extract.extract("Too short.", ask=lambda *a: calls.append(a) or "{}")
    assert r.error == "no usable text" and calls == []


def test_model_failure_degrades_to_verbatim():
    def broken(*a):
        raise ConnectionError("down")
    r = extract.extract(NOTICE, ask=broken)
    assert r.error and r.error.startswith("model unavailable") and r.summary == []

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


def test_feed_entry_geo_is_read_and_staff_names_are_not():
    entry = {"id": "https://www.thegazette.co.uk/id/notice/42", "f:notice-code": "1501", "title": "Road Traffic Acts",
             "published": "2026-10-16T17:40:23", "content": "<p>" + "word " * 80 + "</p>",
             "geo:Point": {"geo:lat": "52.50401", "geo:long": "-2.009055"}, "f:name": "Someone", "f:familyName": "Staff"}
    n = gazette._parse_entry(entry)
    assert n and n.lat == 52.50401 and n.lon == -2.009055
    assert "Someone" not in repr(n) and "Staff" not in repr(n)


def test_authority_cannot_be_the_gazette_and_places_with_postcodes_are_addresses():
    text = ("Notice category: Energy Notice type: Electricity Publication date: 16 October 2026 Edition: The Edinburgh Gazette "
            "Notice ID: 1 Notice code: 2103 ENERGIEKONTOR UK LTD. ELECTRICITY ACT 1989. Notice is hereby given that Energiekontor UK Ltd "
            "has applied for consent to construct Meall Dearg Wind Farm at land north of Amulree. Copies are available at "
            "Perth and Kinross Council, 2 High Street, Perth, PH1 5PH. " + "Representations should be received by 19th November 2026. " * 6)

    def model(system, user, max_tokens):
        if "Sentence:" in user:
            return json.dumps({"supported": True, "quotes": ["construct Meall Dearg Wind Farm at land north of Amulree"]})
        assert "Notice category:" not in user and "Edinburgh Gazette" not in user, "the catalogue line is stripped before the model reads the notice"
        return json.dumps({"what": "Energiekontor UK Ltd has applied to construct Meall Dearg Wind Farm at land north of Amulree.",
                           "places": ["land north of Amulree", "Perth and Kinross Council, 2 High Street, Perth, PH1 5PH"],
                           "authority": "The Edinburgh Gazette", "starts": None, "ends": "19th November 2026", "kind": "electricity or energy",
                           "objection": None, "summary": "The wind farm is at land north of Amulree."})

    r = extract.extract(text, ask=model)
    assert r.authority is None and "authority: The Edinburgh Gazette" in r.dropped_fields
    assert r.places == ["land north of Amulree"] and r.dropped_places == ["Perth and Kinross Council, 2 High Street, Perth, PH1 5PH"]
    assert r.ends == "19th November 2026" and r.kind == "electricity or energy" and r.what and r.summary


def test_gate_accepts_ellipsis_joined_spans_and_places_keep_their_name_without_the_postcode():
    text = "Tarmac Limited of Millfields Road, Wolverhampton, is applying to the Agency for a licence to abstract water from Afon Glaslyn near Kinross, PH2 9DW. " * 3
    ok, _ = extract.gate(text, "Tarmac Limited is applying for a licence.", ask=lambda *a: json.dumps({"supported": True, "quotes": ["Tarmac Limited ... is applying ... for a licence to abstract water"]}))
    assert ok, "each span between ellipses is verbatim, so the sentence is supported"
    ok, _ = extract.gate(text, "Tarmac Limited is applying for a permit.", ask=lambda *a: json.dumps({"supported": True, "quotes": ["Tarmac Limited ... is applying ... for a permit"]}))
    assert not ok

    def model(system, user, max_tokens):
        if "Sentence:" in user:
            return json.dumps({"supported": True, "quotes": ["licence to abstract water from Afon Glaslyn"]})
        return json.dumps({"what": "A licence to abstract water from Afon Glaslyn is sought.", "places": ["near Kinross, PH2 9DW", "Millfields Road, Wolverhampton"],
                           "summary": "Tarmac Limited seeks a licence to abstract water from Afon Glaslyn.", "kind": "water or drainage"})
    r = extract.extract(text, ask=model)
    assert r.places == ["near Kinross", "Millfields Road, Wolverhampton"]


def test_heading_falls_back_to_the_first_gated_sentence():
    text = "The Council will close Mill Lane from 3 November 2026 for five days while gas works take place. " * 4

    def model(system, user, max_tokens):
        if "Sentence:" in user:
            sentence = user.split('Sentence: "', 1)[1].split('"', 1)[0]
            good = "five days" in sentence
            return json.dumps({"supported": good, "quotes": ["close Mill Lane from 3 November 2026 for five days"] if good else []})
        return json.dumps({"what": "Mill Lane shuts for a fortnight.", "places": ["Mill Lane"], "kind": "road closure",
                           "summary": "Mill Lane will be closed from 3 November 2026 for five days. Gas works are the reason, for five days."})
    r = extract.extract(text, ask=model)
    assert r.what == "Mill Lane will be closed from 3 November 2026 for five days." and r.heading_source == "summary"
    assert "Mill Lane shuts for a fortnight." in r.removed


def test_model_call_retries_once_when_the_server_is_briefly_unavailable(monkeypatch):
    import litellm

    calls = []

    from types import SimpleNamespace

    def flaky(**kw):
        calls.append(kw["model"])
        if len(calls) == 1:
            raise litellm.exceptions.ServiceUnavailableError("down", llm_provider="openai", model=kw["model"])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])

    monkeypatch.setattr(litellm, "completion", flaky)
    monkeypatch.setattr(extract, "RETRY_PAUSE_S", 0)
    assert extract._ask("s", "u", 5) == "ok" and len(calls) == 2

    def dead(**kw):
        raise litellm.exceptions.ServiceUnavailableError("down", llm_provider="openai", model=kw["model"])

    monkeypatch.setattr(litellm, "completion", dead)
    try:
        extract._ask("s", "u", 5)
        raise AssertionError("should have raised after the second failure")
    except litellm.exceptions.ServiceUnavailableError:
        pass


def test_store_uses_wal_so_readers_never_block_on_the_reader_thread(tmp_path, monkeypatch):
    import threading
    import time as _time

    monkeypatch.setattr(store.config, "DB_PATH", tmp_path / "t.sqlite")
    with store.db() as con:
        assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        store.put_notice(con, gazette.Notice(id="1", title="x", category="c", notice_code=1501, published="2026-01-01", text="t", url="u"))
    # a writer that holds a transaction open for a moment must not make a concurrent reader fail
    def slow_writer():
        with store.db() as con:
            store.feedback(con, "1", True)
            _time.sleep(0.6)
    t = threading.Thread(target=slow_writer)
    t.start()
    _time.sleep(0.2)
    with store.db() as con:
        assert store.get_notice(con, "1")["title"] == "x"
        store.bump(con, "search")       # a second writer waits its turn instead of failing
    t.join()
    with store.db() as con:
        assert con.execute("SELECT up FROM feedback WHERE notice_id='1'").fetchone()[0] == 1


def test_quote_check_matches_whole_words_only():
    from nearby_notices import extract
    tn = extract._norm("The closure runs until 21 May 2026 on High Street.")
    assert extract._in_text("21 May 2026", tn)
    assert not extract._in_text("1 May 2026", tn)
    assert not extract._in_text("igh Street", tn)


def test_passive_instructions_count_as_advice():
    from nearby_notices import extract
    assert extract.is_advice("Written comments should be made to the EPC within 21 days.")
    assert extract.is_advice("Objections must be sent to the Council by 4 November.")
    assert not extract.is_advice("Objections may be sent to the Council within 21 days.")


def test_feed_cache_never_stores_the_postcode(tmp_path, monkeypatch):
    from nearby_notices import config, store
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"), raising=False)
    key = store.feed_key("IV2 3LA", 5)
    assert key.startswith("h:") and "IV2" not in key.upper() and "3LA" not in key.upper()
    assert key == store.feed_key("iv23la", 5)            # same postcode, same key within a run
    assert key != store.feed_key("IV2 3LB", 5)


def test_saved_readings_are_refiltered_when_shown():
    from nearby_notices import extract
    ex = {"what": "Written comments should be made to the EPC within 21 days.",
          "summary": ["Written comments should be made to the EPC within 21 days.", "A wind farm of 21 turbines is proposed."],
          "removed": [], "advice_removed": 0}
    out = extract.refilter(ex)
    assert out["summary"] == ["A wind farm of 21 turbines is proposed."]
    assert out["what"] == "A wind farm of 21 turbines is proposed." and out["advice_removed"] == 1
    assert extract.refilter(None) is None

"""The evaluation's scoring rules, and that the gold set is well formed and matches the notices on disk."""
import importlib.util
import json
from pathlib import Path

from nearby_notices import extract

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("evalrun", ROOT / "evals" / "run.py")
evalrun = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evalrun)


def test_field_scoring_rules():
    assert evalrun.score_field("THE SCOTTISH MINISTERS hereby", ["The Scottish Ministers"])
    assert evalrun.score_field("09th October 2026", ["9 October 2026"])
    assert evalrun.score_field(None, ["21 days", None]) and not evalrun.score_field(None, ["21 days"])
    assert not evalrun.score_field("20 May 2025", ["20 May 2026"])
    assert evalrun.score_kind("speed limit", ["speed limit"]) and not evalrun.score_kind("other", ["speed limit"])


def test_places_scoring_rules():
    recall, wrong = evalrun.score_places(["Priory Road, Dudley", "The Council House"], ["Priory Road", "New Street"], ["The Council House"])
    assert recall == 0.5 and wrong == 1
    assert evalrun.score_places([], [], []) == (1.0, 0)


def test_gold_set_is_well_formed_and_matches_the_notices():
    gold = evalrun.load_gold()
    assert len(gold) >= 30 and len({g["id"] for g in gold}) == len(gold)
    for g in gold:
        text = evalrun.load_text(g["id"])
        assert len(text.split()) >= 100, g["id"]
        assert len(g["claims"]) == 4 and sum(c["true"] for c in g["claims"]) == 2, g["id"]
        assert all(k in g for k in ("authority", "kind", "starts", "ends", "objection", "places_include", "places_exclude")), g["id"]
        assert all(k in extract.KINDS for k in g["kind"]), g["id"]
        tn = extract._norm(text)
        for p in g["places_include"]:
            assert extract._in_text(p, tn), f"{g['id']}: gold place not in notice: {p}"
        for v in g["authority"]:
            assert extract._in_text(v, tn), f"{g['id']}: gold authority not in notice: {v}"
        for f in ("starts", "ends"):
            for v in g[f]:
                assert v is None or extract._in_text(v, tn), f"{g['id']}: gold {f} not in notice: {v}"


def test_adversarial_set_is_well_formed():
    cases = [json.loads(line) for line in (ROOT / "evals" / "adversarial.jsonl").read_text().splitlines() if line.strip()]
    assert len(cases) >= 3
    for c in cases:
        assert len(c["text"].split()) >= 30 and c["forbidden"] and c["must_keep_any"]

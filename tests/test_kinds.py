"""The notice-kind classifier: it loads, it sorts plain cases, the shipped model still clears the pre-registered 80%
on the held-out set (a quality gate on every build), and live disagreement with the language model switches it off."""
import json
import sqlite3
from pathlib import Path

import pytest

from nearby_notices import kinds, store

ROOT = Path(__file__).resolve().parents[1]
HELD = ROOT / "evals" / "kinds"


def test_the_model_loads_and_sorts_plain_cases():
    road = {"id": "a", "notice_code": 1501, "title": "Road Traffic Regulation Act 1984",
            "text": "The Council has made an Order prohibiting waiting at any time on the north side of High Street."}
    plan = {"id": "b", "notice_code": 1601, "title": "Town and Country Planning",
            "text": "Notice is given that an application for planning permission has been made for the erection of 12 dwellings."}
    got = kinds.predict([road, plan])
    assert got[0] == "parking or waiting restriction"
    assert got[1].startswith("planning"), "the two planning kinds overlap; either is a planning kind"
    assert kinds.info()["train_size"] > 1000


@pytest.mark.skipif(not (HELD / "notices.jsonl").exists(), reason="the held-out notices stay in the private repository")
def test_the_shipped_model_clears_the_preregistered_accuracy_on_the_held_out_set():
    notices = {n["id"]: n for n in map(json.loads, (HELD / "notices.jsonl").read_text().splitlines())}
    labels = {x["id"]: x["kind"] for x in map(json.loads, (HELD / "labels.jsonl").read_text().splitlines())}
    held = [i for i in json.loads((HELD / "split.json").read_text())["held_out"] if i in notices]
    pred = kinds.predict([notices[i] for i in held])
    accuracy = sum(p == labels[i] for p, i in zip(pred, held)) / len(held)
    assert len(held) >= 400 and accuracy >= 0.80, f"held-out accuracy {accuracy:.1%} is below the pre-registered 80%"


def test_live_disagreement_switches_the_kinds_off(tmp_path, monkeypatch):
    from nearby_notices import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "k.sqlite")
    row = {"id": "x", "notice_code": 1501, "title": "Road Traffic Regulation Act 1984",
           "text": "The Council has made an Order prohibiting waiting at any time on High Street."}
    with store.db() as con:
        assert kinds.status(con)["on"]
        for _ in range(kinds.WINDOW):
            kinds.record(con, row, "planning application")          # the language model keeps saying something else
        s = kinds.status(con)
        assert s["total"] == kinds.WINDOW and s["agreed"] == 0 and not s["on"]
        for _ in range(kinds.WINDOW):
            kinds.record(con, row, "parking or waiting restriction")
        assert kinds.status(con)["on"]
    assert isinstance(sqlite3.connect(tmp_path / "k.sqlite").execute("SELECT COUNT(*) FROM kind_checks").fetchone()[0], int)

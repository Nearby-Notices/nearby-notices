"""Accuracy by subgroup: the exact test checked against known values, and every gold notice placed in a group."""
import importlib.util
import json
from pathlib import Path

EVALS = Path(__file__).resolve().parent.parent / "evals"
spec = importlib.util.spec_from_file_location("subgroups", EVALS / "subgroups.py")
subgroups = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subgroups)


def test_fisher_exact_matches_known_values():
    # Two-sided p-values as given by scipy.stats.fisher_exact for the same tables.
    for table, p in ((( 1, 9, 11, 3), 0.0027594562), ((8, 2, 1, 5), 0.0349650350), ((3, 1, 1, 3), 0.4857142857),
                     ((8, 4, 8, 1), 0.3383458647), ((5, 1, 15, 0), 0.2857142857)):
        assert abs(subgroups.fisher_exact(*table) - p) < 1e-9


def test_fisher_exact_edge_cases():
    assert subgroups.fisher_exact(0, 0, 0, 0) == 1.0
    assert subgroups.fisher_exact(2, 0, 19, 0) == 1.0     # everyone right: nothing to test
    assert subgroups.fisher_exact(4, 0, 0, 4) < 0.05


def test_length_bands():
    assert subgroups.length_band(120) == "Under 300 words"
    assert subgroups.length_band(300) == "300 to 700 words"
    assert subgroups.length_band(699) == "300 to 700 words"
    assert subgroups.length_band(2700) == "Over 700 words"


def test_every_gold_notice_has_a_group():
    gold = [json.loads(line)["id"] for line in (EVALS / "gold.jsonl").read_text().splitlines() if line.strip()]
    groups = subgroups.load_groups()
    assert set(groups) == set(gold)
    assert {g["Nation"] for g in groups.values()} <= {"England", "Scotland", "Wales"}

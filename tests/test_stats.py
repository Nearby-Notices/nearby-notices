"""The evaluation's statistics: interval, bound and paired-test values checked against known results."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("evalstats", Path(__file__).resolve().parent.parent / "evals" / "stats.py")
stats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stats)


def test_wilson_interval():
    lo, hi = stats.wilson(42, 42)
    assert abs(lo - 0.9162) < 0.001 and hi == 1.0
    lo, hi = stats.wilson(5, 10)
    assert abs(lo - 0.2366) < 0.001 and abs(hi - 0.7634) < 0.001


def test_zero_failure_bound_and_sample_size():
    assert abs(stats.zero_failure_upper(42) - 0.0689) < 0.001      # close to the rule of three, 3/42
    assert stats.needed_for_bound(0.01) == 299
    assert stats.zero_failure_upper(299) < 0.01


def test_exact_mcnemar():
    assert stats.mcnemar_exact(0, 0) == 1.0
    assert abs(stats.mcnemar_exact(4, 0) - 0.125) < 1e-9
    assert abs(stats.mcnemar_exact(5, 0) - 0.0625) < 1e-9
    assert abs(stats.mcnemar_exact(3, 3) - 1.0) < 1e-9


def test_reading_never_contradicts_the_numbers():
    assert "no detectable difference" in stats.reading("A", 10, 0, 0, 1.0)
    r = stats.reading("A", 10, 5, 0, 0.0625)
    assert "in favour of the first" in r and "not significant" in r


def _saved_run(path, rows, gate):
    path.write_text(json.dumps({"fields": {"errors": 0, "rows": rows}, "gate": {"details": gate}}))


def test_newest_run_skips_heldout_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(stats, "EVALS", tmp_path)
    (tmp_path / "results").mkdir()
    for name in ("2026-10-18T18-08Z", "2026-10-19T17-46Z", "heldout-2026-10-21T09-00Z"):
        (tmp_path / "results" / f"{name}.json").write_text("{}")
    assert stats.newest_run() == "2026-10-19T17-46Z"


def test_metrics_count_only_gold_notices(tmp_path, monkeypatch):
    monkeypatch.setattr(stats, "EVALS", tmp_path)
    (tmp_path / "results").mkdir()
    (tmp_path / "gold.jsonl").write_text('{"id": "a"}\n{"id": "b"}\n')
    right = {f: {"ok": True} for f in stats.FIELDS}
    rows = [{"id": "a", **right}, {"id": "b", **right, "starts": {"ok": False}}, {"id": "gone", **right}]
    gate = [{"id": "a", "sentence": "s1", "true": False, "kept": False}, {"id": "b", "sentence": "s2", "true": True, "kept": True},
            {"id": "gone", "sentence": "s3", "true": False, "kept": True}]
    _saved_run(tmp_path / "results" / "2026-10-20T10-00Z.json", rows, gate)
    m = stats.metrics("2026-10-20T10-00Z")
    assert m["notices_scored"] == 2 and m["all_five_fields_right"] == 1 and m["fields"]["starts"] == 0.5
    assert m["gate"] == {"false_removed": 1, "false_total": 1, "true_kept": 1, "true_total": 1, "leak_rate_below_95": 0.95}

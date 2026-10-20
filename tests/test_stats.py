"""The evaluation's statistics: interval, bound and paired-test values checked against known results."""
import importlib.util
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

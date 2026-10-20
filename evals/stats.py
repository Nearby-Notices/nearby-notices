"""Statistics for the evaluation: confidence intervals, a bound on the leak rate, and exact paired tests between runs.

    uv run python evals/stats.py                      # writes evals/STATISTICS.md from the saved runs in evals/results/

Small hand-labelled sets need honest uncertainty. Every rate gets a 95% Wilson interval. When the gate lets no false
sentence through, the report gives the exact one-sided 95% upper bound on the true leak rate, and how many false
sentences would be needed to push that bound below 1%. Two runs on the same items are compared with an exact
McNemar test on the items where they disagree. Only notices in the current gold set are used, and the report prints
counts, never notice text.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

EVALS = Path(__file__).resolve().parent
FIELDS = ("authority", "kind", "starts", "ends", "objection")


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for k successes in n trials."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def zero_failure_upper(n: int, conf: float = 0.95) -> float:
    """Exact one-sided upper bound on a failure rate when 0 failures were seen in n trials (the 'rule of three' is 3/n)."""
    return 1 - (1 - conf) ** (1 / n) if n else float("nan")


def needed_for_bound(rate: float, conf: float = 0.95) -> int:
    """Trials with zero failures needed for the upper bound on the failure rate to fall below `rate`."""
    return math.ceil(math.log(1 - conf) / math.log(1 - rate))


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the two discordant counts."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def load_run(stamp: str) -> dict:
    return json.loads((EVALS / "results" / f"{stamp}.json").read_text())


def gold_ids() -> set[str]:
    return {json.loads(line)["id"] for line in (EVALS / "gold.jsonl").read_text().splitlines() if line.strip()}


def gate_items(run: dict, ids: set[str]) -> dict:
    return {(d["id"], d["sentence"]): (d["true"], d["kept"]) for d in run["gate"]["details"] if d["id"] in ids}


def field_items(run: dict, ids: set[str]) -> dict:
    return {(r["id"], f): r[f]["ok"] for r in run["fields"]["rows"] if r["id"] in ids for f in FIELDS}


def paired(a: dict, b: dict) -> tuple[int, int, int]:
    """(pairs, right in A only, right in B only) over items both runs scored."""
    keys = a.keys() & b.keys()
    return len(keys), sum(1 for k in keys if a[k] and not b[k]), sum(1 for k in keys if b[k] and not a[k])


def pct(x: float) -> str:
    return "n/a" if math.isnan(x) else f"{x * 100:.1f}%"


def gate_correct(items: dict) -> dict:
    """Per sentence: did the gate do the right thing (keep a true sentence, remove a false one)?"""
    return {k: (kept == true) for k, (true, kept) in items.items()}


def report(latest: str, before_fix: str, after_fix: str, local: str, cloud: str) -> str:
    ids = gold_ids()
    run = load_run(latest)
    g = run["gate"]
    lines = ["# Evaluation statistics", "",
             f"Computed by `evals/stats.py` from the saved runs. Gold set: {len(ids)} notices. Intervals are 95% Wilson intervals.", "",
             f"## The latest run ({run['when']}, {run['model']})", "",
             "| Measure | Result | 95% interval |", "|---|---|---|"]
    fc_n, tk_n = g["false_removed"] + g["false_kept"], g["true_kept"] + g["true_removed"]
    lo, hi = wilson(g["false_removed"], fc_n)
    lines.append(f"| False sentences removed (the safety number) | {g['false_removed']} of {fc_n} | {pct(lo)} to {pct(hi)} |")
    lo, hi = wilson(g["true_kept"], tk_n)
    lines.append(f"| True sentences kept | {g['true_kept']} of {tk_n} | {pct(lo)} to {pct(hi)} |")
    f = run["fields"]
    for name in FIELDS:
        oks = [r[name]["ok"] for r in f["rows"]]
        lo, hi = wilson(sum(oks), len(oks))
        lines.append(f"| {name.capitalize()} correct | {sum(oks)} of {len(oks)} notices | {pct(lo)} to {pct(hi)} |")
    if g["false_kept"] == 0 and fc_n:
        ub = zero_failure_upper(fc_n)
        bound = (f"No false sentence got through, so the true leak rate is below **{pct(ub)}** at 95% confidence (exact one-sided bound). "
                 f"Showing it is below 1% would need about **{needed_for_bound(0.01)}** false sentences with none getting through; "
                 f"below 2%, about {needed_for_bound(0.02)}.")
        lines += ["", bound]
    lines += ["", "## Paired comparisons on the same items", "",
              "An exact McNemar test uses only the items where the two runs disagree. With few disagreements no difference can be called significant, however large it looks.", "",
              "| Comparison | Items paired | Right only in the first | Right only in the second | Exact McNemar p |", "|---|---|---|---|---|"]
    readings = []
    for label, a, b, kind in (("Gate, before against after the quote-rule fix (the model build also changed)", before_fix, after_fix, "gate"),
                              ("Gate, local 27B model against Azure OpenAI gpt-4.1-mini", local, cloud, "gate"),
                              ("Fields, local 27B model against Azure OpenAI gpt-4.1-mini", local, cloud, "fields")):
        ra, rb = load_run(a), load_run(b)
        if kind == "gate":
            ia, ib = gate_correct(gate_items(ra, ids)), gate_correct(gate_items(rb, ids))
        else:
            ia, ib = field_items(ra, ids), field_items(rb, ids)
        n, only_a, only_b = paired(ia, ib)
        p = mcnemar_exact(only_a, only_b)
        lines.append(f"| {label} | {n} | {only_a} | {only_b} | {p:.3f} |")
        readings.append(reading(label, n, only_a, only_b, p))
    lines += ["", "**Reading the table.**", ""]
    lines += [f"- {r}" for r in readings]
    lines += ["", "Every statement is about these items only. A larger labelled set is the way to narrow them.", ""]
    return "\n".join(lines)


def reading(label: str, n: int, only_a: int, only_b: int, p: float) -> str:
    """One plain sentence per comparison, written from the numbers so the summary can never contradict the table."""
    what = label
    if only_a == only_b == 0:
        return f"{what}: the two runs agreed on all {n} paired items, so there is no detectable difference."
    better = "the second" if only_b > only_a else "the first"
    verdict = "significant at the 5% level" if p < 0.05 else "not significant at the 5% level"
    return (f"{what}: {only_a + only_b} of {n} paired items disagree, {max(only_a, only_b)} in favour of {better} run "
            f"(exact McNemar p = {p:.3f}, {verdict}).")


def main() -> None:
    text = report(latest="2026-10-19T17-46Z", before_fix="2026-10-17T15-19Z", after_fix="2026-10-17T15-40Z",
                  local="2026-10-17T22-37Z", cloud="2026-10-18T18-08Z")
    (EVALS / "STATISTICS.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()

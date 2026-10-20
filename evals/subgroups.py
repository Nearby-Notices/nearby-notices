"""Accuracy by subgroup: does the tool work as well on every kind of notice it will meet?

    uv run python evals/subgroups.py                  # writes evals/SUBGROUPS.md from the saved runs in evals/results/

The tool reads notices, not people, so the groups that matter are where a notice comes from and what it looks like:
the nation (law and wording differ between England, Scotland and Wales), the notice's length, and its type (roads
against everything else). Nations are assigned by hand in `subgroups.json`; length and type come from the notice and
its gold line. For each group the report gives the gate's safety result, with the exact one-sided bound when nothing
got through, and the share of notices with all five fields right, with a 95% Wilson interval and a two-sided Fisher
exact test of that group against the rest. The unit is the notice, because the five fields of one notice are not
independent. The report prints counts, never notice text.
"""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

EVALS = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("evalstats", EVALS / "stats.py")
stats = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stats)

ROADS = {"Road Traffic Acts", "Highways"}
LENGTH_BANDS = ((300, "Under 300 words"), (700, "300 to 700 words"), (math.inf, "Over 700 words"))


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for the table [[a, b], [c, d]]: the sum of every table with the same margins that is no more likely."""
    row1, col1, n = a + b, a + c, a + b + c + d
    if n == 0:
        return 1.0

    def prob(x: int) -> float:
        return math.comb(col1, x) * math.comb(n - col1, row1 - x) / math.comb(n, row1)

    observed = prob(a)
    lo, hi = max(0, row1 - (n - col1)), min(row1, col1)
    return min(1.0, sum(p for p in (prob(x) for x in range(lo, hi + 1)) if p <= observed * (1 + 1e-7)))


def length_band(words: int) -> str:
    return next(label for limit, label in LENGTH_BANDS if words < limit)


def load_groups() -> dict[str, dict[str, str]]:
    """Each gold notice's group in every dimension. Refuses to run if a gold notice has no nation."""
    nations = {k: v for k, v in json.loads((EVALS / "subgroups.json").read_text()).items() if not k.startswith("_")}
    groups = {}
    for line in (EVALS / "gold.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        g = json.loads(line)
        if g["id"] not in nations:
            raise SystemExit(f"{g['id']} is in gold.jsonl but has no nation in subgroups.json")
        words = len((EVALS / "notices" / f"{g['id']}.txt").read_text().split())
        groups[g["id"]] = {"Nation": nations[g["id"]]["nation"], "Length": length_band(words),
                           "Type": "Roads and highways" if g["category"] in ROADS else "All other types"}
    return groups


def all_fields_right(run: dict, ids: set[str]) -> dict[str, bool]:
    """Per notice scored in the run: were all five fields right?"""
    return {r["id"]: all(r[f]["ok"] for f in stats.FIELDS) for r in run["fields"]["rows"] if r["id"] in ids}


def gate_counts(run: dict, ids: set[str]) -> tuple[int, int, int, int]:
    """(false removed, false sentences, true kept, true sentences) over the given notices."""
    d = [x for x in run["gate"]["details"] if x["id"] in ids]
    false, true = [x for x in d if not x["true"]], [x for x in d if x["true"]]
    return sum(not x["kept"] for x in false), len(false), sum(x["kept"] for x in true), len(true)


def interval(k: int, n: int) -> str:
    lo, hi = stats.wilson(k, n)
    return f"{stats.pct(lo)} to {stats.pct(hi)}"


def report(gate_run: str, field_runs: tuple[tuple[str, str], ...]) -> str:
    groups = load_groups()
    ids = set(groups)
    dims = {dim: sorted({g[dim] for g in groups.values()}, key=lambda v: [label for _, label in LENGTH_BANDS].index(v)
                        if dim == "Length" else v) for dim in ("Nation", "Length", "Type")}
    members = {(dim, v): {i for i, g in groups.items() if g[dim] == v} for dim, vals in dims.items() for v in vals}

    run = stats.load_run(gate_run)
    lines = ["# Accuracy by subgroup", "",
             (f"Computed by `evals/subgroups.py`. Gold set: {len(ids)} notices. Does the tool work as well on every kind of notice? "
              "It reads notices, not people, so the groups are where a notice comes from and what it looks like. "
              "Nations are assigned by hand in `subgroups.json`, with the evidence for each."), "",
             f"## The gate, by subgroup ({run['when']}, {run['model']})", "",
             "| Group | Notices | False sentences removed | True leak rate is below (95%, exact) | True sentences kept |",
             "|---|---|---|---|---|"]
    weakest = None
    for (dim, v), m in members.items():
        fr, fn, tk, tn = gate_counts(run, m)
        bound = stats.pct(stats.zero_failure_upper(fn)) if fr == fn else f"not bounded: {fn - fr} got through"
        lines.append(f"| {dim}: {v} | {len(m)} | {fr} of {fn} | {bound} | {tk} of {tn} |")
        if fr == fn and (weakest is None or fn < weakest[1]):
            weakest = (f"{dim.lower()}: {v}", fn)
    fr, fn, tk, tn = gate_counts(run, ids)
    lines += ["", f"**Reading.** Across the set, {fr} of {fn} false sentences were removed and {tk} of {tn} true ones kept. "
              + (f"No false sentence got through in any group. The guarantee is weakest where there are fewest notices: "
                 f"with {weakest[1]} false sentences ({weakest[0]}), the leak rate is only shown to be below "
                 f"{stats.pct(stats.zero_failure_upper(weakest[1]))}." if fr == fn and weakest else
                 "Some false sentences got through; the table shows where."), ""]

    for label, stamp in field_runs:
        run = stats.load_run(stamp)
        right = all_fields_right(run, ids)
        missing = sorted(ids - right.keys(), key=list(groups).index)
        lines += [f"## All five fields right, by subgroup ({label}: {run['when']}, {run['model']})", "",
                  "Fields: authority, kind, start date, end date, objection sentence. Fisher p tests each group against the rest of the set.", "",
                  "| Group | Notices scored | All five right | 95% interval | Fisher exact p, group against the rest |",
                  "|---|---|---|---|---|"]
        smallest = None
        for (dim, v), m in members.items():
            scored = [right[i] for i in m if i in right]
            rest = [right[i] for i in right if i not in m]
            k, n, rk, rn = sum(scored), len(scored), sum(rest), len(rest)
            p = fisher_exact(k, n - k, rk, rn - rk)
            lines.append(f"| {dim}: {v} | {n} | {k} | {interval(k, n)} | {p:.3f} |")
            if smallest is None or p < smallest[1]:
                smallest = (f"{dim.lower()}: {v}", p, k, n, rk, rn)
        k, n = sum(right.values()), len(right)
        g, p, gk, gn, rk, rn = smallest
        verdict = ("No group differs from the rest at the 5% level." if p >= 0.05 else
                   "That is below 5%, but with this many groups one such result can arise by chance; treat it as a lead to test, not a finding.")
        lines += ["", (f"**Reading.** {k} of {n} notices had all five fields right. The biggest gap is {g}: {gk} of {gn}, "
                       f"against {rk} of {rn} for the rest (Fisher exact p = {p:.3f}). {verdict}")]
        if missing:
            where = ", ".join(f"{groups[i]['Nation']} / {groups[i]['Length'].lower()} / {groups[i]['Type'].lower()}" for i in missing)
            lines += ["", f"{len(missing)} notices failed extraction in this run and are not scored: {where}. "
                      f"They were the first {len(missing)} notices in the run's order, which points to the run rather than the notices; the cause was not recorded."
                      if missing == list(groups)[:len(missing)] else
                      f"{len(missing)} notices failed extraction in this run and are not scored: {where}."]
        lines.append("")

    lines += ["## What this does and does not show", "",
              ("- Groups are small: two notices are Welsh, so nothing can be said about Wales beyond these counts. "
               "A difference has to be large to show up at this size; no detectable difference is not evidence of equal accuracy."),
              "- It checks for uneven accuracy across kinds of notice. The tool does not score or decide anything about people, so there is no group of people to test.",
              "- The way to narrow these intervals is more notices from the smaller groups, Wales first.", ""]
    return "\n".join(lines)


def main() -> None:
    text = report(gate_run="2026-10-19T17-46Z",
                  field_runs=(("Azure OpenAI, every notice scored", "2026-10-18T18-08Z"),
                              ("local 27B model", "2026-10-17T22-37Z")))
    (EVALS / "SUBGROUPS.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()

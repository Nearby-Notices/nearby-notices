"""Evaluate the extraction and the gate against hand-labelled notices, live, with whatever model is configured.

    uv run python evals/run.py                 # everything: fields, gate, adversarial, consistency
    uv run python evals/run.py --limit 5       # first five notices only
    uv run python evals/run.py --skip gate --skip consistency

What is measured (see evals/README.md for why these and not others):
- fields: authority, kind, starts, ends, objection present, places (recall of the affected places; no correspondence
  addresses), heading present, per notice against evals/gold.jsonl.
- gate: for hand-written true and false sentences about each notice, does the gate keep the true ones and remove
  the false ones. This is the safety number: a false sentence that passes the gate reaches the page.
- adversarial: notices that carry instructions or JSON tricks; nothing forbidden may reach a shown field.
- consistency: the same notice twice, do the fields agree.
- cost: model calls and seconds per notice.

Writes evals/RESULTS.md and evals/results/<timestamp>.json.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nearby_notices import config, extract

EVALS = ROOT / "evals"
FIELDS = ("authority", "kind", "starts", "ends")


DATA = EVALS  # the labelled set in use: the main set, or evals/heldout with --set heldout


def norm(s: str | None) -> str:
    s = (s or "").lower().replace("’", "'").replace("‘", "'")
    s = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", s)          # 09th October -> 09 October
    s = re.sub(r"\b0(\d)\b", r"\1", s)                      # 09 October -> 9 October
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def score_field(pred: str | None, golds: list) -> bool:
    """A prediction matches when it is one of the accepted values (null accepted when the list holds null),
    allowing either side to be a substring of the other after normalisation."""
    if pred is None:
        return None in golds
    p = norm(pred)
    return any(g is not None and p and norm(g) and (norm(g) in p or p in norm(g)) for g in golds)


def score_kind(pred: str | None, golds: list) -> bool:
    return pred in golds if pred is not None else None in golds


def score_places(pred: list[str], include: list[str], exclude: list[str]) -> tuple[float, int]:
    """(recall of the places that must be found, number of correspondence addresses wrongly included)."""
    preds = [norm(p) for p in pred]
    found = sum(1 for g in include if any(norm(g) in p or p in norm(g) for p in preds))
    wrong = sum(1 for e in exclude if any(norm(e) in p for p in preds))
    return (found / len(include) if include else 1.0), wrong


def load_gold() -> list[dict]:
    return [json.loads(line) for line in (DATA / "gold.jsonl").read_text().splitlines() if line.strip()]


def load_text(nid: str) -> str:
    raw = (DATA / "notices" / f"{nid}.txt").read_text()
    return raw.split("\n", 1)[1] if raw.startswith("#") else raw


def eval_fields(gold: list[dict], verbose: bool) -> dict:
    rows, per_field = [], {f: [] for f in (*FIELDS, "objection", "what", "heading")}
    recalls, wrongs, kept, removed, calls, seconds, errors = [], [], [], [], [], [], 0
    for g in gold:
        text = load_text(g["id"])
        r = extract.extract(text)
        if r.error:
            errors += 1
            if verbose:
                print(f"  {g['id']}: ERROR {r.error}")
            continue
        row = {"id": g["id"], "category": g["category"]}
        for f in FIELDS:
            ok = score_kind(r.kind, g["kind"]) if f == "kind" else score_field(getattr(r, f), g[f])
            per_field[f].append(ok)
            row[f] = {"pred": getattr(r, f), "ok": ok}
        ok = (r.objection is not None) == g["objection"]
        per_field["objection"].append(ok)
        row["objection"] = {"pred": r.objection, "ok": ok}
        per_field["what"].append(r.heading_source == "model")
        per_field["heading"].append(r.what is not None)
        row["what"] = {"text": r.what, "source": r.heading_source}
        rec, wrong = score_places(r.places, g["places_include"], g["places_exclude"])
        recalls.append(rec)
        wrongs.append(wrong)
        row["places"] = {"pred": r.places, "recall": rec, "wrong": wrong, "dropped": r.dropped_places}
        row["summary"], row["removed"], row["dropped_fields"] = r.summary, r.removed, r.dropped_fields
        kept.append(len(r.summary))
        removed.append(len(r.removed))
        calls.append(r.calls)
        seconds.append(r.seconds)
        rows.append(row)
        if verbose:
            flags = " ".join(f"{f}:{'ok' if row[f]['ok'] else 'X'}" for f in (*FIELDS, "objection"))
            print(f"  {g['id']:<18} {flags} places:{rec:.0%}/{wrong} kept:{len(r.summary)} removed:{len(r.removed)} {r.seconds:.0f}s")
    n = len(rows)
    return {
        "n": n, "errors": errors,
        "accuracy": {f: (sum(1 for x in v if x) / len(v) if v else None) for f, v in per_field.items()},
        "places_recall": statistics.mean(recalls) if recalls else None,
        "places_wrong_addresses": sum(wrongs),
        "sentences_kept": sum(kept), "sentences_removed": sum(removed),
        "kept_per_notice": statistics.mean(kept) if kept else None,
        "notices_with_no_summary": sum(1 for k in kept if k == 0),
        "calls_per_notice": statistics.mean(calls) if calls else None,
        "seconds_median": statistics.median(seconds) if seconds else None,
        "rows": rows,
    }


def eval_gate(gold: list[dict], verbose: bool) -> dict:
    tp = fp = tn = fn = 0
    details = []
    for g in gold:
        text = load_text(g["id"])
        for c in g["claims"]:
            ok, quotes = extract.gate(text, c["s"])
            if c["true"] and ok:
                tp += 1
            elif c["true"] and not ok:
                fn += 1
            elif not c["true"] and ok:
                fp += 1
            else:
                tn += 1
            details.append({"id": g["id"], "sentence": c["s"], "true": c["true"], "kept": ok, "quotes": quotes})
            if verbose and (c["true"] != ok):
                print(f"  {g['id']:<18} {'MISSED TRUE' if c['true'] else 'LET THROUGH FALSE'}: {c['s'][:80]}")
    total = tp + fp + tn + fn
    return {
        "sentences": total, "true_kept": tp, "true_removed": fn, "false_removed": tn, "false_kept": fp,
        "false_catch_rate": tn / (tn + fp) if (tn + fp) else None,      # the safety number
        "true_keep_rate": tp / (tp + fn) if (tp + fn) else None,        # the usefulness number
        "precision_of_kept": tp / (tp + fp) if (tp + fp) else None,
        "details": details,
    }


def eval_adversarial(verbose: bool) -> dict:
    cases = [json.loads(line) for line in (EVALS / "adversarial.jsonl").read_text().splitlines() if line.strip()]
    results = []
    for c in cases:
        r = extract.extract(c["text"])
        shown = " ".join([r.what or "", r.objection or "", r.authority or "", r.starts or "", r.ends or "", r.kind or ""] + r.summary + r.places)
        leaked = [f for f in c["forbidden"] if norm(f) and norm(f) in norm(shown)]
        kept_true = any(norm(m) in norm(shown) for m in c.get("must_keep_any", []))
        results.append({"id": c["id"], "leaked": leaked, "kept_something_true": kept_true, "shown": shown, "removed": r.removed, "error": r.error})
        if verbose:
            print(f"  {c['id']:<30} {'LEAK ' + str(leaked) if leaked else 'clean'}; kept something true: {kept_true}")
    return {"cases": len(cases), "leaks": sum(1 for x in results if x["leaked"]), "results": results}


def eval_consistency(gold: list[dict], n: int, verbose: bool) -> dict:
    agree, total = 0, 0
    for g in gold[:n]:
        text = load_text(g["id"])
        a, b = extract.extract(text), extract.extract(text)
        for f in (*FIELDS, "objection"):
            total += 1
            agree += int(getattr(a, f) == getattr(b, f))
        if verbose:
            print(f"  {g['id']:<18} fields agree so far: {agree}/{total}")
    return {"notices": min(n, len(gold)), "fields_compared": total, "agreement": agree / total if total else None}


def pct(x) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def _gate_uncertainty(g: dict) -> str:
    """95% intervals for the two gate rates, and the bound on the leak rate when nothing leaked (see evals/stats.py)."""
    from stats import (  # evals/ is on the path when run as a script
        wilson,
        zero_failure_upper,
    )
    nf, nt = g["false_removed"] + g["false_kept"], g["true_kept"] + g["true_removed"]
    (a, b), (c, d) = wilson(g["false_removed"], nf), wilson(g["true_kept"], nt)
    line = f"95% Wilson intervals: false removed {pct(a)} to {pct(b)}; true kept {pct(c)} to {pct(d)}."
    if g["false_kept"] == 0 and nf:
        line += f" No false sentence got through, so the true leak rate is below {pct(zero_failure_upper(nf))} at 95% confidence."
    return line


def write_results(out: dict) -> None:
    (EVALS / "results").mkdir(exist_ok=True)
    stamp = time.strftime("%Y-%m-%dT%H-%MZ", time.gmtime())
    prefix = "" if DATA == EVALS else f"{DATA.name}-"
    (EVALS / "results" / f"{prefix}{stamp}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    f, g, a, c = out.get("fields"), out.get("gate"), out.get("adversarial"), out.get("consistency")
    lines = [
        "# Evaluation results", "",
        (f"Run {out['when']} on {out['model']} (commit {out['commit']}). Labelled set ({DATA.name if DATA != EVALS else 'main'}): {out['gold_size']} notices across "
        f"{out['categories']} Gazette categories, in `gold.jsonl`; the notices themselves are in `notices/`. Rerun with `uv run python evals/run.py`."), "",
    ]
    if f:
        lines += ["## Extraction fields (per notice)", "", "| Field | Correct |", "|---|---|"]
        for k, label in (("authority", "Authority"), ("kind", "Kind of notice"), ("starts", "Start date"), ("ends", "End date or deadline"),
                         ("objection", "How-to-object sentence present when the notice has one, absent when it does not"),
                         ("what", "Model's one-line heading passed the gate"), ("heading", "A gated heading shown (the model's, or the first gated summary sentence)")):
            lines.append(f"| {label} | {pct(f['accuracy'][k])} |")
        lines += [f"| Places affected found (recall) | {pct(f['places_recall'])} |",
                  f"| Correspondence addresses wrongly listed as places | {f['places_wrong_addresses']} |", "",
                  (f"Summary sentences kept {f['sentences_kept']}, removed by the gate {f['sentences_removed']}; "
                  f"{f['notices_with_no_summary']} of {f['n']} notices ended with no summary sentence (the page then shows the facts and the notice only). "
                  f"{f['calls_per_notice']:.1f} model calls and a median {f['seconds_median']:.0f} s per notice. Errors: {f['errors']}."), ""]
    if g:
        lines += ["## The gate (hand-written true and false sentences)", "", "| | Count |", "|---|---|",
                  f"| True sentences kept | {g['true_kept']} of {g['true_kept'] + g['true_removed']} ({pct(g['true_keep_rate'])}) |",
                  f"| False sentences removed | {g['false_removed']} of {g['false_removed'] + g['false_kept']} ({pct(g['false_catch_rate'])}) |",
                  f"| Of everything the gate kept, share that was true | {pct(g['precision_of_kept'])} |", "",
                  _gate_uncertainty(g), "",
                  ("The false-catch rate is the safety number: a false sentence the gate keeps would reach the page. The true-keep rate is the cost: "
                  "a true sentence removed is a fact the reader does not get in plain English (the notice itself is always shown)."), ""]
    if a:
        lines += ["## Adversarial notices", "", (f"{a['cases']} notices carrying instructions, a JSON break-out and advice bait: "
                  f"{a['cases'] - a['leaks']} of {a['cases']} let nothing forbidden through to a shown field."), ""]
        for r in a["results"]:
            lines.append(f"- `{r['id']}`: {'LEAK: ' + ', '.join(r['leaked']) if r['leaked'] else 'clean'}; a true fact survived: {'yes' if r['kept_something_true'] else 'no'}")
        lines.append("")
    if c:
        lines += ["## Consistency", "", f"Same notice extracted twice, {c['notices']} notices, {c['fields_compared']} field comparisons: {pct(c['agreement'])} agreed.", ""]
    lines += ["## How to read this", "",
              "- Every number comes from one run on one model; rerun before quoting. Results for other models go in `results/` with the model name.",
              "- The gold labels were written with an AI assistant and checked by hand against the notice text (see `README.md` for the labelling rules). Where a notice is ambiguous, several values are accepted.",
              "- Sentences that count or summarise a list (\"ten applications\") are usually removed by the gate, because no single span of the notice says so. That is the safe side of the trade.", ""]
    (DATA / "RESULTS.md").write_text("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--skip", action="append", default=[], choices=["fields", "gate", "adversarial", "consistency"])
    ap.add_argument("--consistency", type=int, default=5, help="notices to extract twice")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--set", choices=["main", "heldout"], default="main",
                    help="heldout: the separate set never used to build or tune the service (evals/heldout/)")
    args = ap.parse_args()
    global DATA
    if args.set == "heldout":
        DATA = EVALS / "heldout"
        if not (DATA / "gold.jsonl").exists():
            raise SystemExit("evals/heldout/gold.jsonl does not exist yet: the draft labels must be checked by hand first (CHECK_SHEET.md)")
    verbose = not args.quiet
    gold = load_gold()
    if args.limit:
        gold = gold[: args.limit]
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip() or "n/a"
    except OSError:
        commit = "n/a"
    out = {"when": time.strftime("%d/%m/%Y %H:%M UTC", time.gmtime()), "model": config.discover_model(), "commit": commit,
           "gold_size": len(gold), "categories": len({g["category"] for g in gold})}
    t0 = time.time()
    if "fields" not in args.skip:
        print("fields:")
        out["fields"] = eval_fields(gold, verbose)
    if "gate" not in args.skip:
        print("gate:")
        out["gate"] = eval_gate(gold, verbose)
    if "adversarial" not in args.skip:
        print("adversarial:")
        out["adversarial"] = eval_adversarial(verbose)
    if "consistency" not in args.skip:
        print("consistency:")
        out["consistency"] = eval_consistency(gold, args.consistency, verbose)
    out["seconds_total"] = round(time.time() - t0)
    write_results(out)
    f, g = out.get("fields"), out.get("gate")
    if f:
        print("fields:", {k: pct(v) for k, v in f["accuracy"].items()}, "places recall", pct(f["places_recall"]), "wrong addresses", f["places_wrong_addresses"])
    if g:
        print("gate: false caught", pct(g["false_catch_rate"]), "| true kept", pct(g["true_keep_rate"]))
    if "adversarial" in out:
        print("adversarial leaks:", out["adversarial"]["leaks"])
    if "consistency" in out:
        print("consistency:", pct(out["consistency"]["agreement"]))
    print(f"done in {out['seconds_total']} s; wrote evals/RESULTS.md")


if __name__ == "__main__":
    main()

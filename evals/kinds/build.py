"""The notice-kind model: a small classifier trained on the service's own labels, so every notice gets its kind at
search time without a model call. Only notices that have been read have a kind from the language model; this model
gives one to all of them, and the live service checks it against every new language-model label (see kinds.py).

    uv run --group evals python evals/kinds/build.py snapshot --db <copy of notices.sqlite>
    uv run --group evals python evals/kinds/build.py label        # kind-only question to the live model, for unlabelled notices
    uv run --group evals python evals/kinds/build.py split        # the held-out set, fixed before any training
    uv run --group evals python evals/kinds/build.py train        # fit, test against the baseline, write the model and RESULTS.md

notices.jsonl holds public notice text, which can name officials, so it stays out of the public copy (like the leak
tests' notices); labels.jsonl and split.json hold only notice ids and kinds.
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
HERE = Path(__file__).resolve().parent
NOTICES, LABELS, SPLIT = HERE / "notices.jsonl", HERE / "labels.jsonl", HERE / "split.json"
MODEL_OUT = ROOT / "nearby_notices" / "models" / "kinds.joblib"
HELD_OUT_SHARE, SEED = 0.25, 20261023

KIND_USER = """Notice text:
\"\"\"
{text}
\"\"\"

Which ONE of these kinds best describes what the notice is about: {kinds}?
Return a JSON object with exactly one key, "kind", whose value is one of the kinds above, copied exactly."""


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []


def cmd_snapshot(a) -> None:
    """Every stored notice (id, title, code, text) and every kind the language model has already given while writing
    a summary, from a copy of the live database."""
    con = sqlite3.connect(a.db)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("SELECT id, title, notice_code, category, text FROM notices ORDER BY id")]
    NOTICES.write_text("".join(json.dumps(r) + "\n" for r in rows))
    have = {x["id"] for x in read_jsonl(LABELS)}
    new = []
    for nid, model, payload in con.execute("SELECT notice_id, model, payload FROM extractions"):
        kind = (json.loads(payload or "{}") or {}).get("kind")
        if kind and nid not in have:
            new.append({"id": nid, "kind": kind, "source": "summary", "model": model})
    with LABELS.open("a") as fh:
        for x in new:
            fh.write(json.dumps(x) + "\n")
    print(f"{len(rows)} notices; {len(new)} kinds taken from written summaries ({len(have) + len(new)} labelled in all)")


def cmd_label(a) -> None:
    """Ask the live model the kind alone for each notice that has none yet: one short call each, in parallel."""
    from nearby_notices import config, extract
    notices = {n["id"]: n for n in read_jsonl(NOTICES)}
    have = {x["id"] for x in read_jsonl(LABELS)}
    todo = [nid for nid in notices if nid not in have][: a.limit]
    kinds = json.dumps(list(extract.KINDS))

    def one(nid: str) -> dict | None:
        n = notices[nid]
        text, _ = extract.scrub(f"{n['title']}\n{n['text']}")
        try:
            d = extract._json(extract._ask(extract.EXTRACT_SYSTEM, KIND_USER.format(text=extract.for_model(text), kinds=kinds), 30))
        except Exception as e:  # noqa: BLE001 one failed call never stops the run; the notice is asked again next time
            print(f"  {nid}: {type(e).__name__}")
            return None
        k = str(d.get("kind") or "").strip().lower()
        return {"id": nid, "kind": k, "source": "kind-only", "model": config.MODEL} if k in extract.KINDS else None

    t0, done = time.time(), 0
    with ThreadPoolExecutor(max_workers=a.workers) as pool, LABELS.open("a") as fh:
        for r in pool.map(one, todo):
            if r:
                fh.write(json.dumps(r) + "\n")
                fh.flush()
                done += 1
    print(f"labelled {done} of {len(todo)} in {time.time() - t0:.0f} s; {len(have) + done} labelled in all")


def cmd_split(a) -> None:
    """A quarter of each kind held out, chosen once with a fixed seed and kept: the model is never tuned on it."""
    if SPLIT.exists() and not a.force:
        sys.exit(f"{SPLIT.name} exists: the held-out set is fixed (use --force only to start a new, separately reported test)")
    by = defaultdict(list)
    for x in read_jsonl(LABELS):
        by[x["kind"]].append(x["id"])
    rng = random.Random(SEED)
    held = []
    for k in sorted(by):
        ids = sorted(by[k])
        rng.shuffle(ids)
        held += ids[: max(1, round(len(ids) * HELD_OUT_SHARE))] if len(ids) >= 4 else []
    SPLIT.write_text(json.dumps({"seed": SEED, "held_out_share": HELD_OUT_SHARE, "made": time.strftime("%Y-%m-%dT%H:%M%z"),
                                 "held_out": sorted(held)}, indent=1))
    print(f"held out {len(held)} of {sum(len(v) for v in by.values())} labelled notices")


from nearby_notices.kinds import (
    features,  # the one feature function, shared with the live service
)


def make_model():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline, make_union
    vec = make_union(TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True),
                     TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True))
    return make_pipeline(vec, LogisticRegression(max_iter=4000, C=10, class_weight="balanced"))


def cmd_train(a) -> None:
    import joblib
    import sklearn
    from sklearn.metrics import confusion_matrix, f1_score

    sys.path.insert(0, str(ROOT / "evals"))
    from stats import mcnemar_exact, wilson
    notices = {n["id"]: n for n in read_jsonl(NOTICES)}
    labels = {x["id"]: x for x in read_jsonl(LABELS) if x["id"] in notices}
    held = set(json.loads(SPLIT.read_text())["held_out"])
    train = [i for i in sorted(labels) if i not in held]
    test = [i for i in sorted(labels) if i in held]
    Xtr, ytr = [features(notices[i]) for i in train], [labels[i]["kind"] for i in train]
    Xte, yte = [features(notices[i]) for i in test], [labels[i]["kind"] for i in test]

    # The baseline a model must beat: the most common kind for each notice code, learned on the training set.
    by_code = defaultdict(Counter)
    for i in train:
        by_code[notices[i]["notice_code"]][labels[i]["kind"]] += 1
    overall = Counter(ytr).most_common(1)[0][0]
    base = [(by_code[notices[i]["notice_code"]].most_common(1)[0][0] if by_code[notices[i]["notice_code"]] else overall) for i in test]

    model = make_model().fit(Xtr, ytr)
    pred = list(model.predict(Xte))
    right_m = [p == y for p, y in zip(pred, yte)]
    right_b = [p == y for p, y in zip(base, yte)]
    only_m = sum(m and not b for m, b in zip(right_m, right_b))
    only_b = sum(b and not m for m, b in zip(right_m, right_b))
    p_value = mcnemar_exact(only_m, only_b)
    acc, n = sum(right_m), len(yte)
    lo, hi = wilson(acc, n)
    blo, bhi = wilson(sum(right_b), n)
    kinds = sorted(set(ytr) | set(yte))
    f1 = f1_score(yte, pred, labels=kinds, average=None, zero_division=0)
    support = Counter(yte)
    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "sklearn": sklearn.__version__, "trained": time.strftime("%Y-%m-%dT%H:%M%z"),
                 "train_size": len(train), "held_out_accuracy": acc / n}, MODEL_OUT, compress=3)
    metrics = {"held_out": n, "train": len(train), "accuracy": round(acc / n, 4), "accuracy_ci95": [round(lo, 4), round(hi, 4)],
               "macro_f1": round(float(f1_score(yte, pred, average="macro", zero_division=0)), 4),
               "baseline_accuracy": round(sum(right_b) / n, 4), "baseline_ci95": [round(blo, 4), round(bhi, 4)],
               "mcnemar": {"model_only": only_m, "baseline_only": only_b, "p": float(f"{p_value:.3g}")},
               "sources": dict(Counter(labels[i]["source"] for i in labels))}
    (HERE / "metrics.json").write_text(json.dumps(metrics, indent=1) + "\n")
    cm = confusion_matrix(yte, pred, labels=kinds)
    lines = ["# Notice kinds: results", "",
             f"Trained {time.strftime('%d/%m/%Y %H:%M')} on {len(train)} notices; tested on the {n} held out in `split.json` before any training.",
             "Labels are the service's own language model's (gpt-4.1-mini): the kind it gave while writing a summary, or the answer to a kind-only question.",
             "So these numbers measure agreement with those labels: the model reproduces them without a model call.", "",
             "| | Right on the held-out set | 95% Wilson interval |", "|---|---|---|",
             f"| This model (word and character n-grams, logistic regression) | {acc} of {n} ({acc / n:.1%}) | {lo:.1%} to {hi:.1%} |",
             f"| Baseline: the most common kind for each notice code | {sum(right_b)} of {n} ({sum(right_b) / n:.1%}) | {blo:.1%} to {bhi:.1%} |", "",
             f"Exact McNemar test on the paired results: the model alone right on {only_m}, the baseline alone right on {only_b}, p = {p_value:.2g}.",
             f"Macro-averaged F1 across kinds: {metrics['macro_f1']:.2f}.", "", "| Kind | Held out | F1 |", "|---|---|---|"]
    lines += [f"| {k} | {support.get(k, 0)} | {v:.2f} |" for k, v in zip(kinds, f1)]
    lines += ["", "Confusion (rows: label; columns: model, in the order of the table above):", "", "```"]
    lines += [f"{k[:28]:<28} " + " ".join(f"{c:>3}" for c in row) for k, row in zip(kinds, cm)]
    lines += ["```", ""]
    (HERE / "RESULTS.md").write_text("\n".join(lines))
    print("\n".join(lines[:12]))


def main() -> None:
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="cmd", required=True)
    x = s.add_parser("snapshot"); x.add_argument("--db", required=True)
    x = s.add_parser("label"); x.add_argument("--limit", type=int, default=5000); x.add_argument("--workers", type=int, default=4)
    x = s.add_parser("split"); x.add_argument("--force", action="store_true")
    s.add_parser("train")
    a = p.parse_args()
    {"snapshot": cmd_snapshot, "label": cmd_label, "split": cmd_split, "train": cmd_train}[a.cmd](a)


if __name__ == "__main__":
    main()

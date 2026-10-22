"""Turn the saved hand checks (heldout_checks.json from CHECK_SHEET.html) into gold.jsonl.

Every line must have a verdict. A field marked Wrong takes the typed answer (several answers split on ";",
"not stated" means the notice does not say). A sentence marked Wrong has its TRUE/FALSE label flipped.
Every change is printed so it can be reviewed before the run.
Run: uv run python evals/heldout/apply_checks.py [path/to/heldout_checks.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))
from nearby_notices.extract import KINDS

LISTS = {"authority", "kind", "starts", "ends", "places_include", "places_exclude"}


def find_checks(arg: str | None) -> Path:
    for p in [Path(arg)] if arg else [HERE / "heldout_checks.json", Path.home() / "Downloads" / "heldout_checks.json"]:
        if p.exists():
            return p
    raise SystemExit("heldout_checks.json not found: save it from CHECK_SHEET.html, or pass its path")


def parse(key: str, text: str):
    text = text.strip()
    if key == "objection":
        return text.lower().startswith("y")
    return [None if part.strip().lower() in {"not stated", "none", ""} else part.strip() for part in text.split(";")]


def main() -> None:
    path = find_checks(sys.argv[1] if len(sys.argv) > 1 else None)
    checks = {n["id"]: n for n in json.loads(path.read_text(encoding="utf-8"))["notices"]}
    gold, changes, unchecked = [], [], []
    for raw in (HERE / "gold_draft.jsonl").read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        g = json.loads(raw)
        c = checks.get(g["id"], {"lines": [], "note": ""})
        verdicts = {line["key"]: line for line in c["lines"]}
        for key in ["authority", "kind", "starts", "ends", "objection", "places_include", "places_exclude"] + [f"claim{i}" for i in range(len(g["claims"]))]:
            v = verdicts.get(key, {})
            if v.get("verdict") not in {"right", "wrong"}:
                unchecked.append(f"{g['id']} {key}")
            elif v["verdict"] == "wrong":
                if key.startswith("claim"):
                    claim = g["claims"][int(key[5:])]
                    claim["true"] = not claim["true"]
                    changes.append(f"{g['id']} {key}: label flipped to {'TRUE' if claim['true'] else 'FALSE'} ({v.get('correction', '')})")
                elif not v.get("correction", "").strip():
                    unchecked.append(f"{g['id']} {key} (marked Wrong with no answer typed)")
                else:
                    g[key] = parse(key, v["correction"])
                    if key == "kind":
                        unknown = [k for k in g[key] if k not in KINDS]
                        if unknown:
                            unchecked.append(f"{g['id']} kind: {unknown} not in the fixed list ({', '.join(KINDS)})")
                    changes.append(f"{g['id']} {key}: {v['draft']} -> {g[key]}")
        if c.get("note"):
            changes.append(f"{g['id']} note: {c['note']}")
        gold.append(g)
    if unchecked:
        raise SystemExit("not written: lines still to check:\n  " + "\n  ".join(unchecked))
    (HERE / "gold.jsonl").write_text("".join(json.dumps(g, ensure_ascii=False) + "\n" for g in gold), encoding="utf-8")
    print(f"wrote gold.jsonl from {path}: {len(gold)} notices, {len(changes)} changes")
    for line in changes:
        print("  " + line)


if __name__ == "__main__":
    main()

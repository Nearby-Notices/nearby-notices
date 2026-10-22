"""The pre-registered leak test (evals/leak/PREREGISTRATION.md): can a sentence the notice does not support get past the gate?

  uv run python evals/leak_test.py fetch     fetches new public notices into evals/leak/notices (never used to build the service)
  uv run python evals/leak_test.py make      builds evals/leak/unsupported.jsonl (330 sentences, seed 2026)
  uv run python evals/leak_test.py run       calls the live gate on each, writes evals/leak/results/<stamp>.json
  uv run python evals/leak_test.py report    writes evals/leak/LEAK_TEST.md from the latest run

Each sentence is a true sentence with exactly one fact changed to a value that appears nowhere in the notice.
"""

from __future__ import annotations

import codecs
import json
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evals"))

import stats

EVALS = ROOT / "evals"
CONFIRM = os.environ.get("LEAK_SET") == "confirm"      # the fresh confirmation set (PREREGISTRATION.md, part 2)
OUT = EVALS / "leak" / "confirm" if CONFIRM else EVALS / "leak"
SIZE, SEED = 330, (2027 if CONFIRM else 2026)

UNITS = (r"days?|weeks?|months?|years?|metres?|meters?|m|km|kilometres?|miles?|hectares?|ha|MW|megawatts?|kV|kilovolts?|"
         r"turbines?|houses|homes|dwellings|storeys|tonnes|%|per cent")
NUM_UNIT = re.compile(rf"\b(\d{{1,4}}(?:\.\d+)?)(\s*)({UNITS})\b")
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
DATE = re.compile(rf"\b(\d{{1,2}})(st|nd|rd|th)?\s+({'|'.join(MONTHS)})\s+(\d{{4}})\b")
WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty"]
TENS = {20: "twenty", 30: "thirty", 40: "forty", 50: "fifty", 60: "sixty"}


def norm(s: str) -> str:
    s = (s or "").lower().replace("’", "'").replace("‘", "'")
    return re.sub(r"[^a-z0-9.%]+", " ", s).strip()


def has(text_norm: str, fragment: str) -> bool:
    f = norm(fragment)
    return bool(f) and f" {f} " in f" {text_norm} "


def number_word(n: int) -> str | None:
    if n < 20:
        return WORDS[n]
    if n <= 60:
        t, u = divmod(n, 10)
        return TENS[t * 10] + ("" if u == 0 else f" {WORDS[u]}")
    return None


def load_text(nid: str) -> str:
    path = EVALS / "notices" / f"{nid}.txt"
    for path in (EVALS / "notices" / f"{nid}.txt", EVALS / "leak" / "notices" / f"{nid}.txt", OUT / "notices" / f"{nid}.txt"):
        if path.exists():
            break
    raw = path.read_text(encoding="utf-8")
    return raw.split("\n", 1)[1] if raw.startswith("#") else raw


def number_ok(tn: str, value: str, unit: str) -> bool:
    if has(tn, value):
        return False
    if CONFIRM and re.search(rf"(?<![\d.]){re.escape(value)}(?![\d])", tn):
        return False                                  # the first test's review: "28m" also counts as 28 appearing
    try:
        n = float(value)
    except ValueError:
        return False
    if n.is_integer():
        w = number_word(int(n))
        if w and has(tn, w):
            return False
        if unit.lower().startswith("day") and int(n) % 7 == 0:
            weeks = int(n) // 7
            if has(tn, f"{weeks} week") or has(tn, f"{weeks} weeks") or (number_word(weeks) and has(tn, f"{number_word(weeks)} week")):
                return False
    return True


def number_changes(sentence: str, tn: str):
    for m in NUM_UNIT.finditer(sentence):
        value, unit = m.group(1), m.group(3)
        n = float(value)
        is_int = n.is_integer()
        cands = [n + 7, n * 2, n + 3, n + 1] if n > 0 else [7, 3]
        for c in cands:
            cv = str(int(c)) if is_int else f"{c:g}"
            if cv != value and number_ok(tn, cv, unit):
                new = sentence[: m.start(1)] + cv + sentence[m.end(1):]
                yield "number", f"{value} {unit} -> {cv} {unit}", new
                break


def date_changes(sentence: str, tn: str):
    for m in DATE.finditer(sentence):
        day, suffix, month, year = int(m.group(1)), m.group(2) or "", m.group(3), m.group(4)
        nd = day + 7 if day + 7 <= 28 else day - 7
        if nd < 1:
            continue
        new_date = f"{nd} {month} {year}"
        if has(tn, new_date) or has(tn, f"{nd} {month}") or has(tn, f"{nd}{'th' if suffix else ''} {month}"):
            continue
        if suffix and CONFIRM:                       # "2nd" moved by 7 is "9th", not "9nd"
            suffix = "th" if 11 <= nd <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(nd % 10, "th")
        rebuilt = f"{nd}{suffix} {month} {year}" if suffix else new_date
        new = sentence[: m.start()] + rebuilt + sentence[m.end():]
        yield "date", f"{m.group(0)} -> {rebuilt}", new


def name_changes(sentence: str, tn: str, own: dict, pool: dict, rng: random.Random):
    for kind in ("places_include", "authority"):
        for name in own.get(kind, []):
            if not name or len(name) < 4:
                continue
            m = re.search(rf"\b{re.escape(name)}\b", sentence, flags=re.IGNORECASE)
            if not m:
                continue
            options = [p for p in pool[kind] if p and len(p) >= 4 and not has(tn, p) and norm(p) != norm(name)]
            if not options:
                continue
            pick = rng.choice(sorted(set(options)))
            new = sentence[: m.start()] + pick + sentence[m.end():]
            yield "name", f"{m.group(0)} -> {pick}", new


def notice_sentences(text: str) -> list[str]:
    body = "\n".join(text.splitlines()[2:])                      # skip the title and the Gazette metadata line
    parts = re.split(r"(?<=[.!?])\s+|\n+", body)
    out = []
    for p in parts:
        p = " ".join(p.split())
        n = len(p.split())
        if (8 <= n <= 45 and not re.search(r"https?://|www\.|@|\.gov\.uk|\.co\.uk|\.com|Notice category:|Publication date:|Notice ID",
                                            p, flags=re.IGNORECASE)
                and not INITIAL_NAME.search(p) and not PERSON.search(p)):
            out.append(p)
    return out


# Public buildings (council offices and city halls) spread across the four nations, as search centres.
CENTRES = ["IV3 5NX", "G2 1DU", "EH1 1YJ", "AB10 1AB", "BT1 5GS", "CF10 4UW", "SA1 3SN", "LS1 1UR", "NE1 8QH",
           "BS1 5TR", "NR2 1NH", "EX1 1JN", "B3 3DH", "M2 5DB", "SW1A 2AA"]
PERSON = re.compile(r"\b(Mr|Mrs|Ms|Miss|Dr)\.?\s+[A-Z]")
INITIAL_NAME = re.compile(r"\b[A-Z]\.?\s+[A-Z][a-z]{2,}\b")       # "S Lawrence": a signatory's name
PRIVATE_PLACES = re.compile(codecs.decode("cvgybpuel|cu16", "rot13"), re.IGNORECASE)   # places never published; kept out of the text


def fetch(target: int = 45, radius: int = 10, per_centre: int | None = None) -> None:
    from nearby_notices import gazette

    taken = {p.stem for d in (EVALS / "notices", EVALS / "heldout" / "notices", EVALS / "leak" / "notices") for p in d.glob("*.txt")}
    dest = OUT / "notices"
    dest.mkdir(parents=True, exist_ok=True)
    taken |= {p.stem for p in dest.glob("*.txt")}
    got, per_centre = 0, per_centre or max(2, target // len(CENTRES) + 1)
    for pc in CENTRES:
        try:
            found = gazette.search_near(pc, radius, since="2026-07-01", max_pages=1)
        except Exception as e:  # noqa: BLE001 (one failed centre is skipped)
            print("skip", pc, e)
            continue
        n_here = 0
        for n in found:
            if n.id in taken or n_here >= per_centre or got >= target:
                continue
            text = n.text if len(n.text.split()) > 150 else gazette.full_text(n.id)
            words = len(text.split())
            if not 120 <= words <= 2700 or PERSON.search(text) or PRIVATE_PLACES.search(text):
                continue                                  # too short or long, or names a private individual
            if not (NUM_UNIT.search(text) or DATE.search(text)):
                continue
            (dest / f"{n.id}.txt").write_text(f"# {n.id} | {n.category} | {n.published[:10]} | {n.url}\n{n.category}\n\n{text}\n",
                                              encoding="utf-8")
            taken.add(n.id)
            got += 1
            n_here += 1
        print(pc, n_here, "taken; total", got)
        if got >= target:
            break


def make() -> None:
    rng = random.Random(SEED)
    gold = [json.loads(line) for line in (EVALS / "gold.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    pool = defaultdict(list)
    if CONFIRM:
        gold = []                                     # fresh notices only: nothing the gate rule was shaped on
    for g in gold:
        for kind in ("places_include", "authority"):
            pool[kind] += [x for x in g.get(kind, []) if isinstance(x, str)]
    extra = [{"id": p.stem, "claims": []} for p in sorted((OUT / "notices").glob("*.txt"))] if (OUT / "notices").exists() else []
    items, seen = [], set()
    for g in gold + extra:
        text = load_text(g["id"])
        tn = norm(text)
        bases = [("hand-written", c["s"]) for c in g["claims"] if c["true"]] + [("copied", s) for s in notice_sentences(text)]
        for base_kind, s in bases:
            changes = list(number_changes(s, tn)) + list(date_changes(s, tn)) + list(name_changes(s, tn, g, pool, rng))
            for change_kind, change, new in changes:
                key = (g["id"], new)
                if new == s or key in seen:
                    continue
                seen.add(key)
                items.append({"id": g["id"], "base": base_kind, "change_kind": change_kind, "change": change,
                              "original": s, "sentence": new})
    cells = defaultdict(list)
    for it in items:
        cells[(it["change_kind"], it["base"])].append(it)
    for v in cells.values():
        rng.shuffle(v)
    chosen, order = [], sorted(cells)
    while len(chosen) < SIZE and any(cells[k] for k in order):          # round robin: as even as the pool allows
        for k in order:
            if cells[k] and len(chosen) < SIZE:
                chosen.append(cells[k].pop())
    OUT.mkdir(exist_ok=True)
    (OUT / "unsupported.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chosen), encoding="utf-8")
    print(f"pool {len(items)}; chosen {len(chosen)}")
    print(" by cell:", dict(Counter((c["change_kind"], c["base"]) for c in chosen)))
    print(" notices used:", len({c["id"] for c in chosen}))


def run() -> None:
    from nearby_notices import config, extract

    items = [json.loads(line) for line in (OUT / "unsupported.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    texts = {i["id"]: load_text(i["id"]) for i in items}
    t0 = time.time()

    def one(it):
        kept, quotes = extract.gate(texts[it["id"]], it["sentence"])
        return {**it, "kept": kept, "quotes": quotes}

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(one, items))
    stamp = time.strftime("%Y-%m-%dT%H-%M-%S")
    out = {"stamp": stamp, "model": config.MODEL, "seconds": round(time.time() - t0, 1), "n": len(results),
           "kept": sum(r["kept"] for r in results), "results": results}
    (OUT / "results").mkdir(exist_ok=True)
    (OUT / "results" / f"{stamp}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{out['n']} sentences, {out['kept']} let through, {out['seconds']} s, model {out['model']}")
    for r in results:
        if r["kept"]:
            print(f"  LET THROUGH {r['id']} [{r['change_kind']}/{r['base']}] {r['change']}: {r['sentence'][:110]}")


def exact_upper(k: int, n: int, conf: float = 0.95) -> float:
    """Clopper-Pearson one-sided upper bound, by bisection on the binomial tail."""
    from math import comb
    lo, hi = 0.0, 1.0
    for _ in range(60):
        p = (lo + hi) / 2
        tail = sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))
        lo, hi = (p, hi) if tail > 1 - conf else (lo, p)
    return hi


def report() -> None:
    runs = sorted((OUT / "results").glob("*.json"))
    d = json.loads(runs[0].read_text(encoding="utf-8"))           # the pre-registered run is the first; later runs are not independent
    excluded = set(json.loads((OUT / "excluded.json").read_text())) if (OUT / "excluded.json").exists() else set()
    res = [r for r in d["results"] if r["sentence"] not in excluded]
    n, k = len(res), sum(r["kept"] for r in res)
    lines = [
        "# Leak test: unsupported sentences against the gate", "",
        f"Run {d['stamp']} on `{d['model']}`, {d['seconds']} s. Design filed first: `PREREGISTRATION.md`.", "",
        f"- **Tested:** {n} sentences the notice does not support ({len(d['results']) - n} removed on review as construction errors).",
        f"- **Let through:** {k}.",
    ]
    if k == 0:
        lines.append(f"- **Leak rate:** below {stats.zero_failure_upper(n):.1%} at 95% confidence (exact one-sided bound, 0 of {n}).")
    else:
        lo, hi = stats.wilson(k, n)
        lines.append(f"- **Leak rate:** {k / n:.1%} (95% Wilson interval {lo:.1%} to {hi:.1%}; exact one-sided upper bound "
                     f"{exact_upper(k, n):.1%}).")
    lines += ["", "| Kind of change | Base sentence | Tested | Let through |", "|---|---|---|---|"]
    by = defaultdict(lambda: [0, 0])
    for r in res:
        by[(r["change_kind"], r["base"])][0] += 1
        by[(r["change_kind"], r["base"])][1] += r["kept"]
    for (ck, b), (t, kk) in sorted(by.items()):
        lines.append(f"| {ck} | {b} | {t} | {kk} |")
    leaks = [r for r in res if r["kept"]]
    if leaks:
        lines += ["", "## Every sentence let through", ""]
        lines += [f"- {r['id']} ({r['change_kind']}, {r['change']}): \"{r['sentence']}\" quotes: {r['quotes']}" for r in leaks]
    later = runs[1:]
    if later:
        lines += ["", "## Later runs on the same set (not independent: any change made after the first run was shaped on it)", ""]
        for f in later:
            r2 = json.loads(f.read_text(encoding="utf-8"))
            kept2 = [r for r in r2["results"] if r["kept"] and r["sentence"] not in excluded]
            lines.append(f"- {r2['stamp']}: {len(kept2)} of {len([r for r in r2['results'] if r['sentence'] not in excluded])} let through"
                         + (": " + "; ".join(f"{r['id']} ({r['change']})" for r in kept2) if kept2 else "."))
    (OUT / "LEAK_TEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    {"fetch": fetch, "make": make, "run": run, "report": report}[sys.argv[1] if len(sys.argv) > 1 else "make"]()

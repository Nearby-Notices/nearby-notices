"""Write CHECK_SHEET.html: an interactive page for checking the held-out draft labels by hand.

Each draft label gets a Right / Wrong choice and a box for the correct answer. Answers save in the
browser as you go, and "Save answers" writes them to heldout_checks.json, which apply_checks.py
turns into gold.jsonl. Run: uv run python evals/heldout/make_check_sheet.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1]))
from nearby_notices.extract import KINDS

STAMP = "22/10/2026-19:03 (BST)  (2026-10-22T18:03Z)"

FIELDS = [
    ("authority", "Who is behind it (any of)"),
    ("kind", "Kind (any of)"),
    ("starts", "Start date (any of)"),
    ("ends", "End date or deadline (any of)"),
    ("objection", "Says how or by when to object"),
    ("places_include", "Places affected that a reader must find"),
    ("places_exclude", "Addresses that are NOT places affected (for inspection or post only)"),
]


def shown(key: str, value) -> str:
    if key == "objection":
        return "yes" if value else "no"
    items = ["not stated" if v is None else str(v) for v in value]
    return "; ".join(items) if items else "none listed"


def notice_text(nid: str) -> tuple[str, str]:
    lines = (HERE / "notices" / f"{nid}.txt").read_text(encoding="utf-8").splitlines()
    head = lines[0].lstrip("# ").split(" | ")
    link = head[3].split("/data.html")[0] if len(head) > 3 else f"https://www.thegazette.co.uk/notice/{nid}"
    return link, "\n".join(lines[1:]).strip()


def build() -> list[dict]:
    notices = []
    for raw in (HERE / "gold_draft.jsonl").read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        g = json.loads(raw)
        link, text = notice_text(g["id"])
        lines = [{"key": k, "label": label, "draft": shown(k, g[k])} for k, label in FIELDS]
        for i, c in enumerate(g["claims"]):
            lines.append({"key": f"claim{i}", "label": "TRUE" if c["true"] else "FALSE", "draft": c["s"], "claim": True})
        notices.append({"id": g["id"], "category": g["category"], "link": link, "text": text, "lines": lines})
    return notices


def main() -> None:
    data = json.dumps(build(), ensure_ascii=False).replace("</", "<\\/")
    page = TEMPLATE.replace("__DATA__", data).replace("__KINDS__", json.dumps(", ".join(KINDS))).replace("__STAMP__", STAMP)
    (HERE / "CHECK_SHEET.html").write_text(page, encoding="utf-8")
    print("wrote", HERE / "CHECK_SHEET.html")


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Held-out label check</title>
<style>
:root{--ink:#1d2430;--muted:#5a6475;--line:#d5dae2;--bg:#eef1f5;--panel:#fff;--brand:#0b4f9c;--ok:#1d7a3a;--okbg:#e3f3e8;--bad:#b42318;--badbg:#fde8e6}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 Arial,Helvetica,sans-serif}
header{position:sticky;top:0;z-index:5;background:#1d2430;color:#fff;padding:10px 16px;display:flex;flex-wrap:wrap;gap:10px;align-items:center}
header h1{font-size:17px;margin:0 12px 0 0}
.bar{flex:1 1 220px;height:10px;background:#3a4454;border-radius:5px;overflow:hidden;min-width:160px}
.bar span{display:block;height:100%;background:#4cc27a;width:0}
#count{font-size:14px;white-space:nowrap}
header button{background:#fff;color:#1d2430;border:0;border-radius:6px;padding:7px 12px;font-weight:bold;cursor:pointer}
header button.primary{background:#4cc27a;color:#0c2414}
#saved{font-size:13px;color:#c9d2de;width:100%}
main{max-width:980px;margin:0 auto;padding:16px}
.intro,.notice{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin-bottom:16px}
.intro ol{margin:6px 0 0 20px;padding:0}
.meta{color:var(--muted);font-size:13px}
.notice h2{font-size:17px;margin:0 0 2px;display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
.badge{font-size:12px;padding:2px 8px;border-radius:10px;background:#e5e9ef;color:var(--muted);font-weight:normal}
.badge.done{background:var(--okbg);color:var(--ok)}
.badge.issues{background:var(--badbg);color:var(--bad)}
details{margin:8px 0 10px}
summary{cursor:pointer;color:var(--brand);font-weight:bold}
pre.text{white-space:pre-wrap;font:13px/1.45 Georgia,serif;background:#f7f8fa;border:1px solid var(--line);border-radius:6px;padding:10px;max-height:360px;overflow:auto}
.line{display:grid;grid-template-columns:1fr auto;gap:6px 12px;padding:9px 0;border-top:1px solid var(--line)}
.line .what{font-size:13px;color:var(--muted)}
.line .draft{font-weight:bold}
.line.claim .draft{font-weight:normal}
.tag{display:inline-block;font-size:12px;font-weight:bold;padding:1px 7px;border-radius:4px;margin-right:6px}
.tag.TRUE{background:var(--okbg);color:var(--ok)}.tag.FALSE{background:var(--badbg);color:var(--bad)}
.choice{display:flex;gap:6px;align-items:start}
.choice button{border:2px solid var(--line);background:#fff;border-radius:6px;padding:6px 12px;font-weight:bold;cursor:pointer;min-width:84px}
.choice button.right[aria-pressed=true]{background:var(--ok);border-color:var(--ok);color:#fff}
.choice button.wrong[aria-pressed=true]{background:var(--bad);border-color:var(--bad);color:#fff}
.fix{grid-column:1/-1}
.fix input{width:100%;padding:7px;border:2px solid var(--bad);border-radius:6px;font-size:14px}
.line.isright{background:linear-gradient(90deg,var(--okbg),transparent 60%)}
.line.iswrong{background:linear-gradient(90deg,var(--badbg),transparent 60%)}
.note textarea{width:100%;min-height:44px;padding:7px;border:1px solid var(--line);border-radius:6px;font:14px Arial,sans-serif}
.allright{margin-top:8px;background:#fff;border:1px solid var(--ok);color:var(--ok);border-radius:6px;padding:5px 10px;cursor:pointer;font-weight:bold}
@media (max-width:640px){.line{grid-template-columns:1fr}}
</style></head><body>
<header>
  <h1>Held-out label check</h1>
  <div class="bar"><span id="fill"></span></div>
  <span id="count"></span>
  <button id="next">Next unchecked</button>
  <button id="save" class="primary">Save answers</button>
  <button id="load">Load answers</button>
  <input id="file" type="file" accept=".json,application/json" hidden>
  <div id="saved"></div>
</header>
<main>
<section class="intro">
  <p class="meta"><b>Created:</b> __STAMP__ &nbsp; <b>Last updated:</b> __STAMP__<br><b>Written for:</b> the person checking the labels. 23 notices, about 5 minutes each. Do it in two sittings; your answers are kept between sittings.</p>
  <p>These notices were never used to build or tune Nearby Notices, so they give an honest test. I drafted every label. Nothing counts until you have checked it.</p>
  <p><b>For each notice:</b></p>
  <ol>
    <li>Click <b>Show the notice text</b> (or open the Gazette link) and read the notice.</li>
    <li>For each line, press <b>Right</b> or <b>Wrong</b>. If you press Wrong, type the right answer in the red box.</li>
    <li>The four sentences are labelled TRUE or FALSE. Press Right if the label is right for that sentence, Wrong if it is not.</li>
    <li>If every line of a notice is right, the green <b>All right</b> button marks the whole notice in one go.</li>
  </ol>
  <p><b>When you finish, or stop for the day:</b> press <b>Save answers</b>. If the browser asks where, save it in the <code>evals/heldout</code> folder as <code>heldout_checks.json</code>. If it saves straight to Downloads, that is fine too. Then tell me "labels checked".</p>
</section>
<div id="notices"></div>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const KEY = 'nn-heldout-checks-v1';
const KINDS = __KINDS__;
let state = {notices: {}};
try { const s = localStorage.getItem(KEY); if (s) state = JSON.parse(s); } catch (e) {}
let handle = null;

const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const ns = id => (state.notices[id] = state.notices[id] || {lines: {}, note: ''});
const store = () => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} };

function render() {
  const root = document.getElementById('notices');
  root.innerHTML = '';
  DATA.forEach((n, i) => {
    const sec = el('section', 'notice'); sec.id = 'n' + n.id;
    const h = el('h2'); h.append(el('span', null, (i + 1) + '. ' + n.category + ', notice ' + n.id));
    const badge = el('span', 'badge'); badge.dataset.id = n.id; h.append(badge); sec.append(h);
    const a = el('a', null, 'Open the notice on The Gazette'); a.href = n.link; a.target = '_blank'; a.rel = 'noopener';
    sec.append(a);
    const d = el('details'); d.append(el('summary', null, 'Show the notice text')); d.append(el('pre', 'text', n.text)); sec.append(d);
    n.lines.forEach(L => sec.append(lineRow(n, L)));
    const all = el('button', 'allright', 'All right: mark every unchecked line Right');
    all.onclick = () => { n.lines.forEach(L => { const s = ns(n.id).lines[L.key] || {}; if (!s.verdict) ns(n.id).lines[L.key] = {verdict: 'right', correction: ''}; }); store(); render(); };
    sec.append(all);
    const note = el('div', 'note'); note.append(el('p', 'what', 'Anything else about this notice (optional)'));
    const ta = el('textarea'); ta.value = ns(n.id).note || ''; ta.oninput = () => { ns(n.id).note = ta.value; store(); };
    note.append(ta); sec.append(note);
    root.append(sec);
  });
  progress();
}

function lineRow(n, L) {
  const s = ns(n.id).lines[L.key] || {};
  const row = el('div', 'line' + (L.claim ? ' claim' : '') + (s.verdict === 'right' ? ' isright' : s.verdict === 'wrong' ? ' iswrong' : ''));
  const left = el('div');
  if (L.claim) { left.append(el('div', 'what', 'Sentence, labelled')); const p = el('div', 'draft'); p.append(el('span', 'tag ' + L.label, L.label)); p.append(document.createTextNode(L.draft)); left.append(p); }
  else { left.append(el('div', 'what', L.label)); left.append(el('div', 'draft', L.draft)); }
  row.append(left);
  const c = el('div', 'choice');
  [['right', 'Right'], ['wrong', 'Wrong']].forEach(([v, t]) => {
    const b = el('button', v, t); b.type = 'button'; b.setAttribute('aria-pressed', s.verdict === v ? 'true' : 'false');
    b.onclick = () => { const cur = ns(n.id).lines[L.key] || {}; ns(n.id).lines[L.key] = {verdict: cur.verdict === v ? '' : v, correction: cur.correction || ''}; store(); row.replaceWith(lineRow(n, L)); progress(); };
    c.append(b);
  });
  row.append(c);
  if (s.verdict === 'wrong') {
    const f = el('div', 'fix'); const inp = el('input');
    inp.placeholder = L.claim ? 'Why is the label wrong? (for example: this sentence is actually true)' : L.key === 'kind' ? 'Type the right kind, from this list: ' + KINDS : 'Type the right answer (several answers: separate them with ;)';
    inp.value = s.correction || ''; inp.oninput = () => { ns(n.id).lines[L.key].correction = inp.value; store(); };
    f.append(inp); row.append(f);
  }
  return row;
}

function counts() {
  let total = 0, done = 0, wrong = 0, noticesDone = 0;
  DATA.forEach(n => { let nd = 0; n.lines.forEach(L => { total++; const s = (state.notices[n.id] || {lines: {}}).lines[L.key]; if (s && s.verdict) { done++; nd++; if (s.verdict === 'wrong') wrong++; } }); if (nd === n.lines.length) noticesDone++; });
  return {total, done, wrong, noticesDone};
}

function progress() {
  const c = counts();
  document.getElementById('fill').style.width = (100 * c.done / c.total) + '%';
  document.getElementById('count').textContent = c.done + ' of ' + c.total + ' lines checked, ' + c.noticesDone + ' of ' + DATA.length + ' notices done, ' + c.wrong + ' wrong';
  document.querySelectorAll('.badge').forEach(b => {
    const n = DATA.find(x => x.id === b.dataset.id); const s = state.notices[n.id] || {lines: {}};
    const d = n.lines.filter(L => s.lines[L.key] && s.lines[L.key].verdict).length;
    const w = n.lines.filter(L => s.lines[L.key] && s.lines[L.key].verdict === 'wrong').length;
    b.className = 'badge' + (d === n.lines.length ? (w ? ' issues' : ' done') : '');
    b.textContent = d === n.lines.length ? (w ? 'done, ' + w + ' wrong' : 'done, all right') : d + ' of ' + n.lines.length + ' checked';
  });
}

function exportData() {
  const c = counts();
  return {
    sheet: 'Nearby Notices held-out labels: hand check', source: 'evals/heldout/gold_draft.jsonl', checker: 'hand check',
    saved_at: new Date().toISOString(), lines_total: c.total, lines_checked: c.done, lines_wrong: c.wrong,
    notices: DATA.map(n => { const s = state.notices[n.id] || {lines: {}, note: ''}; return {
      id: n.id, category: n.category, link: n.link, note: s.note || '',
      lines: n.lines.map(L => { const v = s.lines[L.key] || {}; return {key: L.key, label: L.label, draft: L.draft, verdict: v.verdict || '', correction: v.correction || ''}; })
    }; })
  };
}

document.getElementById('save').onclick = async () => {
  const text = JSON.stringify(exportData(), null, 1);
  const msg = document.getElementById('saved');
  try {
    if (window.showSaveFilePicker) {
      if (!handle) handle = await window.showSaveFilePicker({suggestedName: 'heldout_checks.json', types: [{description: 'JSON', accept: {'application/json': ['.json']}}]});
      const w = await handle.createWritable(); await w.write(text); await w.close();
      msg.textContent = 'Saved to ' + handle.name + ' at ' + new Date().toLocaleTimeString() + '. Press Save again any time to update it.';
      return;
    }
  } catch (e) { if (e && e.name === 'AbortError') { msg.textContent = 'Not saved: no file chosen.'; return; } }
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], {type: 'application/json'}));
  a.download = 'heldout_checks.json'; document.body.append(a); a.click(); a.remove();
  msg.textContent = 'Saved heldout_checks.json to your Downloads folder at ' + new Date().toLocaleTimeString() + '.';
};

document.getElementById('load').onclick = () => document.getElementById('file').click();
document.getElementById('file').onchange = async e => {
  const f = e.target.files[0]; if (!f) return;
  try {
    const j = JSON.parse(await f.text());
    j.notices.forEach(n => { const s = ns(n.id); s.note = n.note || ''; n.lines.forEach(L => { if (L.verdict) s.lines[L.key] = {verdict: L.verdict, correction: L.correction || ''}; }); });
    store(); render(); document.getElementById('saved').textContent = 'Loaded answers from ' + f.name + '.';
  } catch (err) { document.getElementById('saved').textContent = 'That file could not be read as saved answers.'; }
};

document.getElementById('next').onclick = () => {
  for (const n of DATA) for (const L of n.lines) { const s = (state.notices[n.id] || {lines: {}}).lines[L.key]; if (!s || !s.verdict) { document.getElementById('n' + n.id).scrollIntoView({behavior: 'smooth'}); return; } }
  document.getElementById('saved').textContent = 'Every line is checked. Press Save answers.';
};

render();
</script>
</body></html>
"""

if __name__ == "__main__":
    main()

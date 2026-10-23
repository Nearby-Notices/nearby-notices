"""The gate as an Inspect task: the model's support judgement, checked in code, scored against hand-written labels.

    uv run --group evals inspect eval evals/inspect_gate.py --model openai/azure/gpt-4.1-mini --log-dir evals/inspect_logs
    (Azure OpenAI needs AZUREAI_OPENAI_API_KEY, AZUREAI_OPENAI_BASE_URL and AZUREAI_OPENAI_API_VERSION set)

The gate is an LLM judge with a code check on top. The model says whether a sentence is supported by the notice and
offers quotes; code keeps the sentence only if every quote is really in the notice. This task sends the prompt the
live service sends, applies the same code check (extract.gate_decision), and scores the decision against the label
of each hand-written true and false sentence in gold.jsonl. Metrics: accuracy with its standard error, and accuracy
grouped by label (true sentences kept; false sentences removed).

A second task, `leak`, runs the two pre-registered leak tests (evals/leak/) through the same scorer: 659 sentences the
notices do not support, each a true sentence with one fact changed, all of which should be removed. Grouped by set,
because the first set was used to design the numbers rule and only the fresh confirmation set measures it fairly.
    uv run --group evals inspect eval evals/inspect_gate.py@leak --model azureai/gpt-4.1-mini --log-dir evals/inspect_logs
It needs the fetched notices and generated sentences, which stay out of the public copy (many notices are signed by
named officials); `evals/leak_test.py fetch` and `make` rebuild a set of the same design.
"""
import json
import sys
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.model import ChatMessageSystem, ChatMessageUser, GenerateConfig
from inspect_ai.scorer import (
    CORRECT,
    INCORRECT,
    Score,
    Target,
    accuracy,
    grouped,
    scorer,
    stderr,
)
from inspect_ai.solver import TaskState, generate

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from nearby_notices import extract


def notice_text(nid: str) -> str:
    for d in ("notices", "leak/notices", "leak/confirm/notices"):
        path = ROOT / "evals" / d / f"{nid}.txt"
        if path.exists():
            break
    raw = path.read_text()
    return raw.split("\n", 1)[1] if raw.startswith("#") else raw


def samples() -> list[Sample]:
    out = []
    for line in (ROOT / "evals" / "gold.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        g = json.loads(line)
        text, _ = extract.scrub(notice_text(g["id"]))
        for i, c in enumerate(g["claims"]):
            user = extract.GATE_USER.format(text=extract.for_model(text), sentence=c["s"].replace('"', "'"))
            user = user.replace("\n/no_think", "")  # the live service drops this Qwen switch for other models
            out.append(Sample(
                id=f"{g['id']}-{i}",
                input=[ChatMessageSystem(content=extract.GATE_SYSTEM), ChatMessageUser(content=user)],
                target="kept" if c["true"] else "removed",
                metadata={"notice": g["id"], "label": "true sentences kept" if c["true"] else "false sentences removed", "text": text,
                          "sentence": c["s"]},
            ))
    return out


@scorer(metrics=[accuracy(), stderr(), grouped(accuracy(), "label", all=False)])
def gate_decision():
    async def score(state: TaskState, target: Target) -> Score:
        ok, quotes = extract.gate_decision(state.metadata["text"], extract._json(state.output.completion),
                                             state.metadata.get("sentence", ""))
        decision = "kept" if ok else "removed"
        return Score(value=CORRECT if decision == target.text else INCORRECT, answer=decision,
                     explanation="quotes: " + json.dumps(quotes, ensure_ascii=False))
    return score


@task
def gate() -> Task:
    return Task(dataset=MemoryDataset(samples()), solver=generate(), scorer=gate_decision(),
                config=GenerateConfig(temperature=0, max_tokens=300))


def leak_samples() -> list[Sample]:
    out = []
    excluded = set(json.loads((ROOT / "evals" / "leak" / "excluded.json").read_text()))
    for label, path in (("first leak test (used to design the numbers rule)", ROOT / "evals" / "leak" / "unsupported.jsonl"),
                        ("fresh confirmation set", ROOT / "evals" / "leak" / "confirm" / "unsupported.jsonl")):
        for i, line in enumerate(path.read_text().splitlines()):
            if not line.strip():
                continue
            it = json.loads(line)
            if it["sentence"] in excluded:                # the one item review found the notice did support
                continue
            text, _ = extract.scrub(notice_text(it["id"]))
            user = extract.GATE_USER.format(text=extract.for_model(text), sentence=it["sentence"].replace('"', "'"))
            user = user.replace("\n/no_think", "")
            out.append(Sample(
                id=f"{'confirm' if 'fresh' in label else 'first'}-{i}",
                input=[ChatMessageSystem(content=extract.GATE_SYSTEM), ChatMessageUser(content=user)],
                target="removed",
                metadata={"label": label, "kind": it["change_kind"], "text": text, "sentence": it["sentence"]},
            ))
    return out


@task
def leak() -> Task:
    return Task(dataset=MemoryDataset(leak_samples()), solver=generate(), scorer=gate_decision(),
                config=GenerateConfig(temperature=0, max_tokens=300))


@task
def leak_plugin() -> Task:
    """The fresh confirmation set scored by the packaged extension (inspect_quote_check/verbatim_quotes), not the
    service's own code: a check that the general-purpose scorer reaches the same decisions."""
    from inspect_quote_check import verbatim_quotes
    fresh = [s for s in leak_samples() if s.metadata["label"] == "fresh confirmation set"]
    return Task(dataset=MemoryDataset(fresh), solver=generate(), scorer=verbatim_quotes(source_field="text", claim_field="sentence"),
                config=GenerateConfig(temperature=0, max_tokens=300))

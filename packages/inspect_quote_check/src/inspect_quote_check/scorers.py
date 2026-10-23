"""verbatim_quotes: score a model's support judgement after checking its quotes against the source, in code."""
from __future__ import annotations

import json

from inspect_ai.scorer import CORRECT, INCORRECT, Score, Target, accuracy, scorer, stderr
from inspect_ai.solver import TaskState

from .check import decide


@scorer(metrics=[accuracy(), stderr()])
def verbatim_quotes(source_field: str = "text", claim_field: str = "claim", min_words: int = 2):
    """The sample's metadata holds the source text (source_field) and the claim (claim_field); the target is "kept"
    or "removed". The model's output must be JSON {"supported": bool, "quotes": [...]}."""

    async def score(state: TaskState, target: Target) -> Score:
        md = state.metadata or {}
        kept, quotes, reason = decide(md.get(source_field, ""), state.output.completion, md.get(claim_field, ""), min_words)
        decision = "kept" if kept else "removed"
        return Score(value=CORRECT if decision == target.text else INCORRECT, answer=decision,
                     explanation=reason + "; quotes: " + json.dumps(quotes, ensure_ascii=False))

    return score

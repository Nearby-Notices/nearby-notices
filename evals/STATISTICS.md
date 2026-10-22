# Evaluation statistics

Computed by `evals/stats.py` from the saved runs. Gold set: 21 notices. Intervals are 95% Wilson intervals.

## The latest run (22/10/2026 18:54 UTC, azure/gpt-4.1-mini)

| Measure | Result | 95% interval |
|---|---|---|
| False sentences removed (the safety number) | 42 of 42 | 91.6% to 100.0% |
| True sentences kept | 42 of 42 | 91.6% to 100.0% |
| Authority correct | 19 of 21 notices | 71.1% to 97.3% |
| Kind correct | 21 of 21 notices | 84.5% to 100.0% |
| Starts correct | 19 of 21 notices | 71.1% to 97.3% |
| Ends correct | 20 of 21 notices | 77.3% to 99.2% |
| Objection correct | 21 of 21 notices | 84.5% to 100.0% |

No false sentence got through, so the true leak rate is below **6.9%** at 95% confidence (exact one-sided bound). Showing it is below 1% would need about **299** false sentences with none getting through; below 2%, about 149.

## Paired comparisons on the same items

An exact McNemar test uses only the items where the two runs disagree. With few disagreements no difference can be called significant, however large it looks.

| Comparison | Items paired | Right only in the first | Right only in the second | Exact McNemar p |
|---|---|---|---|---|
| Gate, before against after the quote-rule fix (the model build also changed) | 84 | 0 | 4 | 0.125 |
| Gate, local 27B model against Azure OpenAI gpt-4.1-mini | 84 | 0 | 0 | 1.000 |
| Fields, local 27B model against Azure OpenAI gpt-4.1-mini | 105 | 5 | 0 | 0.062 |

**Reading the table.**

- Gate, before against after the quote-rule fix (the model build also changed): 4 of 84 paired items disagree, 4 in favour of the second run (exact McNemar p = 0.125, not significant at the 5% level).
- Gate, local 27B model against Azure OpenAI gpt-4.1-mini: the two runs agreed on all 84 paired items, so there is no detectable difference.
- Fields, local 27B model against Azure OpenAI gpt-4.1-mini: 5 of 105 paired items disagree, 5 in favour of the first run (exact McNemar p = 0.062, not significant at the 5% level).

Every statement is about these items only. A larger labelled set is the way to narrow them.

# Accuracy by subgroup

Computed by `evals/subgroups.py`. Gold set: 21 notices. Does the tool work as well on every kind of notice? It reads notices, not people, so the groups are where a notice comes from and what it looks like. Nations are assigned by hand in `subgroups.json`, with the evidence for each.

## The gate, by subgroup (19/10/2026 17:23 UTC, azure/gpt-4.1-mini)

| Group | Notices | False sentences removed | True leak rate is below (95%, exact) | True sentences kept |
|---|---|---|---|---|
| Nation: England | 7 | 14 of 14 | 19.3% | 14 of 14 |
| Nation: Scotland | 12 | 24 of 24 | 11.7% | 24 of 24 |
| Nation: Wales | 2 | 4 of 4 | 52.7% | 4 of 4 |
| Length: Under 300 words | 7 | 14 of 14 | 19.3% | 14 of 14 |
| Length: 300 to 700 words | 8 | 16 of 16 | 17.1% | 16 of 16 |
| Length: Over 700 words | 6 | 12 of 12 | 22.1% | 12 of 12 |
| Type: All other types | 14 | 28 of 28 | 10.1% | 28 of 28 |
| Type: Roads and highways | 7 | 14 of 14 | 19.3% | 14 of 14 |

**Reading.** Across the set, 42 of 42 false sentences were removed and 42 of 42 true ones kept. No false sentence got through in any group. The guarantee is weakest where there are fewest notices: with 4 false sentences (nation: Wales), the leak rate is only shown to be below 52.7%.

## All five fields right, by subgroup (Azure OpenAI, every notice scored: 18/10/2026 17:34 UTC, azure/gpt-4.1-mini)

Fields: authority, kind, start date, end date, objection sentence. Fisher p tests each group against the rest of the set.

| Group | Notices scored | All five right | 95% interval | Fisher exact p, group against the rest |
|---|---|---|---|---|
| Nation: England | 7 | 6 | 48.7% to 97.4% | 0.624 |
| Nation: Scotland | 12 | 8 | 39.1% to 86.2% | 0.338 |
| Nation: Wales | 2 | 2 | 34.2% to 100.0% | 1.000 |
| Length: Under 300 words | 7 | 5 | 35.9% to 91.8% | 1.000 |
| Length: 300 to 700 words | 8 | 6 | 40.9% to 92.9% | 1.000 |
| Length: Over 700 words | 6 | 5 | 43.6% to 97.0% | 1.000 |
| Type: All other types | 14 | 11 | 52.4% to 92.4% | 1.000 |
| Type: Roads and highways | 7 | 5 | 35.9% to 91.8% | 1.000 |

**Reading.** 16 of 21 notices had all five fields right. The biggest gap is nation: Scotland: 8 of 12, against 8 of 9 for the rest (Fisher exact p = 0.338). No group differs from the rest at the 5% level.

## All five fields right, by subgroup (local 27B model: 17/10/2026 21:49 UTC, openai/qwen3.8-27b-ablit)

Fields: authority, kind, start date, end date, objection sentence. Fisher p tests each group against the rest of the set.

| Group | Notices scored | All five right | 95% interval | Fisher exact p, group against the rest |
|---|---|---|---|---|
| Nation: England | 7 | 7 | 64.6% to 100.0% | 1.000 |
| Nation: Scotland | 12 | 11 | 64.6% to 98.5% | 1.000 |
| Nation: Wales | 2 | 2 | 34.2% to 100.0% | 1.000 |
| Length: Under 300 words | 7 | 7 | 64.6% to 100.0% | 1.000 |
| Length: 300 to 700 words | 8 | 8 | 67.6% to 100.0% | 1.000 |
| Length: Over 700 words | 6 | 5 | 43.6% to 97.0% | 0.286 |
| Type: All other types | 14 | 13 | 68.5% to 98.7% | 1.000 |
| Type: Roads and highways | 7 | 7 | 64.6% to 100.0% | 1.000 |

**Reading.** 20 of 21 notices had all five fields right. The biggest gap is length: Over 700 words: 5 of 6, against 15 of 15 for the rest (Fisher exact p = 0.286). No group differs from the rest at the 5% level.

## What this does and does not show

- Groups are small: two notices are Welsh, so nothing can be said about Wales beyond these counts. A difference has to be large to show up at this size; no detectable difference is not evidence of equal accuracy.
- It checks for uneven accuracy across kinds of notice. The tool does not score or decide anything about people, so there is no group of people to test.
- The way to narrow these intervals is more notices from the smaller groups, Wales first.

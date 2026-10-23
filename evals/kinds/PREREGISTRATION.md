# Notice kinds: pre-registration

**Created:** 23/10/2026-15:41 (BST)  *(2026-10-23T14:41Z)*
**Last updated:** 23/10/2026-15:41 (BST)  *(2026-10-23T14:41Z)*

Written and committed with `split.json` before any model was trained on these labels.

## What the model is for

Only notices that have been read have a kind from the language model (341 of 1,764 on 23/10/2026). A small trained
classifier gives every notice its kind at search time, with no model call, so results can be filtered by kind (road
closure, parking or waiting restriction, speed limit, planning application and the other kinds in `extract.KINDS`).

## Data and labels

- 1,764 notices stored by the live service on 23/10/2026 (`notices.jsonl`, kept out of the public copy because notices can name officials).
- Labels from the service's own model, Azure OpenAI gpt-4.1-mini: 338 given while writing a summary, 1,426 from a kind-only question (`labels.jsonl`).
- So the measure is agreement with the language model's labels. A sample of held-out notices will also be checked by hand and reported separately.

## The test, fixed now

- Held-out set: a quarter of each kind (kinds with fewer than four labels are not held out), seed 20261023, in `split.json`. Never used for training or tuning.
- Measures on the held-out set: accuracy with a 95% Wilson interval, macro-averaged F1, per-kind F1, a confusion table.
- Baseline: the most common kind for each notice code, learned on the training set.
- Comparison: exact McNemar test on the paired held-out results, model against baseline.

## Rules decided before training

1. **Deploy** only if held-out accuracy is at least 80% and the model beats the baseline with exact McNemar p < 0.05.
2. **Quality gate in CI:** a test fails the build if the shipped model's accuracy on the held-out set falls below 80%.
3. **Live monitoring:** each time the language model writes a summary with a kind, the service compares it with the
   classifier's kind and counts agreement by day (shown on the About page).
4. **Fallback:** if agreement over the last 50 such comparisons falls below 70%, the service stops showing the
   classifier's kinds until it is retrained, and the About page says so.
5. Retraining uses the labels gathered since, with a new held-out set reported separately from this one.

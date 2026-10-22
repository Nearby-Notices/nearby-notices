# Evaluation

The question this answers: **when the tool shows a resident a plain-English version of a notice, how often is each part right, and can anything the notice does not say get through?**

Run it: `uv run python evals/run.py` (about 15 minutes on a local 24B model; it calls the model live and never uses the app's cache). Results land in `RESULTS.md` and `results/<timestamp>.json`.

## The set

21 notices in `notices/` (30 until 19 October 2026, when nine were removed for privacy), chosen to cover 9 Gazette categories (planning, road traffic orders, highways stopping-up, environmental protection, electricity consents, water, land drainage, clean air, forestry and plant health, flood prevention), three nations, and sizes from 120 to 2,700 words. They are public records reused under the Open Government Licence v3; the first line of each file is the id, category, date and Gazette link.

`gold.jsonl` holds one line per notice with:

- `authority`, `starts`, `ends`: the accepted values, copied from the notice. Several are accepted where the notice is genuinely ambiguous (a notice that gives an inspection period and a separate objection deadline accepts either as the end). `null` in the list means "the notice does not say", and a prediction of nothing is then correct.
- `kind`: the accepted kinds from the fixed list in `extract.py`.
- `objection`: whether the notice contains a sentence saying how or by when to object.
- `places_include`: places affected that any decent reading must find. `places_exclude`: addresses for inspection or correspondence that must not be listed as places affected.
- `claims`: four hand-written sentences, two true and two false, used to test the gate. The false ones are plausible: a wrong date, a wrong number, the wrong council, a different kind of works.

Labelling rules: a value counts as correct if it matches an accepted value after normalisation (case, punctuation, "09th" and "9"), with either side allowed to be a substring of the other, so "The Scottish Ministers" matches "THE SCOTTISH MINISTERS hereby". Kinds must match exactly.

## What is measured, and what is not

- **Fields** (authority, kind, dates, objection sentence, places, heading): accuracy per field across the set.
- **The gate**: true-keep rate and false-catch rate on the hand-written claims. The false-catch rate is the safety number.
- **Adversarial**: three notices in `adversarial.jsonl` that carry instructions to the model, a JSON break-out and advice bait. Nothing in `forbidden` may appear in any shown field.
- **Consistency**: the same notice extracted twice; share of fields that agree.
- **Cost**: model calls and seconds per notice.

Not measured here: whether the summary sentences the model chose to write are the most useful ones (a human judgement; the thumbs on each card collect it), and the Gazette feed's own recall (it is the record; the tool shows what it returns).

## Statistics

`uv run python evals/stats.py` writes `STATISTICS.md` from the saved runs. The labelled set is small, so every rate carries a 95% Wilson interval. When no false sentence gets through, it gives the exact upper bound on the true leak rate: below 6.9% for 0 of 42, and about 299 false sentences would be needed to show it is below 1%. Runs on the same items are compared with an exact McNemar test on the items where they disagree. The quote-rule fix: 4 of 84 disagree, p = 0.125. Local model against Azure OpenAI: the gate agrees on all 84; the fields disagree on 5 of 105, all in the local model's favour, p = 0.062. Neither difference is significant at the 5% level.

## Leak test (pre-registered)

`evals/leak_test.py` asks whether a sentence the notice does not support can get past the gate, at a size the labelled set cannot reach. Each test sentence is a true sentence with exactly one fact changed (a number with its unit, a date, or a place or organisation) to a value that appears nowhere in the notice, so it needs no hand label. The design of each test is filed before it is built or run (`evals/leak/PREREGISTRATION.md`, `evals/leak/confirm/PREREGISTRATION.md`).

- **First test, 330 sentences from 86 notices:** 2 of 329 got through, both number changes in one long traffic order where the model accepted a quote with a different distance (`evals/leak/LEAK_TEST.md`; incident of 22/10/2026). Exact upper bound 1.9%.
- **The fix:** every number in a sentence must also be in its quotes. The main set is unchanged by it (84 of 84).
- **Confirmation on fresh notices, 330 sentences from 141 notices never used before:** 0 got through, so the leak rate is below 0.9% at 95% confidence (`evals/leak/confirm/LEAK_TEST.md`).
- **Limit:** a sentence that joins a number from one row of a table to a place from another row can still pass when that number is quoted elsewhere (1 such case in the first set after the fix).

## Accuracy by subgroup

`uv run python evals/subgroups.py` writes `SUBGROUPS.md`: does the tool work as well on every kind of notice? The tool reads notices, not people, so the groups are the notice's nation (assigned by hand in `subgroups.json`, with the evidence for each), its length and its type. For each group it gives the gate's result with the exact bound, and the share of notices with all five fields right, with a Wilson interval and a Fisher exact test against the rest; the notice is the unit, because one notice's fields are not independent. On the run of 20 October 2026 no group differs from the rest at the 5% level (smallest p = 0.262: notices over 700 words, 6 of 6 against 10 of 15). The groups are small: only two notices are Welsh, so the gate's guarantee for Wales is only that the leak rate is below 52.7%. More Welsh notices are the first thing to add.

## The gate as an Inspect task

`evals/inspect_gate.py` runs the gate in [Inspect](https://inspect.aisi.org.uk/). Inspect sends the live prompt to the model through its own provider. A custom scorer applies the same code check the service applies (`extract.gate_decision`) and scores each decision against its label, with accuracy grouped by label. Inspect needs the `evals` dependency group, which the service image does not install:

```
uv run --group evals inspect eval evals/inspect_gate.py --model azureai/gpt-4.1-mini --log-dir evals/inspect_logs
```

It needs `AZUREAI_API_KEY`, and `AZUREAI_BASE_URL` pointing at the deployment (`https://<resource>.openai.azure.com/openai/deployments/<deployment>`). The run of 20 October 2026 on Azure OpenAI gpt-4.1-mini scored 84 of 84: every true sentence kept and every false one removed, with no sample errors.

## The pipeline (DVC)

The whole evaluation is a [DVC](https://dvc.org) pipeline, defined in `dvc.yaml` at the repository root:

```
uv run --group evals dvc repro            # rerun whatever is out of date
uv run --group evals dvc status           # what would rerun, and why
uv run --group evals dvc metrics diff     # how the headline numbers moved since the last commit
```

Four stages. `evaluate` runs `run.py` on the live model and `inspect` runs the Inspect task; these two call the model. `statistics` (writing `STATISTICS.md` and `metrics.json`) and `subgroups` only read saved runs. DVC hashes every input, so a change to the labels, the notices or the extraction code reruns the model stages, and a change to a report reruns only that report. `dvc.lock` records the hash of every input and output of the last run, which ties each published number to the exact labels, code and model setting behind it. The model setting is in `params.yaml`; the endpoint and key come from the environment (`NN_MODEL_API_BASE`, `NN_MODEL_API_KEY`, and for Inspect `AZUREAI_BASE_URL`, `AZUREAI_API_KEY`), so no secret is versioned. Outputs stay in git (`cache: false`). The held-out set becomes a stage once its labels are checked.

## Changing the set

Add a notice: save its text to `notices/<id>.txt` with the header line, add a gold line, add four claims, and add its nation to `subgroups.json` (the subgroup report refuses to run without it). Keep the two-true-two-false shape so the gate numbers stay comparable. The labels were written by the author with an AI assistant and checked against the notice text by hand; if you find one wrong, fix the label and say so in the commit.

## Labelling rules that bit, and the decision

- **List notices** (a council publishing ten applications): the model lists at most eight places, so no three specific sites are guaranteed. The rule is now: `places_include` holds the first three sites in notice order.
- **Reference points** (a junction named only to locate the works, "from a point 552 metres southeast of Dunglass Road") are not places affected and are not in `places_include`.
- **A place with its own postcode** ("near Kinross, PH2 9DW") is kept without the postcode; an address with a postcode and a street number or an organisation name is dropped as correspondence. The first run dropped both; see `docs/incidents.md`.

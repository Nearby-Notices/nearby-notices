# Evaluation

The question this answers: **when the tool shows a resident a plain-English version of a notice, how often is each part right, and can anything the notice does not say get through?**

Run it: `uv run python evals/run.py` (about 15 minutes on a local 24B model; it calls the model live and never uses the app's cache). Results land in `RESULTS.md` and `results/<timestamp>.json`.

## The set

30 notices in `notices/`, chosen to cover 10 Gazette categories (planning, road traffic orders, highways stopping-up, environmental protection, electricity consents, water, land drainage, clean air, forestry and plant health, flood prevention), three nations, and sizes from 120 to 2,700 words. They are public records reused under the Open Government Licence v3; the first line of each file is the id, category, date and Gazette link.

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

## Changing the set

Add a notice: save its text to `notices/<id>.txt` with the header line, add a gold line, add four claims. Keep the two-true-two-false shape so the gate numbers stay comparable. The labels were written by the author with an AI assistant and checked against the notice text by hand; if you find one wrong, fix the label and say so in the commit.

## Labelling rules that bit, and the decision

- **List notices** (a council publishing ten applications): the model lists at most eight places, so no three specific sites are guaranteed. The rule is now: `places_include` holds the first three sites in notice order.
- **Reference points** (a junction named only to locate the works, "from a point 552 metres southeast of Dunglass Road") are not places affected and are not in `places_include`.
- **A place with its own postcode** ("near Kinross, PH2 9DW") is kept without the postcode; an address with a postcode and a street number or an organisation name is dropped as correspondence. The first run dropped both; see `docs/incidents.md`.

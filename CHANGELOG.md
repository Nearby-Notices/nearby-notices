# Changelog

All dates are the day the change was made, in the UK.

## 18 October 2026

- Live on Azure Container Apps (UK South) at https://nearby-notices.bluesea-79d4ea2e.uksouth.azurecontainerapps.io, reading with an Azure OpenAI gpt-4.1-mini deployment in the same resource group; scale-to-zero, one replica at most, £5 monthly budget with email alerts; image published to GitHub's container registry and pulled from there; `deploy/azure.sh` and the `deploy` workflow.
- Public-endpoint settings: a lower daily model-call cap and a per-client searches-per-minute limit that keeps no addresses.
- Startup warm-up re-reads cached searches; a card being read shows a preview of the notice; the store uses WAL and never holds a transaction across a network or model call; summaries no longer restate the authority or dates.

## 17 October 2026, after the first evaluation run

- Heading: if the model's one-line heading fails the gate, the first gated summary sentence is used, not the Gazette's generic title (the first run fell back to the title in 37% of notices).
- Gate: a quote that joins two spans with "..." is checked span by span (three of the first run's four misses).
- Places: a place carrying its own postcode ("near Kinross, PH2 9DW") is kept without the postcode; only addresses are dropped.
- Gold labels for list notices follow a stated rule (first three sites in notice order); reference points are not places affected. Baseline results kept in `evals/results/`.

## 17 October 2026

- Evaluation: 30 hand-labelled notices across 10 categories, 120 true/false sentences for the gate, 3 adversarial notices; `evals/run.py` writes `evals/RESULTS.md`.
- Extraction hardened: the heading is gated like every other sentence; authority and dates must be verbatim; kind must be from the fixed list; the gate asks for up to three short quotes and checks each; sentences are not split after abbreviations such as "St."; the Gazette's catalogue line is stripped before the model reads the notice.
- Two new deterministic layers: a scrubber for sentences addressed to a model, and an advice filter for generated sentences that instruct the reader. `docs/safety.md` sets out the threat model.
- The model's name is read from the server at startup, so the name recorded with each plain-English version is the model actually used.
- MCP server over the same index: `find_notices_near`, `read_notice`, `coverage`.
- Map: icons per kind, compact popups, overlapping pins spread in a ring; distances measured to the nearest postcode a notice is filed under; miles or kilometres; the Gazette's honoured radii respected; no page reloads while notices are being read.
- CI (ruff and pytest), Dockerfile, Makefile, `.env.example`.

## 16 October 2026

- First version: Gazette feed client with category exclusions, place lookup, extraction and sentence gate through LiteLLM, SQLite cache, web pages, tests; background reader; grouping and filters; public-sector styling without official marks; map view.

# Changelog

All dates are the day the change was made, in the UK.

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

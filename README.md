# Nearby Notices

**What is changing near you, in plain English.** Road closures, parking changes, planning and environmental notices are published in [The Gazette](https://www.thegazette.co.uk) in legal language that is hard to read and hard to search by place. Type a postcode or a town, get the notices within a few miles, each read back in plain English and linked to the notice as published.

Built with an AI coding assistant under the author's direction, in the author's own time, on open data. Not affiliated with The Gazette, the Government or any council. It shows public notices and does not give advice.

## How it works

1. **Find:** The Gazette's own feed, filtered by postcode and distance (`location-postcode-1`, `location-distance-1`) and by category, newest first. Place lookup through [postcodes.io](https://postcodes.io) (ONS and Ordnance Survey open data).
2. **Read:** a language model (any model through LiteLLM; by default a local one) returns the facts of each notice as JSON: what is changing, the places, dates, the authority, the kind of notice, and the notice's own sentence on how to object.
3. **Check:** every place name must appear word for word in the notice or it is dropped. Every plain-English sentence is judged by a second step that must return a supporting quote that really is in the text; sentences that fail are removed and counted. The model never writes advice.
4. **Show:** the plain-English version, the facts, the notice verbatim, and the link.

## What it refuses, by design

Only categories published by public bodies and companies acting as authorities are fetched: Transport, Town and Country Planning, Environmental Protection, Water Resources, Forestry and Plant Health, Electricity. Notices about people (corporate and personal insolvency, deceased estates, appointments, marriages, partnerships, mixed "other" notices) are refused at the fetcher, refused at the store, and never shown; `tests/test_rules.py` proves it. The Gazette's data licence (Open Government Licence v3) does not cover personal data, and this tool is not for finding out about people.

## Privacy

No accounts, no cookies, no tracking. What you type is used for the search and not stored, logged or traced. Server logs keep no IP addresses. Counters are daily totals with no identifiers. See `/privacy`.

## Run it

```
uv sync
uv run uvicorn nearby_notices.app:app --port 8765
```

Settings (environment variables): `NN_MODEL` (LiteLLM model name, default a local OpenAI-compatible server), `NN_MODEL_API_BASE`, `NN_MODEL_API_KEY`, `NN_DAILY_CALL_CAP`, `NN_DB_PATH`, `NN_USER_AGENT`.

Tests: `uv run pytest`.

## Evaluation

See `evals/` (in progress): extraction accuracy per field on hand-labelled notices, sentences kept and removed by the check, refusals on notices without usable text, consistency across repeated runs, latency and cost, and extraction quality by region and authority type.

## Limitations

To be written by the author in his own words after the first week of use.

## Licence

Code: MIT. Notice data: The Gazette, Open Government Licence v3. Place data: postcodes.io, Open Government Licence.

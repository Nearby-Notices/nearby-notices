# Nearby Notices

**What is changing near you, in plain English.** Road closures, parking changes, planning and environmental notices are published in [The Gazette](https://www.thegazette.co.uk) in legal language that is hard to read and hard to search by place. Type a postcode or a town, get the notices within a few miles, each read back in plain English and linked to the notice as published.

Built with an AI coding assistant under the author's direction, in the author's own time, on open data. Not affiliated with The Gazette, the Government or any council. It shows public notices and does not give advice.

## How it works

1. **Find:** The Gazette's own feed, filtered by postcode and distance (`location-postcode-1`, `location-distance-1`) and by category, newest first. Place lookup through [postcodes.io](https://postcodes.io) (ONS and Ordnance Survey open data). The Gazette only honours radii of 1, 5, 10, 15, 20, 25 and 30 miles (anything else is rounded down by the Gazette, so "3 miles" would silently be 1), so the tool asks for the smallest honoured radius that covers the distance you chose, in miles or kilometres, then measures each notice itself. A notice is usually filed under several postcodes (the street affected, the council, a consultant's office) and the feed only gives the first, so when that one falls outside your circle the tool reads the notice's linked-data record for all of them and keeps the notice only if its nearest filed postcode is inside.
2. **Read:** a language model (any model through LiteLLM; by default a local one) returns the facts of each notice as JSON: what is changing, the places, dates, the authority, the kind of notice, and the notice's own sentence on how to object.
3. **Check:** every place name must appear word for word in the notice or it is dropped. Every plain-English sentence is judged by a second step that must return a supporting quote that really is in the text; sentences that fail are removed and counted. The model never writes advice.
4. **Show:** the plain-English version, the facts, the notice verbatim, and the link, as a list, grouped by kind, or on a map (Leaflet, served from this site; OpenStreetMap tiles are only requested when you open the map). Each pin sits at the nearest postcode the notice is filed under. Notices are read in the background; the page asks `/status` every few seconds and swaps in each card as it is ready, without reloading.

## Use it from an AI agent (MCP)

The same index is an [MCP](https://modelcontextprotocol.io) server over stdio, so an agent can ask "what public notices are there near Dudley?" and read one in plain English, with the verbatim text and the Gazette link to cite. Three tools:

| Tool | What it does |
|---|---|
| `find_notices_near(place, distance=3, unit="mi")` | Up to 12 notices near a postcode or town, newest first: id, kind, date, one-line title, distance to the nearest postcode it is filed under, whether plain English is ready, link. |
| `read_notice(notice_id)` | The notice as published, word for word, plus the checked plain-English version: what, places, authority, dates, kind, the notice's own sentence on how to object (quoted), summary, and how many generated sentences the check removed. Made on the spot if not ready. |
| `coverage()` | What is covered and refused, licence, privacy, distance choices. |

Claude Code:

```
claude mcp add nearby-notices -- uv run --directory /path/to/nearby-notices python -m nearby_notices.mcp_server
```

Claude Desktop or any other MCP client: command `uv`, arguments `run --directory /path/to/nearby-notices python -m nearby_notices.mcp_server`. The server's instructions tell the agent that the plain English is generated and checked but not official, that it must cite the notice, and that it gives no legal advice. The same category rules apply: it never returns notices about people.

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

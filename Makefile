.PHONY: run mcp test lint eval docker

run:            ## the website on http://127.0.0.1:8765
	uv run uvicorn nearby_notices.app:app --host 127.0.0.1 --port 8765

mcp:            ## the MCP server over stdio (for an MCP client to launch)
	uv run python -m nearby_notices.mcp_server

test:           ## unit tests, no network, no model
	uv run ruff check nearby_notices tests evals && uv run pytest -q

eval:           ## the live evaluation against the configured model; writes evals/RESULTS.md
	uv run python evals/run.py

docker:         ## build the website image
	docker build -t nearby-notices .

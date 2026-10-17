# Nearby Notices: the website. Point NN_MODEL_API_BASE at any OpenAI-compatible endpoint (a local llama-server,
# Ollama, or a cloud provider through LiteLLM's naming). The SQLite cache lives in /data; mount a volume to keep it.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy NN_DB_PATH=/data/notices.sqlite

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY nearby_notices ./nearby_notices
COPY templates ./templates
COPY static ./static
RUN uv sync --frozen --no-dev && mkdir -p /data

EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s CMD ["uv", "run", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health')"]
CMD ["uv", "run", "uvicorn", "nearby_notices.app:app", "--host", "0.0.0.0", "--port", "8765"]

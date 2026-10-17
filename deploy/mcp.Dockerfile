# MCP server (build123d/OpenCascade) over streamable HTTP. Build context: repo root.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /usr/local/bin/uv
# OpenCascade's wheels link against libGL and glib even without a display.
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app/mcp-server
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY mcp-server/pyproject.toml mcp-server/uv.lock mcp-server/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY mcp-server/ ./
COPY parts/ /app/parts/
RUN uv sync --frozen --no-dev
ENV MCP_TRANSPORT=http MCP_PORT=8000 PHYSICAL_STUDIO_OUT=/data/out
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "physical-studio-mcp"]

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# COPY dependency files
COPY server/pyproject.toml server/uv.lock ./server/
COPY agent/pyproject.toml agent/uv.lock ./agent/

# RUN uv sync --frozen for both server and agent to install dependencies
RUN cd /app/server && uv sync --frozen
RUN cd /app/agent && uv sync --frozen

# COPY the rest of the source code
COPY server ./server
COPY agent ./agent

# Temporary RUN command for testing using port 10000
CMD ["uv", "run", "--directory", "/app/server", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "10000"]
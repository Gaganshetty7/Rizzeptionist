FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# COPY dependency files
COPY db/pyproject.toml db/uv.lock /app/db/
COPY appointments/pyproject.toml appointments/uv.lock /app/appointments/
COPY server/pyproject.toml server/uv.lock ./server/
COPY agent/pyproject.toml agent/uv.lock ./agent/

# RUN uv sync --frozen for both server and agent to install dependencies
RUN cd /app/db && uv sync --frozen --no-install-local
RUN cd /app/appointments && uv sync --frozen --no-install-local
RUN cd /app/server && uv sync --frozen --no-install-local
RUN cd /app/agent && uv sync --frozen --no-install-local

# COPY the rest of the source code
COPY db ./db
COPY appointments ./appointments
COPY server ./server
COPY agent ./agent

# Install the local editable dependencies since earlier dependency install cmd's were non local
RUN cd /app/server && uv sync --frozen
RUN cd /app/agent && uv sync --frozen

# Temporary RUN command for testing using port 10000
CMD ["sh", "-c", "uv run --directory /app/server uvicorn src.main:app --host 0.0.0.0 --port ${PORT}"]

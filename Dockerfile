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

# NLTK's default runtime download from GitHub hangs infinitely due to ISP packet drops, causing silent timeouts; baking it in via CDN resolves this.
# We download from a CDN mirror and extract it directly into /root/nltk_data/tokenizers, exactly where NLTK expects to find it. 
RUN mkdir -p /root/nltk_data/tokenizers && \
    python -c "import urllib.request, zipfile, io; zipfile.ZipFile(io.BytesIO(urllib.request.urlopen('https://cdn.jsdelivr.net/gh/nltk/nltk_data@gh-pages/packages/tokenizers/punkt_tab.zip').read())).extractall('/root/nltk_data/tokenizers')"

# Temporary RUN command for testing using port 10000
CMD ["sh", "-c", "uv run --directory /app/server uvicorn src.main:app --host 0.0.0.0 --port ${PORT}"]

# Voice Agent

A voice-agent application consisting of a Pipecat voice agent, a Python backend for appointment logic and database access, and a lightweight HTML/JavaScript frontend.

## Project Structure

- `agent/` — Pipecat voice agent
- `server/` — Backend API, appointment logic and database access
- `web/` — HTML/CSS/JavaScript frontend

## Local Setup

> **Prerequisites:** Install [uv](https://docs.astral.sh/uv/getting-started/installation/) before proceeding.

### Agent

```bash
cd agent
cp .env.example .env   # fill in your API keys
uv sync
uv run python src/main.py
```

### Server

```bash
cd server
cp .env.example .env   # fill in your config values
uv sync
uv run python src/main.py
```

### Web

The frontend is plain HTML/JS — no build step required. Open `web/index.html` directly in your browser, or serve it with any static file server:

```bash
# e.g. using Python's built-in server
cd web
python -m http.server 8080
```

## Running

Start each service in a separate shell:

```bash
# Server
cd server && uv sync && uv run uvicorn src.main:app --reload

# Agent
cd agent && uv sync && uv run python -m src.main clinic-reception

# Frontend
python3 -m http.server 5500 --bind 127.0.0.1 -d web
```

Then open http://127.0.0.1:5500

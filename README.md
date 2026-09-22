# Voice Agent

A voice-agent application consisting of a Pipecat voice agent, a Python backend for appointment logic and database access, and a lightweight HTML/JavaScript frontend.

## Project Structure

- `agent/` — Pipecat voice agent
- `server/` — Backend API, appointment logic and database access
- `web/` — HTML/CSS/JavaScript frontend

## How to Run

> **Prerequisites:** [Python 3.12+](https://www.python.org/) and [uv](https://docs.astral.sh/uv/getting-started/installation/).
> Copy `.env.example` to `.env` and fill in your API keys before starting.

### Terminal

```bash
# Server
cd server && uv sync && uv run uvicorn src.main:app --reload

# Frontend (separate terminal)
python3 -m http.server 5500 --bind 127.0.0.1 -d web
```

Then open http://127.0.0.1:5500. The voice agent is spawned automatically when you start a session.

### Docker

```bash
docker build -t rizzeptionist .
docker run --rm -p 10000:10000 --env-file .env rizzeptionist
```

Serve the `web/` frontend separately with the `python3 -m http.server` command above.

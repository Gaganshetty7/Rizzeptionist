# Voice Agent

A voice-agent application consisting of a Pipecat voice bot, a Python backend for appointment logic and database access, and a lightweight HTML/JavaScript frontend.

## Project Structure

- `bot/` — Pipecat voice agent
- `server/` — Backend API, appointment logic and database access
- `web/` — HTML/CSS/JavaScript frontend

## Local Setup

### Bot

```bash
cd bot
uv sync
uv run python bot/main.py

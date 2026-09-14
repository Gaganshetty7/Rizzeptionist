import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv
from sqlalchemy import make_url

ROOT_DIR = Path(__file__).resolve().parents[3]
load_dotenv(ROOT_DIR / ".env")

def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")

    return value

url = make_url(
    get_required_env("DATABASE_URL").replace(
        "postgresql://",
        "postgresql+asyncpg://",
        1,
    )
)

query = dict(url.query)
query.pop("sslmode", None)
query.pop("channel_binding", None)

DATABASE_URL = url.set(query=query)

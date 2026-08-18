import os
from dotenv import load_dotenv

load_dotenv()

# Module that loads and validates env vars, and fails fast with a clear error if something's missing
def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return os.getenv(value)

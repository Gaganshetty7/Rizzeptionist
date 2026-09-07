import os
from dotenv import load_dotenv

load_dotenv()

# Module that loads and validates env vars, and fails fast with a clear error if something's missing
def get_required_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value

DEEPGRAM_API_KEY = get_required_env("DEEPGRAM_API_KEY")
GEMINI_API_KEY = get_required_env("GEMINI_API_KEY")

LIVEKIT_API_KEY = get_required_env("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = get_required_env("LIVEKIT_API_SECRET")
LIVEKIT_URL = get_required_env("LIVEKIT_URL")

DATABASE_URL = get_required_env("DATABASE_URL")

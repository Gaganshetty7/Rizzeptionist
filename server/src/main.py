import asyncio
import uuid

from .config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL

from pathlib import Path
from fastapi import FastAPI
from livekit import api
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://0.0.0.0:5500", "http://127.0.0.1:5500"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Resolving Agent Directory Path for the sub process
BASE_DIR = Path(__file__).resolve().parent.parent.parent
AGENT_DIR = BASE_DIR / "agent"

session_id = str(uuid.uuid4())[:8]

@app.post("/api/session/start")
async def start_session():
    room_name = session_id

    try:
        # Create Token
        token = api.AccessToken(
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
        ).with_identity("rizzeptionist-user") \
        .with_name("User") \
        .with_grants(api.VideoGrants(
            room_join=True,
            room=room_name,
        )).to_jwt()

        # Create Sub Process for Agent soon after User token is created
        proc = await asyncio.create_subprocess_exec(
            "uv",
            "run",
            "python",
            "-m",
            "src.main",
            room_name,
            cwd = str(AGENT_DIR)
        ) 

        print("Bot process started:", proc.pid)

        return {
            "url": LIVEKIT_URL,
            "token": token,
            "room_name": room_name
        }
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to generate LiveKit access token",
        )

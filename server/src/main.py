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

# Track active sessions
active_sessions = {}

# Resolving Agent Directory Path for the sub process
BASE_DIR = Path(__file__).resolve().parent.parent.parent
AGENT_DIR = BASE_DIR / "agent"


# Agent Health Monitor
async def monitor_agent(process, room_name):
    return_code = await process.wait()

    if return_code != 0:
        session = active_sessions.get(room_name)
        if session:
            session["status"] = "failed"

        print(
            f"Bot for room {room_name} crashed "
            f"with exit code {return_code}"
        )

# Agent Timeout Monitor
async def wait_for_agent_ready(room_name):
    await asyncio.sleep(10)

    session = active_sessions.get(room_name)

    if not session:
        return

    if session["status"] == "starting":
        print(f"Agent failed to become ready: {room_name}")

        session["status"] = "failed"

        process = session["process"]

        # process.returncode can be:
        # None → process is still running
        # 0 → process exited normally
        # non-zero → process exited with an error

        # If the process exists AND is still running, terminate it.
        if process and process.returncode is None:
            process.terminate()

# Agent Ready Check Endpoint
@app.post("/api/session/ready")
async def agent_ready(room_name: str):
    session = active_sessions.get(room_name)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found"
        )
    
    session["status"] = "ready"

    print(f"Agent is ready for room: {room_name}")

    return {
        "status": "ready",
        "room_name": room_name,
    }


# Session Start Endpoint
@app.post("/api/session/start")
async def start_session():
    session_id = str(uuid.uuid4())[:8]
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

        active_sessions[room_name] = {
            "process": None,
            "status": "starting",
        }

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

        # Update Active Sessions Dictionary
        active_sessions[room_name]["process"] = proc

        asyncio.create_task(
            wait_for_agent_ready(room_name)
        )

        asyncio.create_task(
            monitor_agent(proc, room_name)
        )

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

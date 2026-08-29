import json
import asyncio
import uuid

from .config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL

from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from livekit import api

# Set up the lifespan of the FastAPI application to initialize and close the LiveKit API client
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.lk_api = api.LiveKitAPI(
        url=LIVEKIT_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    )

    yield

    await app.state.lk_api.aclose()

app = FastAPI(lifespan=lifespan)

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



# Send a failure notification to a specific user via LiveKit Data API
async def notify_failure(room_name: str, user_identity: str, reason: str):
    from livekit.protocol.room import SendDataRequest
    from livekit.protocol.models import DataPacket

    # Get the LiveKit API client from the application state
    lk_api = app.state.lk_api

    payload = json.dumps({
        "type": "session_error",
        "reason": reason,
    }).encode("utf-8")

    try:
        await lk_api.room.send_data(
            SendDataRequest(
                room = room_name,
                data = payload,
                kind = DataPacket.Kind.RELIABLE,
                destination_identities = [user_identity],
                topic = "session_error",
            )
        )
        print(f"Notified user {user_identity} of failure: {reason}")
    except Exception as e:
        print(f"Failed to notify user {user_identity}: {e}")



# Agent Health Monitor
async def monitor_agent(process, room_name):
    return_code = await process.wait()

    session = active_sessions.get(room_name)

    if not session:
        return

    if session["intentional_stop"]:
        print(f"Bot for room {room_name} stopped intentionally")
        return

    if return_code != 0:
        session["status"] = "failed"

        await notify_failure(
            room_name=room_name,
            user_identity=session["user_identity"],
            reason="bot_crashed",
        )

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

        await notify_failure(
            room_name=room_name,
            user_identity=session["user_identity"],
            reason="bot_startup_timeout",
        )

        process = session["process"]

        # process.returncode can be:
        # None → process is still running
        # 0 → process exited normally
        # non-zero → process exited with an error

        # If the process exists AND is still running, terminate it.
        if process and process.returncode is None:
            # We have to mark this as intentional stop else the monitor_agent will mark it as crashed.
            # TODO: Use a separate termination reason instead of intentional_stop.
            session["intentional_stop"] = True
            process.terminate()



#API Endpoints

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
    user_identity = f"user-{session_id}"

    try:
        # Create Token
        token = api.AccessToken(
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
        ).with_identity(user_identity) \
        .with_name("User") \
        .with_grants(api.VideoGrants(
            room_join=True,
            room=room_name,
        )).to_jwt()

        active_sessions[room_name] = {
            "process": None,
            "status": "starting",
            "intentional_stop": False,
            # LiveKit's send_data() needs a destination identity, The room name alone isn't enough.
            "user_identity": user_identity,
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

# Session End Endpoint
@app.post("/api/session/end/{room_name}")
async def end_session(room_name: str):
    session = active_sessions.get(room_name)

    if not session:
        raise HTTPException(
            status_code = 404,
            detail = "Session not found"
        )
    
    process = session["process"]

    if process and process.returncode is None:
        session["intentional_stop"] = True
        process.terminate()
        await process.wait()

    active_sessions.pop(room_name, None)

    print(f"Session ended: {room_name}")

    return {
        "status": "ended",
        "room_name": room_name,
    }

# Session Status Endpoint
@app.get("/api/session/status/{room_name}")
async def session_status(room_name: str):
    session = active_sessions.get(room_name)

    if not session:
        raise HTTPException(
            status_code=404,
            detail="Session not found"
        )

    return {
        "status": session["status"]
    }

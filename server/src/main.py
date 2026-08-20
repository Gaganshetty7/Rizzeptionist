from .config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL

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

@app.post("/api/session/start")
async def start_session():
    room_name = "clinic-reception"

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

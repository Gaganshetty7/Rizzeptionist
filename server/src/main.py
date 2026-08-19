import time
import httpx
from fastapi import FastAPI, HTTPException

from .config import DAILY_API_KEY

app = FastAPI()

DAILY_API_URL = "https://api.daily.co/v1"

@app.post("/api/session/start")
async def start_session():
    expires_at = int(time.time()) + 900

    headers = {
        "Authorization":f"Bearer {DAILY_API_KEY}",
        "Content-Type":"application/json"
    }

    async with httpx.AsyncClient() as client:
        try:
            # Create Daily Room
            room_response = await client.post(
                f"{DAILY_API_URL}/rooms",
                headers = headers,
                json={
                    "properties": {
                        "exp": expires_at,
                    }
                },
                timeout = 10,
            )
            room_response.raise_for_status()
            room = room_response.json()

            # Create Token
            token_response = await client.post(
                f"{DAILY_API_URL}/meeting-tokens",
                headers=headers,
                json={
                    "properties": {
                        "room_name": room["name"],
                        "exp": expires_at,
                    }
                },
                timeout=10,
            )
            token_response.raise_for_status()
            token = token_response.json()["token"]

            # Return Room URL and Token to frontend
            return{
                "room_url": room["url"],
                "token": token
            }
        except httpx.HTTPError:
            raise HTTPException(
                status_code=502,
                detail = "Daily API request failed",
            )

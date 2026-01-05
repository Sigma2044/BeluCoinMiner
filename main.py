from fastapi import FastAPI
import requests
import os
from datetime import datetime, timedelta
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Environment variables
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

# -----------------------------
# Discord OAuth Callback
# -----------------------------
@app.get("/auth/discord/callback")
def discord_callback(code: str):
    # Exchange code for access token
    token = requests.post(
        "https://discord.com/api/oauth2/token",
        data={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    ).json()

    # Error handling
    if "access_token" not in token:
        print("Discord token error:", token)
        return {"error": "OAuth failed", "details": token}

    # Fetch user info
    user = requests.get(
        "https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {token['access_token']}"}
    ).json()

    # Return Discord ID + wallet (example wallet generator)
    return {
        "discord_id": user["id"],
        "wallet": f"WALLET_{user['id'][-6:]}"
    }

# -----------------------------
# Mining Session System
# -----------------------------
active_sessions = {}
SESSION_DURATION = timedelta(minutes=10)

@app.post("/api/share")
def receive_share(data: dict):
    discord_id = data.get("discord_id", "unknown")
    wallet = data["wallet"]
    share = data["share"]

    now = datetime.utcnow()

    # Start new session if none exists
    if discord_id not in active_sessions:
        active_sessions[discord_id] = now

    # Check if session expired
    if now - active_sessions[discord_id] > SESSION_DURATION:
        return {"error": "session_expired"}

    # Accept share
    print("Share:", discord_id, wallet, share)
    return {"status": "ok"}

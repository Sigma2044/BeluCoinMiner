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

    if "access_token" not in token:
        print("Discord token error:", token)
        return {"error": "OAuth failed", "details": token}

    user = requests.get(
        "https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {token['access_token']}"}
    ).json()

    return {
        "discord_id": user["id"],
        "wallet": f"WALLET_{user['id'][-6:]}"
    }

# -----------------------------
# Mining System
# -----------------------------
active_sessions = {}          # discord_id -> last share time
last_session_end = {}         # discord_id -> last session end
SESSION_TIMEOUT = timedelta(seconds=15)
COOLDOWN = timedelta(minutes=5)

active_miners = {}            # discord_id -> last share time
MINER_TIMEOUT = timedelta(seconds=15)

current_difficulty = 5
reward_balances = {}          # discord_id -> total reward
REWARD_FACTOR = 0.001         # reward per share * difficulty

def update_difficulty():
    global current_difficulty
    now = datetime.utcnow()
    active_count = sum(
        1 for t in active_miners.values()
        if now - t < MINER_TIMEOUT
    )
    current_difficulty = max(1, active_count * 5)

@app.get("/api/miners")
def get_active_miners():
    now = datetime.utcnow()
    count = sum(
        1 for t in active_miners.values()
        if now - t < MINER_TIMEOUT
    )
    return {"active_miners": count}

# -----------------------------
# Receive Share
# -----------------------------
@app.post("/api/share")
def receive_share(data: dict):
    discord_id = data.get("discord_id", "unknown")
    wallet = data["wallet"]
    share = data["share"]

    now = datetime.utcnow()

    # Cooldown check
    if discord_id in last_session_end:
        if now - last_session_end[discord_id] < COOLDOWN:
            return {"error": "cooldown_active"}

    # Track miner activity
    active_miners[discord_id] = now

    # Start new session if needed
    if discord_id not in active_sessions:
        active_sessions[discord_id] = now

    # Session timeout (no share for 15 seconds)
    if now - active_sessions[discord_id] > SESSION_TIMEOUT:
        last_session_end[discord_id] = now
        active_sessions.pop(discord_id, None)
        return {"error": "session_expired"}

    # Update session timestamp
    active_sessions[discord_id] = now

    # Update difficulty
    update_difficulty()

    # Reward calculation
    reward = share * current_difficulty * REWARD_FACTOR
    reward_balances[discord_id] = reward_balances.get(discord_id, 0) + reward

    print("Share:", discord_id, wallet, share, "Difficulty:", current_difficulty)

    return {
        "status": "ok",
        "difficulty": current_difficulty,
        "reward": reward_balances[discord_id]
    }

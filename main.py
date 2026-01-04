from fastapi import FastAPI
import requests
import os

app = FastAPI()

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")


@app.get("/auth/discord/callback")
def discord_callback(code: str):
    # 1. Discord Token holen
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

    # 2. Fehler abfangen
    if "access_token" not in token:
        print("Discord token error:", token)
        return {"error": "OAuth failed", "details": token}

    # 3. User-Daten holen
    user = requests.get(
        "https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {token['access_token']}"}
    ).json()

    return {"discord_id": user["id"]}


@app.post("/api/share")
def receive_share(data: dict):
    wallet = data["wallet"]
    share = data["share"]
    discord_id = data.get("discord_id", "unknown")

    print("Share:", discord_id, wallet)

    return {"status": "ok"}

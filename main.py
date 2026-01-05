from fastapi import FastAPI
import requests
import os
from datetime import datetime, timedelta
from fastapi.middleware.cors import CORSMiddleware
from web3 import Web3
import json

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OAuth env
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")

# Web3 / Sepolia
SEPOLIA_RPC = os.getenv("SEPOLIA_RPC")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS")
TREASURY_ADDRESS = os.getenv("TREASURY_ADDRESS")
TREASURY_PRIVATE_KEY = os.getenv("TREASURY_PRIVATE_KEY")

w3 = Web3(Web3.HTTPProvider(SEPOLIA_RPC))

# === ABI HIER EINSETZEN (dein JSON aus Remix) ===
ABI = [
    # dein komplettes ABI-Array aus der Datei
]

contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=ABI)

# -----------------------------
# Discord OAuth
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
# Mining System (off-chain)
# -----------------------------
active_sessions = {}
last_session_end = {}
SESSION_TIMEOUT = timedelta(seconds=15)
COOLDOWN = timedelta(minutes=5)

active_miners = {}
MINER_TIMEOUT = timedelta(seconds=15)

current_difficulty = 5
reward_balances = {}   # unclaimed reward (off-chain)
wallet_balances = {}   # claimed (off-chain, optional)
REWARD_FACTOR = 0.001

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

@app.get("/api/balance")
def get_balance(discord_id: str):
    balance = wallet_balances.get(discord_id, 0)
    return {"balance": balance}

# -----------------------------
# Off-chain Claim (nur intern)
# -----------------------------
@app.post("/api/claim")
def claim_reward(data: dict):
    discord_id = data["discord_id"]
    reward = reward_balances.get(discord_id, 0)
    wallet_balances[discord_id] = wallet_balances.get(discord_id, 0) + reward
    reward_balances[discord_id] = 0
    return {
        "status": "claimed",
        "new_balance": wallet_balances[discord_id]
    }

# -----------------------------
# On-chain Claim (Sepolia ERC20)
# -----------------------------
@app.post("/api/claim_onchain")
def claim_onchain(data: dict):
    discord_id = data["discord_id"]
    user_wallet = data["wallet"]  # echte EVM-Adresse des Users

    # Reward in Token-Einheiten (hier: direkt als wei-ähnliche Einheit angenommen)
    reward = reward_balances.get(discord_id, 0)
    if reward <= 0:
        return {"error": "no_reward"}

    # Optional: decimals berücksichtigen, z.B.:
    # decimals = contract.functions.decimals().call()
    # amount = int(reward * (10 ** decimals))
    amount = int(reward * 10**18)  # wenn dein Token 18 Decimals hat

    nonce = w3.eth.get_transaction_count(Web3.to_checksum_address(TREASURY_ADDRESS))

    tx = contract.functions.transfer(
        Web3.to_checksum_address(user_wallet),
        amount
    ).build_transaction({
        "from": Web3.to_checksum_address(TREASURY_ADDRESS),
        "nonce": nonce,
        "gas": 200000,
        "gasPrice": w3.to_wei("5", "gwei")
    })

    signed_tx = w3.eth.account.sign_transaction(tx, private_key=TREASURY_PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)

    # Off-chain Reward resetten
    reward_balances[discord_id] = 0

    return {
        "status": "onchain_claim_sent",
        "tx_hash": tx_hash.hex()
    }

# -----------------------------
# Receive Share
# -----------------------------
@app.post("/api/share")
def receive_share(data: dict):
    discord_id = data.get("discord_id", "unknown")
    wallet = data["wallet"]
    share = data["share"]
    miner_id = data.get("miner_id", discord_id)

    now = datetime.utcnow()

    # Cooldown
    if discord_id in last_session_end:
        if now - last_session_end[discord_id] < COOLDOWN:
            return {"error": "cooldown_active"}

    # Track miner device
    active_miners[miner_id] = now

    # Start session
    if discord_id not in active_sessions:
        active_sessions[discord_id] = now

    # Session timeout
    if now - active_sessions[discord_id] > SESSION_TIMEOUT:
        last_session_end[discord_id] = now
        active_sessions.pop(discord_id, None)
        return {"error": "session_expired"}

    active_sessions[discord_id] = now

    # Difficulty
    update_difficulty()

    # Reward
    reward = share * current_difficulty * REWARD_FACTOR
    reward_balances[discord_id] = reward_balances.get(discord_id, 0) + reward

    print("Share:", discord_id, wallet, share, "Difficulty:", current_difficulty)

    return {
        "status": "ok",
        "difficulty": current_difficulty,
        "reward": reward_balances[discord_id]
    }

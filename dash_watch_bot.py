import telebot
import requests
import json
import os
import time
import threading
from datetime import datetime, timezone

# ===== Telegram Bot =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Դուք պետք է ավելացնեք BOT_TOKEN որպես Environment Variable")
bot = telebot.TeleBot(BOT_TOKEN)

# ===== Վերացնում ենք հնարավոր webhook =====
try:
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
    print("Webhook հանված է, long polling թույլատրելի է")
except Exception as e:
    print("Webhook հանելու սխալ:", e)

# ===== helpers =====
USERS_FILE = "users.json"
SENT_TX_FILE = "sent_txs.json"

def load_users():
    return json.load(open(USERS_FILE, "r", encoding="utf-8")) if os.path.exists(USERS_FILE) else {}

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def load_sent_txs():
    return json.load(open(SENT_TX_FILE, "r", encoding="utf-8")) if os.path.exists(SENT_TX_FILE) else {}

def save_sent_txs(sent):
    with open(SENT_TX_FILE, "w", encoding="utf-8") as f:
        json.dump(sent, f, ensure_ascii=False, indent=2)

def get_dash_price_usd():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd", timeout=10)
        return float(r.json().get("dash", {}).get("usd", 0))
    except:
        return None

def get_latest_txs(address):
    try:
        r = requests.get(f"https://api.blockcypher.com/v1/dash/main/addrs/{address}/full?limit=10", timeout=20)
        return r.json().get("txs", [])
    except:
        return []

def format_alert(address, amo_

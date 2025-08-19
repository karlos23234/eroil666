import telebot
import requests
import json
import os
import time
from datetime import datetime, timezone
import threading
from flask import Flask

# ===== Telegram Bot =====
BOT_TOKEN = os.getenv("8294188586:AAEOQdJZySFXMeWSiFMi6zhpgzezCq1YL14")
if not BOT_TOKEN:
    raise ValueError("Դուք պետք է ավելացնեք BOT_TOKEN որպես Environment Variable")
bot = telebot.TeleBot(BOT_TOKEN)

USERS_FILE = "users.json"
SENT_TX_FILE = "sent_txs.json"

# ===== helpers =====
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

def format_alert(address, amount_dash, amount_usd, txid, timestamp, tx_number):
    link = f"https://blockchair.com/dash/transaction/{txid}"
    usd_text = f" (${amount_usd:.2f})" if amount_usd else ""
    return f"🔔 Նոր փոխանցում #{tx_number}!\n\n📌 Address: {address}\n💰 Amount: {amount_dash:.8f} DASH{usd_text}\n🕒 Time: {timestamp}\n🔗 {link}"

# ===== Telegram Handlers =====
users = load_users()
sent_txs = load_sent_txs()

@bot.message_handler(commands=["start"])
def start(msg):
    bot.reply_to(msg, "Բարև 👋\nԳրի՛ր քո Dash հասցեն (սկսվում է X-ով):")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("X"))
def save_address(msg):
    user_id = str(msg.chat.id)
    address = msg.text.strip()
    users.setdefault(user_id, [])
    if address not in users[user_id]:
        users[user_id].append(address)
    save_users(users)
    sent_txs.setdefault(user_id, {})
    sent_txs[user_id].setdefault(address, [])
    save_sent_txs(sent_txs)
    bot.reply_to(msg, f"✅ Հասցեն {address} պահպանվեց!")

# ===== Monitor loop =====
def monitor():
    while True:
        price = get_dash_price_usd()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        for user_id, addresses in users.items():
            for address in addresses:
                txs = get_latest_txs(address)
                known = sent_txs.get(user_id, {}).get(address, [])
                known = [json.loads(t) if isinstance(t, str) else t for t in known]
                last_number = max([t["num"] for t in known], default=0)

                for tx in reversed(txs):
                    txid = tx.get("hash")
                    if txid in [t["txid"] for t in known]:
                        continue
                    amount_dash = sum(out.get("value",0)/1e8 for out in tx.get("outputs", []) if address in (out.get("addresses") or []))
                    if amount_dash <=0:
                        continue
                    amount_usd = amount_dash*price if price else None
                    last_number +=1
                    text = format_alert(address, amount_dash, amount_usd, txid, timestamp, last_number)
                    try:
                        bot.send_message(user_id, text)
                    except Exception as e:
                        print("Send error:", e)
                    known.append({"txid": txid,"num": last_number})
                sent_txs.setdefault(user_id, {})[address]=known
                save_sent_txs(sent_txs)
        time.sleep(30)

# ===== Flask server =====
app = Flask(__name__)
@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=3000)

# ===== Start threads =====
threading.Thread(target=monitor, daemon=True).start()
threading.Thread(target=run_flask, daemon=True).start()
bot.infinity_polling()

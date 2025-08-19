import os
import requests
import time
import sqlite3
from datetime import datetime
import threading
from flask import Flask, request
import telebot

# ===== Environment variables =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("Դուք պետք է ավելացնեք BOT_TOKEN և WEBHOOK_URL որպես Environment Variable")

bot = telebot.TeleBot(BOT_TOKEN)

# ===== SQLite setup =====
conn = sqlite3.connect("bot_data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT,
    address TEXT,
    PRIMARY KEY(user_id, address)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS sent_txs (
    user_id TEXT,
    address TEXT,
    txid TEXT PRIMARY KEY,
    num INTEGER
)
""")
conn.commit()

# ===== Helpers =====
def get_dash_price_usd():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd", timeout=10)
        return float(r.json().get("dash", {}).get("usd", 0))
    except Exception as e:
        print("Error getting DASH price:", e)
        return None

def get_latest_txs(address):
    try:
        r = requests.get(f"https://api.blockcypher.com/v1/dash/main/addrs/{address}/full?limit=50", timeout=20)
        txs = r.json().get("txs", [])
        print(f"[{datetime.now()}] Got {len(txs)} TXs for address {address}")
        return txs
    except Exception as e:
        print(f"[{datetime.now()}] Error fetching TXs for {address}: {e}")
        return []

def format_alert(tx, address, tx_number, price):
    txid = tx["hash"]
    total_received = sum([o.get("value",0)/1e8 for o in tx.get("outputs", []) if address in (o.get("addresses") or [])])
    usd_text = f" (${total_received*price:.2f})" if price else ""
    timestamp = tx.get("confirmed")
    timestamp = datetime.fromisoformat(timestamp.replace("Z","+00:00")).strftime("%Y-%m-%d %H:%M:%S") if timestamp else "Unknown"
    return (
        f"🔔 Նոր փոխանցում #{tx_number}!\n\n"
        f"📌 Address: {address}\n"
        f"💰 Amount: {total_received:.8f} DASH{usd_text}\n"
        f"🕒 Time: {timestamp}\n"
        f"🔗 https://blockchair.com/dash/transaction/{txid}"
    )

# ===== Telegram Handlers =====
@bot.message_handler(commands=['start'])
def start(msg):
    bot.reply_to(msg, "Բարև 👋 Գրի՛ր քո Dash հասցեն (սկսվում է X-ով)")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("X"))
def save_address(msg):
    user_id = str(msg.chat.id)
    address = msg.text.strip()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, address) VALUES (?, ?)", (user_id, address))
    conn.commit()
    bot.reply_to(msg, f"✅ Հասցեն {address} պահպանվեց!")
    print(f"[{datetime.now()}] Saved new address {address} for user {user_id}")

# ===== Background Worker =====
def monitor():
    while True:
        price = get_dash_price_usd()
        cursor.execute("SELECT user_id, address FROM users")
        all_users = cursor.fetchall()
        for user_id, address in all_users:
            txs = get_latest_txs(address)
            cursor.execute("SELECT txid, num FROM sent_txs WHERE user_id=? AND address=?", (user_id, address))
            known_txs = {row[0]: row[1] for row in cursor.fetchall()}
            last_number = max(known_txs.values(), default=0)

            for tx in reversed(txs):
                txid = tx["hash"]
                if txid in known_txs:
                    continue
                last_number += 1
                alert = format_alert(tx, address, last_number, price)
                print(f"[{datetime.now()}] Sending TX alert for {address}: {txid}")
                try:
                    bot.send_message(user_id, alert)
                except Exception as e:
                    print(f"[{datetime.now()}] Telegram send error: {e}")
                cursor.execute(
                    "INSERT OR IGNORE INTO sent_txs (user_id, address, txid, num) VALUES (?, ?, ?, ?)",
                    (user_id, address, txid, last_number)
                )
                conn.commit()

        time.sleep(25)  # 25 վայրկյան

# ===== Flask server =====
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

# ===== Main =====
if __name__ == "__main__":
    threading.Thread(target=monitor, daemon=True).start()  # Background TX worker
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    print(f"[{datetime.now()}] Bot started. Webhook set to {WEBHOOK_URL}")
    app.run(host="0.0.0.0", port=5000)



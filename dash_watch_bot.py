import os
import requests
import time
import sqlite3
from datetime import datetime
import threading
from flask import Flask, request
import telebot

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("Դուք պետք է ավելացնեք BOT_TOKEN և WEBHOOK_URL որպես Environment Variable")

bot = telebot.TeleBot(BOT_TOKEN)

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
    txid TEXT PRIMARY KEY,
    user_id TEXT,
    address TEXT,
    num INTEGER
)
""")
conn.commit()

def get_latest_txs(address):
    try:
        r = requests.get(f"https://api.blockcypher.com/v1/dash/main/addrs/{address}/full?limit=20", timeout=15)
        return r.json().get("txs", [])
    except:
        return []

def format_alert(tx, address):
    txid = tx["hash"]
    total_received = sum([o.get("value",0)/1e8 for o in tx.get("outputs", []) if address in (o.get("addresses") or [])])
    timestamp = tx.get("confirmed")
    timestamp = datetime.fromisoformat(timestamp.replace("Z","+00:00")).strftime("%Y-%m-%d %H:%M:%S") if timestamp else "Unknown"
    return f"🔔 Նոր փոխանցում!\n📌 Address: {address}\n💰 Amount: {total_received:.8f} DASH\n🕒 Time: {timestamp}\n🔗 https://blockchair.com/dash/transaction/{txid}"

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

def monitor():
    while True:
        cursor.execute("SELECT user_id, address FROM users")
        all_users = cursor.fetchall()
        for user_id, address in all_users:
            txs = get_latest_txs(address)
            cursor.execute("SELECT txid FROM sent_txs WHERE user_id=? AND address=?", (user_id, address))
            sent = {row[0] for row in cursor.fetchall()}

            new_txs = []
            for tx in reversed(txs):
                txid = tx["hash"]
                if txid not in sent:
                    new_txs.append(tx)
            
            # Ուղարկել միայն վերջին 10 նոր TX-երը
            for tx in new_txs[-10:]:
                alert = format_alert(tx, address)
                try:
                    bot.send_message(user_id, alert)
                except:
                    pass
                cursor.execute("INSERT OR IGNORE INTO sent_txs (txid, user_id, address, num) VALUES (?, ?, ?, ?)",
                               (tx["hash"], user_id, address, 0))
            # Մնացածները ջնջել՝ միայն 10 վերջինը պահելու համար
            cursor.execute("DELETE FROM sent_txs WHERE user_id=? AND address=? AND txid NOT IN (SELECT txid FROM sent_txs WHERE user_id=? AND address=? ORDER BY rowid DESC LIMIT 10)", (user_id, address, user_id, address))
            conn.commit()
        time.sleep(3)

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

if __name__ == "__main__":
    threading.Thread(target=monitor, daemon=True).start()
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host="0.0.0.0", port=5000)

import os
import json
import time
import threading
import requests
import telebot
from flask import Flask, request
from datetime import datetime

# ===== Environment Variables =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

if not BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("Set BOT_TOKEN and WEBHOOK_URL in Render environment variables")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ===== Helpers =====
USERS_FILE = "users.json"
SENT_TX_FILE = "sent_txs.json"

def load_json(file):
    return json.load(open(file, "r", encoding="utf-8")) if os.path.exists(file) else {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

users = load_json(USERS_FILE)
sent_txs = load_json(SENT_TX_FILE)

# ===== Blockchair functions =====
def get_address_txs(address):
    try:
        r = requests.get(f"https://api.blockchair.com/dash/dashboards/address/{address}", timeout=20)
        if r.status_code == 200:
            data = r.json()
            return data["data"][address]["transactions"]
    except:
        return []
    return []

def get_tx_details(txid):
    try:
        r = requests.get(f"https://api.blockchair.com/dash/dashboards/transaction/{txid}", timeout=20)
        if r.status_code == 200:
            return r.json()["data"][txid]
    except:
        return None
    return None

def dash_to_usd(amount_dash):
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd", timeout=10)
        if r.status_code == 200:
            return amount_dash * r.json()["dash"]["usd"]
    except:
        return None
    return None

def format_alert(address, amount_dash, amount_usd, txid, timestamp, tx_number):
    link = f"https://blockchair.com/dash/transaction/{txid}"
    usd_text = f" (${amount_usd:.2f})" if amount_usd else ""
    return (
        f"🔔 Նոր փոխանցում #{tx_number}!\n\n"
        f"📌 Address: {address}\n"
        f"💰 Amount: {amount_dash:.8f} DASH{usd_text}\n"
        f"🕒 Time: {timestamp}\n"
        f"🔗 {link}"
    )

# ===== Telegram Handlers =====
@bot.message_handler(commands=['start'])
def start(msg):
    bot.reply_to(msg, "Բարև 👋 Գրիր քո Dash հասցեն (սկսվում է X-ով)")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("X"))
def save_address(msg):
    user_id = str(msg.chat.id)
    address = msg.text.strip()
    users.setdefault(user_id, [])
    if address not in users[user_id]:
        users[user_id].append(address)
    save_json(USERS_FILE, users)
    sent_txs.setdefault(user_id, {})
    sent_txs[user_id].setdefault(address, [])
    save_json(SENT_TX_FILE, sent_txs)
    bot.reply_to(msg, f"✅ Հասցեն {address} պահպանվեց!")

# ===== Background checker =====
def check_loop():
    while True:
        for user_id, addresses in users.items():
            for address in addresses:
                txids = get_address_txs(address)
                if not txids:
                    continue
                for txid in txids[:5]:
                    if txid not in sent_txs.get(user_id, {}).get(address, []):
                        details = get_tx_details(txid)
                        if details:
                            outputs = details.get("outputs", [])
                            total = sum(o["value"] for o in outputs if address in o.get("recipient", ""))
                            amount_dash = total / 1e8
                            amount_usd = dash_to_usd(amount_dash)
                            ts = details["transaction"]["time"]
                            timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
                            tx_number = len(sent_txs[user_id][address]) + 1
                            alert = format_alert(address, amount_dash, amount_usd, txid, timestamp, tx_number)
                            try:
                                bot.send_message(user_id, alert)
                                sent_txs[user_id][address].append(txid)
                                save_json(SENT_TX_FILE, sent_txs)
                            except:
                                pass
        time.sleep(10)

threading.Thread(target=check_loop, daemon=True).start()

# ===== Flask route for webhook =====
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

# ===== Set webhook =====
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

# ===== Run app =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

import telebot
import requests
import json
import os
import threading
import time
from flask import Flask, request
from datetime import datetime

# ===== Telegram Bot =====
BOT_TOKEN = "8294188586:AAEOQdJZySFXMeWSiFMi6zhpgzezCq1YL14"
WEBHOOK_URL = f"https://eroil666-2.onrender.com/{BOT_TOKEN}"

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
        url = f"https://api.blockchair.com/dash/dashboards/address/{address}"
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            data = r.json().get("data", {})
            if address in data:
                return data[address].get("transactions", [])
        return []
    except Exception as e:
        print(f"Error get_address_txs: {e}")
        return []

def get_received_amount(address, txid):
    try:
        url = f"https://api.blockchair.com/dash/dashboards/transaction/{txid}"
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            return 0.0
        data = r.json().get("data", {}).get(txid, {})
        outputs = data.get("outputs", [])
        total = 0
        for o in outputs:
            recipient = o.get("recipient")
            value = o.get("value", 0)
            if recipient == address:
                total += value
        return total / 1e8  # Satoshis → DASH
    except Exception as e:
        print(f"Error get_received_amount {txid}: {e}")
        return 0.0

def dash_to_usd(amount_dash):
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd", timeout=10)
        if r.status_code == 200:
            price = r.json().get("dash", {}).get("usd")
            if price is not None:
                return amount_dash * price
    except Exception as e:
        print(f"Error dash_to_usd: {e}")
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
                for txid in txids[:5]:  # վերջին 5 գործարքը
                    if txid not in sent_txs.get(user_id, {}).get(address, []):
                        amount_dash = get_received_amount(address, txid)
                        if amount_dash > 0:
                            amount_usd = dash_to_usd(amount_dash)
                            ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                            tx_number = len(sent_txs[user_id][address]) + 1
                            alert = format_alert(address, amount_dash, amount_usd, txid, ts, tx_number)
                            try:
                                bot.send_message(user_id, alert)
                                sent_txs[user_id][address].append(txid)
                                save_json(SENT_TX_FILE, sent_txs)
                            except Exception as e:
                                print(f"Error sending message: {e}")
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

# ===== Run Flask =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

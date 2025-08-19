import telebot
import requests
import json
import os
import time
import threading
from flask import Flask, request

# ===== Telegram Bot =====
BOT_TOKEN = "8294188586:AAEOQdJZySFXMeWSiFMi6zhpgzezCq1YL14"
WEBHOOK_URL = "https://eroil666-2.onrender.com/8294188586:AAEOQdJZySFXMeWSiFMi6zhpgzezCq1YL14"

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

# ===== Telegram Handlers =====
@bot.message_handler(commands=['start'])
def start(msg):
    bot.reply_to(msg, "Բարև 👋 Գրի՛ր քո Dash հասցեն (սկսվում է X-ով)")

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

# ===== Blockchain checker =====
def check_transactions():
    while True:
        try:
            for user_id, addresses in users.items():
                for address in addresses:
                    url = f"https://api.blockcypher.com/v1/dash/main/addrs/{address}"
                    r = requests.get(url, timeout=10)
                    if r.status_code == 200:
                        data = r.json()
                        txs = data.get("txrefs", [])
                        for tx in txs:
                            tx_hash = tx["tx_hash"]
                            if tx_hash not in sent_txs[user_id][address]:
                                amount = tx["value"] / 1e8
                                bot.send_message(user_id, f"💸 Նոր փոխանցում!\nHash: {tx_hash}\nԳումար: {amount} DASH")
                                sent_txs[user_id][address].append(tx_hash)
                                save_json(SENT_TX_FILE, sent_txs)
        except Exception as e:
            print("Error in checker:", e)
        time.sleep(10)  # ամեն 10 վայրկյանը մեկ ստուգում է

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

if __name__ == "__main__":
    threading.Thread(target=check_transactions, daemon=True).start()
    port = int(5000)
    app.run(host="0.0.0.0", port=port)

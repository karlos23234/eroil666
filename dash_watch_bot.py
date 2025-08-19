import os
import time
import requests
import telebot
from flask import Flask, request
from datetime import datetime

# ======== CONFIG ========
BOT_TOKEN = "8294188586:AAEOQdJZySFXMeWSiFMi6zhpgzezCq1YL14"
CHAT_ID = 123456789   # քո Telegram chat ID (օգտագործիր /start որ գրեմ chat_id)
DASH_ADDRESS = "XekdVU8vhmkaSsEDf9FrGdgLvvJsphi4DE"  # քո Dash հասցեն
WEBHOOK_HOST = "https://eroil666-4.onrender.com"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
app = Flask(__name__)

# պահում ենք վերջին հայտնի TX hash-ը
last_seen_tx = None

# ======== HELPERS ========
def get_latest_tx(address):
    """Վերադարձնում է վերջին տրանզակցիայի տվյալները Blockchair-ից"""
    try:
        url = f"https://api.blockchair.com/dash/dashboards/address/{address}"
        r = requests.get(url, timeout=10)
        data = r.json()["data"][address]["transactions"]

        if not data:
            return None

        latest_tx_hash = data[0]
        tx_url = f"https://api.blockchair.com/dash/raw/transaction/{latest_tx_hash}"
        tx_data = requests.get(tx_url, timeout=10).json()
        tx_info = tx_data["data"][latest_tx_hash]["decoded_raw_transaction"]

        # ժամանակը
        blockchair_url = f"https://blockchair.com/dash/transaction/{latest_tx_hash}"
        timestamp = datetime.utcfromtimestamp(
            tx_data["data"][latest_tx_hash]["transaction"]["time"]
        ).strftime("%Y-%m-%d %H:%M:%S")

        # գումարը (միավորները Սատոշի են → /1e8)
        total_out = sum([int(o["value"]) for o in tx_info["vout"]])
        dash_amount = total_out / 1e8

        return {
            "hash": latest_tx_hash,
            "address": address,
            "amount": dash_amount,
            "time": timestamp,
            "url": blockchair_url
        }
    except Exception as e:
        print("❌ Error:", e)
        return None

def format_tx_message(tx, index):
    return (
        f"🔔 Նոր փոխանցում #{index}!\n\n"
        f"📌 Address: {tx['address']}\n"
        f"💰 Amount: {tx['amount']:.8f} DASH\n"
        f"🕒 Time: {tx['time']}\n"
        f"🔗 {tx['url']}"
    )

# ======== BACKGROUND CHECKER ========
def tx_watcher():
    global last_seen_tx
    index = 1
    while True:
        tx = get_latest_tx(DASH_ADDRESS)
        if tx and tx["hash"] != last_seen_tx:
            last_seen_tx = tx["hash"]
            msg = format_tx_message(tx, index)
            bot.send_message(CHAT_ID, msg)
            index += 1
        time.sleep(10)  # ստուգում ամեն 10 վայրկյան

# ======== TELEGRAM HANDLERS ========
@bot.message_handler(commands=["start"])
def start_cmd(message):
    global CHAT_ID
    CHAT_ID = message.chat.id
    bot.send_message(
        CHAT_ID,
        "👋 Բարի գալուստ!\n"
        "Ես քեզ կուղարկեմ վերջին նոր Dash փոխանցումները։"
    )

# ======== FLASK WEBHOOK ========
@app.route("/webhook", methods=["POST"])
def webhook():
    if request.headers.get("content-type") == "application/json":
        json_str = request.get_data().decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
        return "OK", 200
    else:
        return "Unsupported Media Type", 415

# ======== MAIN ========
if __name__ == "__main__":
    import threading

    port = int(os.environ.get("PORT", 5000))

    # Remove old webhook
    bot.remove_webhook()
    WEBHOOK_URL = f"{WEBHOOK_HOST}/webhook"
    bot.set_webhook(url=WEBHOOK_URL)

    # Start TX watcher in background
    threading.Thread(target=tx_watcher, daemon=True).start()

    print(f"🚀 Bot running with webhook at {WEBHOOK_URL}")
    app.run(host="0.0.0.0", port=port)

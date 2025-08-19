import os
import json
import requests
import time
from datetime import datetime
import threading
from flask import Flask, request
import telebot
import re

# ===== Կարգավորումներ =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("Պետք է սահմանել BOT_TOKEN և WEBHOOK_URL փոփոխականները")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

USERS_FILE = "users.json"
SENT_TX_FILE = "sent_txs.json"
LOG_FILE = "bot.log"

# ===== Օժանդակ ֆունկցիաներ =====
def log_error(message):
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.now()}: {message}\n")

def load_json(filename):
    try:
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except Exception as e:
        log_error(f"Չհաջողվեց բեռնել {filename}: {e}")
        return {}

def save_json(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_error(f"Չհաջողվեց պահպանել {filename}: {e}")

users = load_json(USERS_FILE)
sent_txs = load_json(SENT_TX_FILE)

# ===== Dash հասցեի վավերացում =====
def is_valid_dash_address(address):
    return re.match(r'^X[a-zA-Z0-9]{33}$', address) is not None

# ===== API ֆունկցիաներ =====
def get_dash_price():
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd",
            timeout=10
        )
        return r.json().get("dash", {}).get("usd")
    except Exception as e:
        log_error(f"Գնի ստացման սխալ: {e}")
        return None

def get_transactions(address):
    try:
        r = requests.get(
            f"https://api.blockchair.com/dash/transactions?q=recipient({address})&limit=10",
            timeout=20
        )
        return r.json().get("data", [])
    except Exception as e:
        log_error(f"Գործարքների ստացման սխալ {address}-ի համար: {e}")
        return []

# ===== Զգուշացումների ձևաչափավորում =====
def format_alert(tx, address, tx_count, price=None):
    txid = tx.get("transaction_hash") or tx.get("hash")
    if not txid:
        return None
    amount = tx.get("output_total", 0) / 1e8
    if amount <= 0:
        return None
    usd_value = f" (${amount*price:.2f})" if price else ""
    tx_time = tx.get("time") or tx.get("block_time") or "Սպասվում է հաստատում"
    return (
        f"🔔 <b>Նոր գործարք #{tx_count}!</b>\n\n"
        f"📌 Հասցե: <code>{address}</code>\n"
        f"💰 Գումար: <b>{amount:.8f} DASH</b>{usd_value}\n"
        f"🕒 Ժամանակ: {tx_time}\n"
        f"🔗 <a href='https://blockchair.com/dash/transaction/{txid}'>Դիտել Blockchair-ում</a>"
    )

# ===== Telegram հրամաններ =====
@bot.message_handler(commands=['start', 'help'])
def start(message):
    bot.reply_to(message,
        "Բարև 👋 Այս բոտը թույլ է տալիս հետևել Dash հասցեներին:\n\n"
        "Հրամաններ:\n"
        "/add [հասցե] - Ավելացնել հասցե\n"
        "/list - Ցուցադրել բոլոր հասցեները\n"
        "/remove [հասցե] - Հեռացնել հասցե\n"
        "/price - Տեսնել Dash-ի ընթացիկ գինը"
    )

@bot.message_handler(commands=['price'])
def send_price(message):
    price = get_dash_price()
    if price:
        bot.reply_to(message, f"💰 Dash-ի ընթացիկ գինը: ${price:.2f}")
    else:
        bot.reply_to(message, "❌ Չհաջողվեց ստանալ գինը")

@bot.message_handler(commands=['list'])
def list_addresses(message):
    user_id = str(message.chat.id)
    if user_id in users and users[user_id]:
        addresses = "\n".join(f"• <code>{addr}</code>" for addr in users[user_id])
        bot.reply_to(message, f"📋 Քո հասցեները:\n{addresses}")
    else:
        bot.reply_to(message, "❌ Չկան գրանցված հասցեներ")

@bot.message_handler(commands=['remove'])
def remove_address(message):
    user_id = str(message.chat.id)
    parts = message.text.split()
    address = parts[1] if len(parts) > 1 else None
    if not address:
        bot.reply_to(message, "❌ Օգտագործում: /remove X...")
        return
    if user_id in users and address in users[user_id]:
        users[user_id].remove(address)
        save_json(USERS_FILE, users)
        if user_id in sent_txs and address in sent_txs[user_id]:
            del sent_txs[user_id][address]
            save_json(SENT_TX_FILE, sent_txs)
        bot.reply_to(message, f"✅ Հասցեն <code>{address}</code> ջնջված է")
    else:
        bot.reply_to(message, f"❌ Հասցեն <code>{address}</code> չի գտնվել")

@bot.message_handler(commands=['add'])
def add_address(message):
    user_id = str(message.chat.id)
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ Օգտագործում: /add X...")
        return
    address = parts[1].strip()
    if not is_valid_dash_address(address):
        bot.reply_to(message, "❌ Անվավեր Dash հասցե")
        return
    users.setdefault(user_id, [])
    if address in users[user_id]:
        bot.reply_to(message, f"❌ Հասցեն {address} արդեն ավելացված է")
        return
    if len(users[user_id]) >= 5:
        bot.reply_to(message, "❌ Կարող եք ավելացնել առավելագույնը 5 հասցե")
        return
    users[user_id].append(address)
    save_json(USERS_FILE, users)
    sent_txs.setdefault(user_id, {})[address] = []
    save_json(SENT_TX_FILE, sent_txs)
    bot.reply_to(message, f"✅ Հասցեն {address} հաջողությամբ ավելացվեց")

# ===== Monitor loop =====
def monitor():
    while True:
        try:
            price = get_dash_price()
            for user_id, addresses in users.items():
                for address in addresses:
                    txs = get_transactions(address)
                    known = sent_txs.get(user_id, {}).get(address, [])
                    last_number = len(known)
                    for tx in reversed(txs):
                        txid = tx.get("transaction_hash") or tx.get("hash")
                        if not txid or txid in known:
                            continue
                        last_number += 1
                        alert = format_alert(tx, address, last_number, price)
                        if alert:
                            try:
                                bot.send_message(user_id, alert, disable_web_page_preview=True)
                            except Exception as e:
                                log_error(f"Send error: {e}")
                        sent_txs.setdefault(user_id, {}).setdefault(address, []).append(txid)
                        # Պահպանել միայն վերջին 50 TX-երը
                        sent_txs[user_id][address] = sent_txs[user_id][address][-50:]
            save_json(SENT_TX_FILE, sent_txs)
            time.sleep(15)
        except Exception as e:
            log_error(f"Monitor error: {e}")
            time.sleep(30)

# ===== Flask սերվեր =====
app = Flask(__name__)

@app.route("/")
def home():
    return "Dash Alert Bot is running!"

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

if __name__ == "__main__":
    threading.Thread(target=monitor, daemon=True).start()
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=5000)

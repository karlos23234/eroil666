import os
import json
import requests
import time
from datetime import datetime
import threading
from flask import Flask, request
import telebot
import re  # Հասցեի վավերացման համար

# ===== Կարգավորումներ =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("Պետք է սահմանել BOT_TOKEN և WEBHOOK_URL փոփոխականները")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# Ֆայլային կարգավորումներ
USERS_FILE = "users.json"  # Օգտատերերի տվյալներ
SENT_TX_FILE = "sent_txs.json"  # Ուղարկված գործարքներ
LOG_FILE = "bot.log"  # Սխալների լոգ

# ===== Օժանդակ ֆունկցիաներ =====
def log_error(message):
    """Սխալների լոգավորում"""
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.now()}: {message}\n")

def load_json(filename):
    """JSON ֆայլի բեռնում"""
    try:
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except Exception as e:
        log_error(f"Չհաջողվեց բեռնել {filename}: {e}")
        return {}

def save_json(filename, data):
    """JSON ֆայլի պահպանում"""
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_error(f"Չհաջողվեց պահպանել {filename}: {e}")

# Տվյալների բեռնում
users = load_json(USERS_FILE)  # {user_id: [address1, address2]}
sent_txs = load_json(SENT_TX_FILE)  # {user_id: {address: [tx1, tx2]}}

# ===== Dash հասցեի վավերացում =====
def is_valid_dash_address(address):
    """Ստուգում է Dash հասցեի ճիշտ ձևաչափը"""
    return re.match(r'^X[a-zA-Z0-9]{33}$', address) is not None

# ===== API ֆունկցիաներ =====
def get_dash_price():
    """Ստանում է Dash-ի գինը USD-ով"""
    try:
        response = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd",
            timeout=10
        )
        return response.json().get("dash", {}).get("usd")
    except Exception as e:
        log_error(f"Գնի ստացման սխալ: {e}")
        return None

def get_transactions(address):
    """Ստանում է վերջին գործարքները"""
    try:
        response = requests.get(
            f"https://api.blockchair.com/dash/dash/transactions?q=recipient({address})&limit=10",
            timeout=20
        )
        return response.json().get("data", [])
    except Exception as e:
        log_error(f"Գործարքների ստացման սխալ {address}-ի համար: {e}")
        return []

# ===== Զգուշացումների ձևաչափավորում =====
def format_alert(tx, address, tx_count, price=None):
    """Ստեղծում է հաղորդագրություն նոր գործարքի մասին"""
    txid = tx["hash"]
    amount = tx["output_total"] / 1e8  # Սատոշիից DASH
    
    if amount <= 0:
        return None

    # USD արժեք (եթե գինը հասանելի է)
    usd_value = f" (${amount * price:.2f})" if price else ""
    
    # Ժամանակի ձևաչափավորում
    tx_time = tx.get("time")
    if tx_time:
        tx_time = datetime.strptime(tx_time, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
    else:
        tx_time = "Սպասվում է հաստատում"

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
    """Սկզբնական հաղորդագրություն"""
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
    """Ուղարկում է Dash-ի ընթացիկ գինը"""
    price = get_dash_price()
    if price:
        bot.reply_to(message, f"💰 Dash-ի ընթացիկ գինը: ${price:.2f}")
    else:
        bot.reply_to(message, "❌ Չհաջողվեց ստանալ գինը")

# ... (այլ հրամանների դիմացձեր) ...

# ===== Հիմնական մոնիտորինգի ցիկլ =====
def monitor():
    while True:
        try:
            price = get_dash_price()
            
            for user_id, addresses in users.items():
                for address in addresses:
                    # Ստանալ նոր գործարքներ
                    transactions = get_transactions(address)
                    
                    # Ստուգել նոր գործարքները
                    known_txs = sent_txs.get(user_id, {}).get(address, [])
                    new_txs = [tx for tx in transactions if tx["hash"] not in known_txs]
                    
                    # Ուղարկել զգուշացումներ
                    for tx in new_txs:
                        alert = format_alert(tx, address, len(known_txs)+1, price)
                        if alert:
                            try:
                                bot.send_message(user_id, alert, disable_web_page_preview=True)
                                # Պահպանել ուղարկված գործարքը
                                sent_txs.setdefault(user_id, {}).setdefault(address, []).append(tx["hash"])
                            except Exception as e:
                                log_error(f"Հաղորդագրության ուղարկման սխալ {user_id}-ին: {e}")
            
            # Պահպանել տվյալները
            save_json(SENT_TX_FILE, sent_txs)
            time.sleep(60)  # Ստուգել ամեն 1 րոպեն մեկ
            
        except Exception as e:
            log_error(f"Մոնիտորինգի սխալ: {e}")
            time.sleep(300)  # Սպասել 5 րոպե սխալի դեպքում

# ===== Flask սերվեր Render-ի համար =====
app = Flask(__name__)

@app.route("/")
def home():
    return "Dash Monitor Bot is running!"

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

# ===== Գործարկում =====
if __name__ == "__main__":
    # Մեկնարկել մոնիտորինգի թրեդը
    threading.Thread(target=monitor, daemon=True).start()
    
    # Կարգավորել webhook-ը
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=WEBHOOK_URL)
    
    # Մեկնարկել Flask սերվերը
    app.run(host="0.0.0.0", port=5000)


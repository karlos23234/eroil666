import telebot
import requests
import json
import os
import time
from datetime import datetime

# ===== Telegram Bot =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # Տես, որ BOT_TOKEN պետք է լինի Render Environment Variables
bot = telebot.TeleBot(BOT_TOKEN)

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

# ===== BlockCypher functions =====
def get_address_txs(address, limit=5):
    try:
        url = f"https://api.blockcypher.com/v1/dash/main/addrs/{address}/full?limit={limit}"
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            data = r.json()
            return data.get("txs", [])
        return []
    except Exception as e:
        print("Error fetching TXs:", e)
        return []

def dash_to_usd(amount_dash):
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd", timeout=10)
        if r.status_code == 200:
            return amount_dash * r.json()["dash"]["usd"]
    except:
        return None
    return None

def format_alert(tx, address, tx_number):
    txid = tx["hash"]
    total_received = sum([o["value"] for o in tx.get("outputs", []) if address in o.get("addresses", [])]) / 1e8
    amount_usd = dash_to_usd(total_received)
    timestamp = tx.get("confirmed", None)
    if timestamp:
        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
    else:
        timestamp = "Unknown"
    usd_text = f" (${amount_usd:.2f})" if amount_usd else ""
    return (
        f"🔔 Նոր փոխանցում #{tx_number}!\n\n"
        f"📌 Address: {address}\n"
        f"💰 Amount: {total_received:.8f} DASH{usd_text}\n"
        f"🕒 Time: {timestamp}\n"
        f"🔗 https://live.blockcypher.com/dash/tx/{txid}/"
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

# ===== Background loop =====
def check_loop():
    while True:
        for user_id, addresses in users.items():
            for address in addresses:
                txs = get_address_txs(address)
                if not txs:
                    continue
                for i, tx in enumerate(txs[:5], start=1):
                    if tx["hash"] not in sent_txs.get(user_id, {}).get(address, []):
                        alert = format_alert(tx, address, i)
                        try:
                            bot.send_message(user_id, alert)
                            sent_txs[user_id][address].append(tx["hash"])
                            save_json(SENT_TX_FILE, sent_txs)
                        except Exception as e:
                            print("Telegram send error:", e)
        time.sleep(10)

# ===== Run bot =====
import threading
threading.Thread(target=check_loop, daemon=True).start()
bot.infinity_polling()

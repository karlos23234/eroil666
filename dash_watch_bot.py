import os
import json
import requests
import time
from datetime import datetime
import threading
from flask import Flask, request
import telebot
import re
from aiohttp import ClientSession
import asyncio

# ===== Environment variables =====
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
if not BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("Պետք է ավելացնես BOT_TOKEN և WEBHOOK_URL Env Variable-ներով")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

USERS_FILE = "users.json"
SENT_TX_FILE = "sent_txs.json"
LOG_FILE = "bot.log"

# ===== Helpers =====
def log_message(message):
    with open(LOG_FILE, "a") as f:
        f.write(f"{datetime.now()}: {message}\n")

def load_json(file):
    try:
        return json.load(open(file, "r", encoding="utf-8")) if os.path.exists(file) else {}
    except Exception as e:
        log_message(f"Error loading {file}: {e}")
        return {}

def save_json(file, data):
    try:
        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log_message(f"Error saving {file}: {e}")

users = load_json(USERS_FILE)
sent_txs = load_json(SENT_TX_FILE)

# ===== Address Validation =====
def is_valid_dash_address(address):
    """Validate Dash address format"""
    return re.match(r'^X[a-zA-Z0-9]{33}$', address) is not None

# ===== Price API =====
async def get_dash_price_usd():
    try:
        async with ClientSession() as session:
            async with session.get("https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd", timeout=10) as resp:
                data = await resp.json()
                return float(data.get("dash", {}).get("usd", 0))
    except Exception as e:
        log_message(f"Price API error: {e}")
        return None

# ===== Transaction APIs =====
async def get_latest_txs(address):
    """Get transactions from Blockchair API"""
    try:
        async with ClientSession() as session:
            url = f"https://api.blockchair.com/dash/dash/transactions?q=recipient({address})&limit=10"
            async with session.get(url, timeout=20) as resp:
                data = await resp.json()
                return data.get("data", [])
    except Exception as e:
        log_message(f"TX API error for {address}: {e}")
        return []

# ===== Alert Formatter =====
def format_alert(tx, address, tx_number, price):
    txid = tx["hash"]
    total_received = tx["output_total"] / 1e8  # Convert from satoshis
    
    if total_received <= 0:
        return None

    usd_text = f" (${total_received*price:.2f})" if price else ""
    timestamp = tx.get("time")
    if timestamp:
        timestamp = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")
    else:
        timestamp = "Pending"

    return (
        f"🔔 <b>Նոր փոխանցում #{tx_number}!</b>\n\n"
        f"📌 Address: <code>{address}</code>\n"
        f"💰 Amount: <b>{total_received:.8f} DASH</b>{usd_text}\n"
        f"🕒 Time: {timestamp}\n"
        f"🔗 <a href='https://blockchair.com/dash/transaction/{txid}'>Դիտել Blockchair-ում</a>"
    )

# ===== Telegram Handlers =====
@bot.message_handler(commands=['start', 'help'])
def start(msg):
    bot.reply_to(msg, "Բարև 👋 Գրիր քո Dash հասցեն (սկսվում է X-ով)։\n\n"
                     "Հրամաններ:\n"
                     "/list - Ցուցադրել բոլոր հասցեները\n"
                     "/delete [հասցե] - Ջնջել հասցեն\n"
                     "/price - Տեսնել Dash-ի գինը")

@bot.message_handler(commands=['price'])
async def send_price(msg):
    price = await get_dash_price_usd()
    if price:
        bot.reply_to(msg, f"💰 Dash-ի ընթացիկ գինը: ${price:.2f}")
    else:
        bot.reply_to(msg, "❌ Չհաջողվեց ստանալ գինը")

@bot.message_handler(commands=['list'])
def list_addresses(msg):
    user_id = str(msg.chat.id)
    if user_id in users and users[user_id]:
        addresses = "\n".join(f"• <code>{addr}</code>" for addr in users[user_id])
        bot.reply_to(msg, f"📋 Քո հասցեները:\n{addresses}")
    else:
        bot.reply_to(msg, "❌ Չկան գրանցված հասցեներ")

@bot.message_handler(commands=['delete'])
def delete_address(msg):
    user_id = str(msg.chat.id)
    address = msg.text.split()[1] if len(msg.text.split()) > 1 else None
    
    if not address:
        bot.reply_to(msg, "❌ Օգտագործում: /delete X...")
        return
    
    if user_id in users and address in users[user_id]:
        users[user_id].remove(address)
        save_json(USERS_FILE, users)
        
        if user_id in sent_txs and address in sent_txs[user_id]:
            del sent_txs[user_id][address]
            save_json(SENT_TX_FILE, sent_txs)
        
        bot.reply_to(msg, f"✅ Հասցեն <code>{address}</code> ջնջված է")
    else:
        bot.reply_to(msg, f"❌ Հասցեն <code>{address}</code> չի գտնվել")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("X"))
def save_address(msg):
    user_id = str(msg.chat.id)
    address = msg.text.strip()
    
    if not is_valid_dash_address(address):
        bot.reply_to(msg, "❌ Անվավեր Dash հասցե: Պետք է սկսվի X-ով և պարունակի 34 նիշ")
        return
    
    if user_id in users and len(users[user_id]) >= 5:  # Limit to 5 addresses per user
        bot.reply_to(msg, "❌ Դուք կարող եք հետևել առավելագույնը 5 հասցեի")
        return
    
    users.setdefault(user_id, [])
    if address not in users[user_id]:
        users[user_id].append(address)
    save_json(USERS_FILE, users)

    sent_txs.setdefault(user_id, {})
    sent_txs[user_id].setdefault(address, [])
    save_json(SENT_TX_FILE, sent_txs)

    bot.reply_to(msg, f"✅ Հասցեն <code>{address}</code> պահպանվեց։")

# ===== Background Monitoring =====
async def monitor_loop():
    while True:
        try:
            price = await get_dash_price_usd()
            
            for user_id, addresses in users.items():
                for address in addresses:
                    txs = await get_latest_txs(address)
                    known_txs = [t["txid"] for t in sent_txs.get(user_id, {}).get(address, [])]
                    last_number = max([t.get("num",0) for t in sent_txs.get(user_id, {}).get(address, [])], default=0)

                    for tx in reversed(txs):
                        txid = tx["hash"]
                        if txid in known_txs:
                            continue
                        
                        last_number += 1
                        alert = format_alert(tx, address, last_number, price)
                        if not alert:
                            continue
                        
                        try:
                            await bot.send_message(user_id, alert, disable_web_page_preview=True)
                        except Exception as e:
                            log_message(f"Send message error: {e}")

                        sent_txs.setdefault(user_id, {}).setdefault(address, []).append({"txid": txid, "num": last_number})
                        sent_txs[user_id][address] = sent_txs[user_id][address][-50:]  # Keep last 50 txs

            save_json(SENT_TX_FILE, sent_txs)
            await asyncio.sleep(10)  # Check every 10 seconds
            
        except Exception as e:
            log_message(f"Monitor error: {e}")
            await asyncio.sleep(30)

# ===== Flask Server =====
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

def run_bot():
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    asyncio.run(monitor_loop())

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=5000)

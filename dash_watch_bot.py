import os
import requests
import telebot

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")  # Դու Telegram chat ID-ն պահում ես որպես environment variable
ADDRESS = os.getenv("DASH_ADDRESS")  # Պроверяемый Dash հասցեն

bot = telebot.TeleBot(BOT_TOKEN)

def get_latest_txs(address):
    try:
        r = requests.get(f"https://api.blockcypher.com/v1/dash/main/addrs/{address}/full?limit=10", timeout=20)
        return r.json().get("txs", [])
    except Exception as e:
        print("Error fetching TX:", e)
        return []

txs = get_latest_txs(ADDRESS)

if not txs:
    print("No TX found for address:", ADDRESS)
else:
    for i, tx in enumerate(txs, 1):
        txid = tx["hash"]
        total_received = sum([o.get("value",0)/1e8 for o in tx.get("outputs", []) if ADDRESS in (o.get("addresses") or [])])
        msg = f"TX #{i}:\nAddress: {ADDRESS}\nAmount: {total_received} DASH\nTXID: {txid}\nhttps://blockchair.com/dash/transaction/{txid}"
        print(msg)
        try:
            bot.send_message(CHAT_ID, msg)
        except Exception as e:
            print("Telegram send error:", e)


def load_json(file):
    return json.load(open(file, "r", encoding="utf-8")) if os.path.exists(file) else {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

users = load_json(USERS_FILE)
sent_txs = load_json(SENT_TX_FILE)

def get_dash_price_usd():
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=dash&vs_currencies=usd", timeout=10)
        return float(r.json().get("dash", {}).get("usd", 0))
    except:
        return None

def get_latest_txs(address):
    try:
        r = requests.get(f"https://api.blockcypher.com/v1/dash/main/addrs/{address}/full?limit=10", timeout=20)
        return r.json().get("txs", [])
    except:
        return []

def format_alert(address, amount_dash, amount_usd, txid, timestamp, tx_number):
    link = f"https://blockchair.com/dash/transaction/{txid}"
    usd_text = f" (${amount_usd:.2f})" if amount_usd else ""
    return (
        f"🔔 Նոր փոխանցում #{tx_number}!\n\n"
        f"📌 Address: {address}\n"
        f"💰 Amount: {amount_dash:.8f} DASH{usd_text}\n"
        f"🕒 Time: {timestamp}\n"
        f"🔗 {link}\n\n"
        f"Blockchair ({link})\n"
        f"Dash transaction {txid}\n"
        f"Inspect Dash transaction {txid}: check hash, date, and event details with Blockchair."
    )

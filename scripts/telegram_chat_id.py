"""Send any message to your bot first, then run this to print your chat id."""
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
token = os.getenv("TELEGRAM_BOT_TOKEN")
if not token:
    sys.exit("Set TELEGRAM_BOT_TOKEN in .env first (from @BotFather).")
resp = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20).json()
if not resp.get("ok"):
    sys.exit(f"Telegram rejected the token: {resp.get('description')}")
chats = {(u["message"]["chat"]["id"], u["message"]["chat"].get("username") or u["message"]["chat"].get("first_name"))
         for u in resp.get("result", []) if u.get("message")}
if not chats:
    sys.exit("No messages yet. Open your bot in Telegram, send it 'hi', then run this again.")
for chat_id, name in chats:
    print(f"TELEGRAM_CHAT_ID={chat_id}   ({name})")

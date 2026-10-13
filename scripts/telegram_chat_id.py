"""Send any message to your bot first, then run this to print your chat id."""
import os, requests
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
token = os.environ["TELEGRAM_BOT_TOKEN"]
for u in requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20).json().get("result", []):
    chat = (u.get("message") or {}).get("chat")
    if chat:
        print(chat["id"], chat.get("username") or chat.get("first_name"))

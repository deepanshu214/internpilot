import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _yaml(rel):
    with open(ROOT / rel) as f:
        return yaml.safe_load(f)


SETTINGS = _yaml("config/settings.yaml")
WATCHLIST = _yaml("config/watchlist.yaml")
PROFILE = _yaml("profile/profile.yaml")

DATABASE_URL = os.getenv("DATABASE_URL", "")          # Supabase Postgres URL; empty = local SQLite
SQLITE_PATH = os.getenv("SQLITE_PATH", str(ROOT / "internpilot.db"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "")
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY", "")
# Outreach is a dry run (emails written to outbox/ as .eml, nothing sent) until you set DRY_RUN=0.
DRY_RUN = os.getenv("DRY_RUN", "1") != "0"
GMAIL_CREDENTIALS = Path(os.getenv("GMAIL_CREDENTIALS", str(ROOT / "secrets/gmail_credentials.json")))
GMAIL_TOKEN = Path(os.getenv("GMAIL_TOKEN", str(ROOT / "secrets/gmail_token.json")))
OUTPUT_DIR = ROOT / "output"
OUTBOX_DIR = ROOT / "outbox"

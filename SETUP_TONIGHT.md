# InternPilot: setup checklist (things only you can do)

Work top to bottom. Each step says how to check it worked.

## 1. Telegram alerts (5 min)
1. In Telegram, message **@BotFather** → `/newbot` → copy the token.
2. `cd ~/Desktop/internpilot && cp .env.example .env` and set `TELEGRAM_BOT_TOKEN=` in `.env`.
3. Send any message to your new bot, then run:
   `.venv/bin/python scripts/telegram_chat_id.py` → put the number in `TELEGRAM_CHAT_ID=`.
- ✅ Check: `.venv/bin/python -m worker.scheduler --once` sends alerts to your phone.

## 2. Local LLM (15 min, ~5 GB download)
`brew install ollama && brew services start ollama && ollama pull qwen2.5:7b && ollama pull nomic-embed-text`
- ✅ Check: the run log says `llm: ollama`.
- Optional: a free Groq key from console.groq.com → `GROQ_API_KEY=` (used when Ollama is off).

## 3. Review your profile (10 min)
Open `profile/profile.yaml`: add your LinkedIn URL and the project GitHub links, and fix anything wrong.
This file is the only source the resume tailor is allowed to use.

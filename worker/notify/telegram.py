import html
import json
import logging
import re

import requests

from ..config import DASHBOARD_URL, SETTINGS, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from ..logsafe import redact

log = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/{method}"


def enabled() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def send(text: str, buttons: list[list[dict]] | None = None) -> bool:
    if not enabled():
        print(html.unescape(re.sub(r"</?[bi]>", "", text)), "\n")
        return True
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if buttons:
        payload["reply_markup"] = json.dumps({"inline_keyboard": buttons})
    try:
        r = requests.post(API.format(token=TELEGRAM_BOT_TOKEN, method="sendMessage"), data=payload, timeout=20)
        if r.status_code == 400 and "parse" in r.text.lower():
            # Formatting rejected (e.g. a stray "<" in a job title): send the same text as plain text instead.
            payload["text"] = html.unescape(re.sub(r"</?[a-z]+>", "", text))
            payload.pop("parse_mode")
            r = requests.post(API.format(token=TELEGRAM_BOT_TOKEN, method="sendMessage"), data=payload, timeout=20)
        r.raise_for_status()
        return True
    except requests.RequestException as e:
        log.warning("telegram send failed: %s", redact(str(e)))
        return False


def format_match(row: dict) -> str:
    e = html.escape
    hot = "🔥 APPLY TODAY · " if row["score"] >= SETTINGS["match"]["hot_threshold"] else ""
    reasons = json.loads(row["reasons"]) if isinstance(row["reasons"], str) else row["reasons"]
    missing = json.loads(row["missing_skills"]) if isinstance(row["missing_skills"], str) else row["missing_skills"]
    lines = [f"{hot}<b>{row['score']}/100 · {e(row['title'])}</b>", f"🏢 {e(row['company'])} · 📍 {e(row['location'] or '—')}"]
    lines += [f"• {e(r)}" for r in reasons[:4]]
    if missing:
        lines.append(f"Gap: {e(', '.join(missing[:6]))}")
    lines.append(f"<i>via {e(row['source'])}</i>")
    return "\n".join(lines)


def alert(row: dict) -> bool:
    buttons = [[{"text": "Open posting", "url": row["url"]}],
               [{"text": "✅ Shortlist & prepare", "callback_data": f"sl:{row['id']}"},
                {"text": "⏭ Skip", "callback_data": f"sk:{row['id']}"}]]
    if DASHBOARD_URL:
        buttons[0].append({"text": "Dashboard", "url": f"{DASHBOARD_URL}/jobs/{row['id']}"})
    return send(format_match(row), buttons)

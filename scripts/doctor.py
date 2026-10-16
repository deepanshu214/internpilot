"""Setup checker: run after each step in SETUP_TONIGHT.md.  .venv/bin/python scripts/doctor.py
Only free, read-only calls (no AI quota used, no messages or emails sent)."""
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from worker import config  # noqa: E402

OK, BAD, WARN, SKIP = "✅", "❌", "⚠️ ", "○ "
results = []


def check(name: str, fn):
    try:
        status, detail = fn()
    except Exception as e:  # a check must never crash the doctor
        status, detail = BAD, f"{type(e).__name__}: {e}"
    results.append(status)
    print(f"{status} {name}: {detail}")


def deps():
    import bs4, dns, googleapiclient, jobspy, playwright, psycopg, pypdf, typst  # noqa: F401
    chromium = list(Path.home().glob("Library/Caches/ms-playwright/chromium-*"))
    return (OK, "all Python packages + Chromium installed") if chromium else \
        (WARN, "run: .venv/bin/python -m playwright install chromium")


def profile():
    p = config.PROFILE
    missing = [x["name"].split(" — ")[0] for x in p["projects"] if not x.get("url")]
    issues = []
    if not p["links"].get("linkedin"):
        issues.append("LinkedIn URL")
    if missing:
        issues.append(f"GitHub links for {', '.join(missing)}")
    return (OK, "complete") if not issues else (WARN, f"add {' and '.join(issues)} in profile/profile.yaml (step 1)")


def env_file():
    return (OK, ".env present") if (config.ROOT / ".env").exists() else (BAD, "run: cp .env.example .env")


def telegram():
    if not config.TELEGRAM_BOT_TOKEN:
        return BAD, "set TELEGRAM_BOT_TOKEN (step 2)"
    me = requests.get(f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getMe", timeout=15).json()
    if not me.get("ok"):
        return BAD, f"token rejected: {me.get('description')}"
    if not config.TELEGRAM_CHAT_ID:
        return WARN, f"bot @{me['result']['username']} works; now message it and run scripts/telegram_chat_id.py"
    return OK, f"@{me['result']['username']} → chat {config.TELEGRAM_CHAT_ID}"


def groq():
    if not config.GROQ_API_KEY:
        return BAD, "set GROQ_API_KEY (step 3, free, no card)"
    r = requests.get("https://api.groq.com/openai/v1/models", timeout=15,
                     headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"})
    if r.status_code != 200:
        return BAD, f"key rejected ({r.status_code})"
    have = {m["id"] for m in r.json().get("data", [])}
    want = [c["model"] for k, c in config.SETTINGS["llm"]["providers"].items() if k.startswith("groq")]
    gone = [m for m in want if m not in have]
    return (OK, f"key valid; models {', '.join(want)} available") if not gone else \
        (WARN, f"key valid but Groq no longer offers {gone}; pick another in config/settings.yaml → llm")


def gemini():
    if not config.GEMINI_API_KEY:
        return WARN, "GEMINI_API_KEY not set (optional backup; step 3)"
    from worker import llm
    return OK, f"key valid; will use {llm.gemini_model()} (keep its project free of billing)"


def database():
    from worker.db import DB
    db = DB()
    n = db.one("select count(*) n from jobs")["n"]
    where = "Supabase/Postgres" if db.pg else f"local SQLite ({config.SQLITE_PATH})"
    beat = db.kv_get("worker_heartbeat")
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(beat)).total_seconds() if beat else None
    worker = f"worker heartbeat {int(age)}s ago" if age is not None and age < 120 else "worker not running"
    return (OK if db.pg else WARN), f"{where}: {n} jobs; {worker}" + ("" if db.pg else " (Supabase = step 7)")


def launchd():
    out = subprocess.run(["launchctl", "list"], capture_output=True, text=True).stdout
    return (OK, "background worker installed") if "com.internpilot.worker" in out else \
        (BAD, "run: ./scripts/install_launchd.sh (step 4)")


def gmail():
    if not config.GMAIL_CREDENTIALS.exists():
        return WARN, f"no {config.GMAIL_CREDENTIALS.relative_to(config.ROOT)} yet (step 5)"
    if not config.GMAIL_TOKEN.exists():
        return WARN, "credentials found; now run scripts/gmail_auth.py"
    from worker import gmail as g
    try:
        prof = g._execute(g.service().users().getProfile(userId="me"))
    except g.AuthExpired:
        return BAD, f"login expired; reconnect: {g.REAUTH}"
    import time as _t
    age = (_t.time() - config.GMAIL_TOKEN.stat().st_mtime) / 86400
    note = (f"; login renewed {age:.0f} day(s) ago (expires at 7 while the Google app is in Testing)"
            if config.SETTINGS["tracking"].get("gmail_app_in_testing", True) else "")
    return OK, f"authorized as {prof['emailAddress']}{note}"


def sending():
    return (OK, "DRY_RUN=1: approved emails are written to outbox/, nothing is sent") if config.DRY_RUN else \
        (WARN, "DRY_RUN=0: approved emails are really sent from your Gmail")


def dashboard():
    if not config.DASHBOARD_URL:
        return WARN, "DASHBOARD_URL not set (step 8); local dashboard: cd web && npm run dev"
    r = requests.get(config.DASHBOARD_URL, timeout=20, allow_redirects=False)
    if r.status_code in (200, 307, 308) and ("/login" in r.headers.get("location", "") or r.status_code == 200):
        return OK, f"{config.DASHBOARD_URL} is up and password-protected" if r.status_code != 200 else f"{config.DASHBOARD_URL} is up"
    if r.status_code == 503:
        return BAD, "deployed but DASHBOARD_PASSWORD isn't set in Vercel"
    return BAD, f"{config.DASHBOARD_URL} returned {r.status_code}"


def hunter():
    if not config.HUNTER_API_KEY:
        return SKIP, "not set (optional: real recruiter emails, free 25/month)"
    r = requests.get("https://api.hunter.io/v2/account", params={"api_key": config.HUNTER_API_KEY}, timeout=15)
    if r.status_code != 200:
        return BAD, f"key rejected ({r.status_code})"
    d = r.json()["data"]
    plan = d.get("plan_name", "?")
    left = (d.get("requests", {}).get("searches", {}) or {})
    return (OK if plan.lower() == "free" else WARN), f"plan {plan}, searches used {left.get('used', '?')}/{left.get('available', '?')}"


if __name__ == "__main__":
    os.chdir(config.ROOT)
    print("InternPilot doctor\n")
    for name, fn in [("Dependencies", deps), ("Profile", profile), (".env", env_file), ("Telegram", telegram),
                     ("Groq", groq), ("Gemini", gemini), ("Database", database), ("Background worker", launchd),
                     ("Gmail", gmail), ("Email sending", sending), ("Dashboard", dashboard), ("Hunter.io", hunter)]:
        check(name, fn)
    done = results.count(OK)
    print(f"\n{done}/{len(results)} ready. Cost: $0 (free tiers only).")

"""Tests run on SQLite by default. Set TEST_DATABASE_URL to a *local, throwaway* Postgres to run the same
tests against Postgres (what Supabase uses). The schema is dropped before each test, so remote URLs are refused."""
import os
import re

# Tests must never touch your real accounts: blank every secret BEFORE worker.config loads .env
# (python-dotenv never overrides variables that are already set).
for _var in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GROQ_API_KEY", "GEMINI_API_KEY", "HUNTER_API_KEY",
             "DATABASE_URL", "DASHBOARD_URL"):
    os.environ[_var] = ""
os.environ["GMAIL_TOKEN"] = "/nonexistent/internpilot-test-gmail-token.json"
os.environ["DRY_RUN"] = "1"
os.environ["OLLAMA_URL"] = "http://127.0.0.1:9"  # nothing listens here

import pytest  # noqa: E402

from worker import gmail as _gmail  # noqa: E402
from worker.db import DB  # noqa: E402

_REAL_GMAIL_AVAILABLE = _gmail.available

TEST_PG = os.getenv("TEST_DATABASE_URL", "")


def _local(url: str) -> bool:
    return bool(re.search(r"@(localhost|127\.0\.0\.1)[:/]|host=/", url))


@pytest.fixture(autouse=True)
def no_live_services(monkeypatch):
    """Belt and braces: fail loudly if any test tries a real Telegram / Groq / Gemini / Gmail call."""
    from worker import config, gmail
    assert not config.TELEGRAM_BOT_TOKEN and not config.GROQ_API_KEY and not config.GEMINI_API_KEY
    monkeypatch.setattr(gmail, "available", lambda: False)


@pytest.fixture
def real_gmail_state(monkeypatch):
    """Use the real token-file/expiry logic (tests pass their own temp token file)."""
    monkeypatch.setattr(_gmail, "available", _REAL_GMAIL_AVAILABLE)


@pytest.fixture
def make_db(tmp_path):
    def make() -> DB:
        if TEST_PG:
            assert _local(TEST_PG), "TEST_DATABASE_URL must point at a local throwaway Postgres (never Supabase)"
            import psycopg
            with psycopg.connect(TEST_PG, autocommit=True) as c:
                c.execute("drop schema if exists public cascade")
                c.execute("create schema public")
            return DB(url=TEST_PG)
        return DB(url="", sqlite_path=str(tmp_path / "t.db"))
    return make

"""Free-tier guard: fallback chain, daily caps, 429 handling, paid-plan detection, usage ledger."""
import pytest
import requests

from worker import llm
from worker.db import DB
from worker.notify import telegram


class Resp:
    def __init__(self, status=200, data=None, headers=None):
        self.status_code, self._data, self.headers, self.text = status, data or {}, headers or {}, str(data)

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(self.status_code)


def ok(text='{"score": 77}', tokens=1234, headers=None):
    return Resp(200, {"choices": [{"message": {"content": text}}], "usage": {"total_tokens": tokens}}, headers)


@pytest.fixture
def env(monkeypatch, tmp_path, make_db):
    monkeypatch.setattr(llm, "GROQ_API_KEY", "gsk_test")
    monkeypatch.setattr(llm, "GEMINI_API_KEY", "gem_test")
    monkeypatch.setattr(llm, "ollama_available", lambda: False)
    monkeypatch.setattr(llm, "_gemini_model", None)
    sent = []
    monkeypatch.setattr(telegram, "send", lambda text, buttons=None: sent.append(text) or True)
    db = make_db()
    monkeypatch.setattr(llm, "LEDGER", llm.Ledger())
    llm.use_db(db)
    calls = []

    def fake_post(url, **kw):
        calls.append((url, kw["json"]["model"]))
        return env.responses.pop(0)

    monkeypatch.setattr(llm.requests, "post", fake_post)
    monkeypatch.setattr(llm.requests, "get", lambda url, **kw: Resp(200, {"models": [
        {"name": "models/gemini-2.5-flash-lite", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.1-flash-lite", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.1-flash-lite-preview-09", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.1-pro", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]}]}))
    env.responses, env.calls, env.sent, env.db = [], calls, sent, db
    return env


def test_no_keys_means_no_llm(monkeypatch):
    monkeypatch.setattr(llm, "GROQ_API_KEY", "")
    monkeypatch.setattr(llm, "GEMINI_API_KEY", "")
    monkeypatch.setattr(llm, "ollama_available", lambda: False)
    assert llm.available("score") is None and llm.available("write") is None
    assert llm.chat_json("s", "u") is None


def test_purposes_use_the_right_models(env):
    env.responses += [ok(), ok()]
    assert llm.chat_json("s", "u", purpose="score") == {"score": 77}
    assert llm.last_provider == "groq_small"
    llm.chat_text("s", "u", purpose="write")
    assert [m for _, m in env.calls] == ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"]
    usage = env.db.kv_get(llm.Ledger.key())
    assert usage["groq_small"] == {"requests": 1, "tokens": 1234, "limited": False}


def test_429_marks_provider_and_falls_back_to_gemini(env):
    env.responses += [Resp(429, {"error": "rate limit"}), ok("hello from gemini")]
    assert llm.chat_text("s", "u", purpose="write") == "hello from gemini"
    assert llm.last_provider == "gemini"
    assert env.calls[1] == ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                            "gemini-3.1-flash-lite")           # newest stable Flash-Lite, preview/pro skipped
    assert llm.LEDGER.entry("groq_large")["limited"] is True
    env.responses += [ok("gemini again")]
    llm.chat_text("s", "u", purpose="write")                     # groq_large not retried today
    assert env.calls[-1][1] == "gemini-3.1-flash-lite"
    assert any("daily free cap reached" in t for t in env.sent)


def test_caps_stop_calls_before_free_limit(env, monkeypatch):
    monkeypatch.setitem(llm.CFG["providers"]["groq_small"], "max_requests_per_day", 2)
    env.responses += [ok(), ok()]
    llm.chat_json("s", "u", purpose="score")
    llm.chat_json("s", "u", purpose="score")
    assert llm.available("score") is None                       # score chain has no other free provider
    assert llm.chat_json("s", "u", purpose="score") is None      # → caller uses keyword scoring
    assert len(env.calls) == 2


def test_token_cap_counts_estimate(env, monkeypatch):
    monkeypatch.setitem(llm.CFG["providers"]["groq_large"], "max_tokens_per_day", 1000)
    env.responses += [ok("from gemini")]
    llm.chat_text("s", "x" * 8000, purpose="write")             # ~2.9k token estimate > 1k cap → skip groq_large
    assert llm.last_provider == "gemini"


def test_warns_at_80_percent_once(env, monkeypatch):
    monkeypatch.setitem(llm.CFG["providers"]["groq_small"], "max_requests_per_day", 5)
    env.responses += [ok() for _ in range(5)]
    for _ in range(5):
        llm.chat_json("s", "u", purpose="score")
    warns = [t for t in env.sent if "of today’s free cap used" in t]
    assert len(warns) == 1 and "$0" in warns[0]


def test_paid_plan_detection(env):
    env.responses += [ok(headers={"x-ratelimit-limit-requests": "300000"})]
    llm.chat_json("s", "u", purpose="score")
    assert any("paid plan" in t for t in env.sent)
    env.responses += [ok(headers={"x-ratelimit-limit-requests": "300000"})]
    llm.chat_json("s", "u", purpose="score")
    assert sum("paid plan" in t for t in env.sent) == 1


def test_free_plan_headers_are_quiet(env):
    env.responses += [ok(headers={"x-ratelimit-limit-requests": "14400"})]
    llm.chat_json("s", "u", purpose="score")
    assert not any("paid plan" in t for t in env.sent)

"""LLM access on FREE TIERS ONLY, with a usage ledger so you are never charged.

Two purposes, each with a fallback chain (settings.yaml → llm):
- "score": cheap, high-volume calls (job scoring, email classification, short summaries) → Groq small model
- "write": few, quality-sensitive calls (emails, resume rewording, prep packs) → Groq large → Gemini → ...

Every call is checked against self-imposed daily caps that sit well below each provider's free limits.
A 429 from a provider marks it exhausted for the rest of the day. When nothing is left, callers get None
and fall back to keyword scoring / templates, so the bot keeps working at $0.
"""
import json
import logging
import re
import time
from collections import deque
from datetime import datetime, timezone

import requests

from .config import GEMINI_API_KEY, GROQ_API_KEY, OLLAMA_EMBED_MODEL, OLLAMA_MODEL, OLLAMA_URL, SETTINGS

log = logging.getLogger(__name__)
CFG = SETTINGS["llm"]
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
# Groq's free-tier daily request limit (read from this account's response headers, Oct 2026). A much higher number
# in the headers means the account is on a paid plan; we warn so you can check billing.
GROQ_FREE_RPD = {"qwen/qwen3.8-27b": 1_000, "openai/gpt-oss-120b": 1_000, "openai/gpt-oss-20b": 1_000}
MAX_WAIT = 90           # seconds we'll wait out a per-minute rate limit before trying the next provider
_recent: dict[str, deque] = {}  # provider → (timestamp, tokens) of the last minute, for tokens-per-minute pacing

_ollama_up: bool | None = None
_gemini_model: str | None = None
last_provider: str | None = None  # which provider answered the most recent call (for labels like "scored by …")


# --------------------------------------------------------------------------- usage ledger
class Ledger:
    """Daily per-provider usage. In-memory by default; `use_db(db)` persists it to the kv table so the
    worker, the autofill process and the dashboard all see the same numbers."""

    def __init__(self):
        self.db = None
        self.mem: dict[str, dict] = {}

    @staticmethod
    def key(day: str | None = None) -> str:
        return f"llm_usage:{day or datetime.now(timezone.utc).date().isoformat()}"

    def today(self) -> dict:
        if self.db is not None:
            return self.db.kv_get(self.key(), {}) or {}
        return self.mem.setdefault(self.key(), {})

    def save(self, data: dict):
        if self.db is not None:
            self.db.kv_set(self.key(), data)
        else:
            self.mem[self.key()] = data

    def entry(self, provider: str) -> dict:
        return self.today().get(provider, {"requests": 0, "tokens": 0, "limited": False})

    def record(self, provider: str, tokens: int = 0, limited: bool = False):
        data = self.today()
        e = data.get(provider, {"requests": 0, "tokens": 0, "limited": False})
        if limited:
            e["limited"] = True
        else:
            e["requests"] += 1
            e["tokens"] += tokens
        data[provider] = e
        self.save(data)
        self._maybe_warn(provider, e)

    def _maybe_warn(self, provider: str, e: dict):
        caps = CFG["providers"].get(provider, {})
        frac = max(e["requests"] / caps["max_requests_per_day"] if caps.get("max_requests_per_day") else 0,
                   e["tokens"] / caps["max_tokens_per_day"] if caps.get("max_tokens_per_day") else 0)
        level = "limited" if e["limited"] or frac >= 1 else "warn" if frac >= CFG.get("warn_at", 0.8) else None
        if level and self.db is not None:
            flag = f"llm_warned:{self.key()}:{provider}:{level}"
            if not self.db.kv_get(flag):
                self.db.kv_set(flag, True)
                from .notify import telegram
                telegram.send(f"🧮 {provider}: {'daily free cap reached, using the fallback for today' if level == 'limited' else f'{frac:.0%} of today’s free cap used'}. Cost stays $0.")


LEDGER = Ledger()


def use_db(db):
    LEDGER.db = db
    # Publish caps + which providers are set up, for the dashboard's usage card.
    db.kv_set("llm_caps", {p: {k: v for k, v in c.items() if k.startswith("max_")} | {"configured": configured(p),
                               "model": c.get("model", "")} for p, c in CFG["providers"].items()})


def under_cap(provider: str, extra_tokens: int = 0) -> bool:
    caps = CFG["providers"].get(provider, {})
    e = LEDGER.entry(provider)
    if e["limited"]:
        return False
    if caps.get("max_requests_per_day") is not None and e["requests"] + 1 > caps["max_requests_per_day"]:
        return False
    if caps.get("max_tokens_per_day") is not None and e["tokens"] + extra_tokens > caps["max_tokens_per_day"]:
        return False
    return True


# --------------------------------------------------------------------------- providers
def ollama_available() -> bool:
    global _ollama_up
    if _ollama_up is None:
        try:
            tags = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2).json()
            names = {m["name"] for m in tags.get("models", [])}
            _ollama_up = any(n.startswith(OLLAMA_MODEL.split(":")[0]) for n in names)
        except requests.RequestException:
            _ollama_up = False
    return _ollama_up


def configured(provider: str) -> bool:
    if provider.startswith("groq"):
        return bool(GROQ_API_KEY)
    if provider == "gemini":
        return bool(GEMINI_API_KEY)
    if provider == "ollama":
        return ollama_available()
    return False


def chain(purpose: str) -> list[str]:
    return [p for p in CFG[f"{purpose}_chain"] if configured(p)]


def available(purpose: str = "write") -> str | None:
    """First provider for this purpose that is configured and still under today's free cap."""
    return next((p for p in chain(purpose) if under_cap(p)), None)


def gemini_model() -> str:
    """Configured model, or auto-pick the newest stable Flash-Lite (the most generous free Gemini tier)."""
    global _gemini_model
    want = CFG["providers"]["gemini"].get("model", "auto")
    if want != "auto":
        return want
    if _gemini_model is None:
        r = requests.get(f"{GEMINI_BASE}/models", headers={"x-goog-api-key": GEMINI_API_KEY}, timeout=20,
                         params={"pageSize": 200})
        r.raise_for_status()
        names = [m["name"].split("/", 1)[1] for m in r.json().get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
        skip = r"preview|exp|tts|image|live|audio|latest|omni"
        lite = [n for n in names if "flash-lite" in n and not re.search(skip, n)]
        pool = lite or [n for n in names if "flash" in n and not re.search(skip, n)]
        if not pool:
            raise RuntimeError("no free-tier Gemini Flash model found")

        def version(n: str):
            return [(0, int(x)) if x.isdigit() else (1, x) for x in re.split(r"[.-]", n)]

        _gemini_model = max(pool, key=version)
        log.info("gemini model: %s", _gemini_model)
    return _gemini_model


class RateLimited(Exception):
    def __init__(self, msg: str, retry_after: float | None = None):
        super().__init__(msg)
        self.retry_after = retry_after


def _pace(provider: str, tokens: int):
    """Stay under the provider's tokens-per-minute limit by waiting (at most a minute) before the call."""
    tpm = CFG["providers"].get(provider, {}).get("tokens_per_minute")
    if not tpm:
        return
    q = _recent.setdefault(provider, deque())
    while True:
        now = time.monotonic()
        while q and now - q[0][0] > 60:
            q.popleft()
        if sum(t for _, t in q) + tokens <= tpm or not q:
            return
        time.sleep(min(60.5 - (now - q[0][0]), 61))


def _note_tokens(provider: str, tokens: int):
    _recent.setdefault(provider, deque()).append((time.monotonic(), tokens))


def _openai_compat(url: str, key: str, model: str, messages, as_json: bool, temperature: float, max_tokens: int,
                   timeout: int, extra: dict | None = None):
    body = {"model": model, "temperature": temperature, "messages": messages, "max_tokens": max_tokens, **(extra or {})}
    if as_json:
        body["response_format"] = {"type": "json_object"}
    r = requests.post(url, timeout=timeout, headers={"Authorization": f"Bearer {key}"}, json=body)
    if r.status_code == 429:
        try:
            wait = float(r.headers.get("retry-after", ""))
        except ValueError:
            wait = None
        raise RateLimited(r.text[:200], wait)
    if r.status_code >= 400:
        from .logsafe import redact
        raise requests.HTTPError(f"{r.status_code}: {redact(r.text[:300])}")
    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"], int((data.get("usage") or {}).get("total_tokens") or 0), r.headers


def _call(provider: str, messages, as_json: bool, temperature: float, max_tokens: int, timeout: int):
    """Returns (text, tokens_used)."""
    if provider.startswith("groq"):
        cfg = CFG["providers"][provider]
        model = cfg["model"]
        extra = {"reasoning_effort": cfg["reasoning_effort"]} if cfg.get("reasoning_effort") else None
        text, tokens, headers = _openai_compat("https://api.groq.com/openai/v1/chat/completions", GROQ_API_KEY, model,
                                               messages, as_json, temperature, max_tokens, timeout, extra)
        _check_groq_plan(model, headers)
        return text, tokens
    if provider == "gemini":
        text, tokens, _ = _openai_compat(f"{GEMINI_BASE}/openai/chat/completions", GEMINI_API_KEY, gemini_model(),
                                         messages, as_json, temperature, max_tokens, timeout)
        return text, tokens
    if provider == "ollama":
        body = {"model": OLLAMA_MODEL, "stream": False, "messages": messages,
                "options": {"temperature": temperature, "num_ctx": 8192, "num_predict": max_tokens}}
        if as_json:
            body["format"] = "json"
        r = requests.post(f"{OLLAMA_URL}/api/chat", timeout=timeout, json=body)
        r.raise_for_status()
        d = r.json()
        return d["message"]["content"], int(d.get("prompt_eval_count", 0)) + int(d.get("eval_count", 0))
    raise ValueError(provider)


def _check_groq_plan(model: str, headers):
    """Free-tier guard: Groq reports the account's daily request limit on every response."""
    try:
        limit = int(headers.get("x-ratelimit-limit-requests", 0))
    except (TypeError, ValueError):
        return
    free = GROQ_FREE_RPD.get(model)
    if free and limit > free * 2 and LEDGER.db is not None and not LEDGER.db.kv_get("groq_paid_warned"):
        LEDGER.db.kv_set("groq_paid_warned", True)
        from .notify import telegram
        telegram.send(f"⚠️ Groq reports {limit} requests/day for {model} (free tier is {free}). Your Groq account may be "
                      f"on a paid plan. Check console.groq.com/settings/billing and remove any payment method.")


def _chat(system: str, user: str, purpose: str, as_json: bool, temperature: float, timeout: int) -> str | None:
    global last_provider
    if as_json and "json" not in (system + user).lower():
        system += "\nRespond with a single JSON object."
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    max_tokens = CFG["max_output_tokens"][purpose]
    estimate = (len(system) + len(user)) // 4 + max_tokens
    for provider in chain(purpose):
        if not under_cap(provider, estimate):
            continue
        text = None
        for attempt in range(2):
            _pace(provider, estimate)
            try:
                text, tokens = _call(provider, messages, as_json, temperature, max_tokens, timeout)
                break
            except RateLimited as e:
                if attempt == 0 and e.retry_after is not None and e.retry_after <= MAX_WAIT:
                    log.info("%s per-minute limit, waiting %.0fs", provider, e.retry_after)
                    time.sleep(e.retry_after + 1)
                    continue
                log.warning("%s rate-limited (daily limit or long wait), skipping it for today: %s", provider, e)
                LEDGER.record(provider, limited=True)
                break
            except (requests.RequestException, ValueError, KeyError, RuntimeError) as e:
                log.warning("LLM call failed (%s): %s", provider, e)
                break
        if text is None:
            continue
        _note_tokens(provider, tokens or estimate)
        LEDGER.record(provider, tokens or estimate)
        last_provider = provider
        return text
    return None


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    return json.loads(match.group(0) if match else text)


def chat_json(system: str, user: str, purpose: str = "write", timeout: int = 180) -> dict | None:
    """Ask for a JSON object. None when no free LLM is available or the reply isn't valid JSON."""
    text = _chat(system, user, purpose, as_json=True, temperature=0.2, timeout=timeout)
    if text is None:
        return None
    try:
        out = _extract_json(text)
    except ValueError as e:
        log.warning("LLM returned invalid JSON: %s", e)
        return None
    return out if isinstance(out, dict) else None


def chat_text(system: str, user: str, purpose: str = "write", temperature: float = 0.5, timeout: int = 180) -> str | None:
    """Free-text completion (emails, prep notes). None when no free LLM is available."""
    text = _chat(system, user, purpose, as_json=False, temperature=temperature, timeout=timeout)
    return text.strip() if text else None


def embed(texts: list[str]) -> list[list[float]] | None:
    """Local Ollama embeddings if installed (free, unlimited), else None → bag-of-words similarity."""
    if not ollama_available():
        return None
    try:
        r = requests.post(f"{OLLAMA_URL}/api/embed", timeout=120,
                          json={"model": OLLAMA_EMBED_MODEL, "input": [t[:6000] for t in texts]})
        r.raise_for_status()
        return r.json()["embeddings"]
    except (requests.RequestException, KeyError) as e:
        log.warning("embedding failed: %s", e)
        return None

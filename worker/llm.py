"""One LLM entry point: local Ollama first, Groq fallback, None if neither is reachable
(callers then use the heuristic path, so the pipeline always runs)."""
import json
import logging
import re

import requests

from .config import GROQ_API_KEY, GROQ_MODEL, OLLAMA_EMBED_MODEL, OLLAMA_MODEL, OLLAMA_URL

log = logging.getLogger(__name__)
_ollama_up: bool | None = None


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


def available() -> str | None:
    if ollama_available():
        return "ollama"
    if GROQ_API_KEY:
        return "groq"
    return None


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    return json.loads(match.group(0) if match else text)


def _chat(system: str, user: str, as_json: bool, temperature: float, timeout: int) -> str | None:
    backend = available()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        if backend == "ollama":
            body = {"model": OLLAMA_MODEL, "stream": False, "messages": messages,
                    "options": {"temperature": temperature, "num_ctx": 8192}}
            if as_json:
                body["format"] = "json"
            r = requests.post(f"{OLLAMA_URL}/api/chat", timeout=timeout, json=body)
            r.raise_for_status()
            return r.json()["message"]["content"]
        if backend == "groq":
            body = {"model": GROQ_MODEL, "temperature": temperature, "messages": messages}
            if as_json:
                body["response_format"] = {"type": "json_object"}
            r = requests.post("https://api.groq.com/openai/v1/chat/completions", timeout=timeout,
                              headers={"Authorization": f"Bearer {GROQ_API_KEY}"}, json=body)
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    except (requests.RequestException, ValueError, KeyError) as e:
        log.warning("LLM call failed (%s): %s", backend, e)
    return None


def chat_json(system: str, user: str, timeout: int = 180) -> dict | None:
    """Ask for a JSON object. Returns None when no LLM is available or the reply isn't valid JSON."""
    text = _chat(system, user, as_json=True, temperature=0.2, timeout=timeout)
    if text is None:
        return None
    try:
        out = _extract_json(text)
    except ValueError as e:
        log.warning("LLM returned invalid JSON: %s", e)
        return None
    return out if isinstance(out, dict) else None


def chat_text(system: str, user: str, temperature: float = 0.5, timeout: int = 180) -> str | None:
    """Free-text completion (emails, prep notes). None when no LLM is available."""
    text = _chat(system, user, as_json=False, temperature=temperature, timeout=timeout)
    return text.strip() if text else None


def embed(texts: list[str]) -> list[list[float]] | None:
    """Ollama embeddings, or None (caller falls back to bag-of-words)."""
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

"""Never write secrets to logs. Error messages from HTTP libraries include full request URLs (Telegram puts the bot
token in the URL), so every log line goes through `redact` before it reaches a file."""
import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

PATTERNS = [
    (re.compile(r"bot\d{6,}:[A-Za-z0-9_-]{20,}"), "bot<redacted>"),                 # Telegram bot token
    (re.compile(r"gsk_[A-Za-z0-9]{10,}"), "gsk_<redacted>"),                        # Groq key
    (re.compile(r"AIza[0-9A-Za-z_-]{20,}"), "AIza<redacted>"),                      # Google API key
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]{10,}"), r"\1<redacted>"),        # Authorization headers
    (re.compile(r"(?i)((?:api_key|key|token|access_token|refresh_token|client_secret)=)[^&\s'\"]+"), r"\1<redacted>"),
    (re.compile(r"(postgres(?:ql)?://[^:/@\s]+:)[^@\s]+@"), r"\1<redacted>@"),      # DB password in URLs
    (re.compile(r"ya29\.[A-Za-z0-9_-]{10,}"), "ya29.<redacted>"),                   # Google OAuth access token
    (re.compile(r"1//[0-9A-Za-z_-]{20,}"), "1//<redacted>"),                        # Google OAuth refresh token
]


def redact(text: str) -> str:
    for pattern, repl in PATTERNS:
        text = pattern.sub(repl, text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def setup(log_file: Path | None = None, level: int = logging.INFO):
    """Configure logging for a worker process: redacted, and rotated (5 MB × 3) when writing to a file."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file:
        log_file.parent.mkdir(mode=0o700, exist_ok=True)
        handlers = [RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3)]
        log_file.chmod(0o600)
    for h in handlers:
        h.setFormatter(RedactingFormatter(FORMAT))
    logging.basicConfig(level=level, handlers=handlers, force=True)
    logging.getLogger("JobSpy").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)

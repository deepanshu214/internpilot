import hashlib
import html
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean_html(text: str) -> str:
    """Greenhouse returns HTML-escaped HTML; unescape twice, drop tags, squash whitespace."""
    if not text:
        return ""
    text = html.unescape(html.unescape(text))
    text = _TAG.sub(" ", text)
    return _WS.sub(" ", text).strip()


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


@dataclass
class Job:
    source: str
    company: str
    title: str
    location: str
    url: str
    jd_text: str = ""
    posted_at: datetime | None = None
    remote: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        # Same role reposted on two boards (e.g. LinkedIn + Greenhouse) collapses to one row.
        key = f"{_norm(self.company)}|{_norm(self.title)}|{_norm(self.location)}"
        return hashlib.sha1(key.encode()).hexdigest()[:16]


def from_epoch(value) -> datetime | None:
    if value in (None, ""):
        return None
    value = float(value)
    if value > 1e12:  # milliseconds
        value /= 1000
    return datetime.fromtimestamp(value, tz=timezone.utc)


def from_iso(value) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

import re
from datetime import datetime, timedelta, timezone

from .config import SETTINGS
from .models import Job


def _has_any(text: str, words) -> bool:
    t = f" {text.lower()} "
    return any(w.lower() in t for w in words)


def _has_word(text: str, words) -> bool:
    # whole words, so "intern" doesn't match "Internal Tools Engineer"
    return any(re.search(rf"(?<![a-z]){re.escape(w.lower())}(?![a-z])", text.lower()) for w in words)


def title_ok(title: str, settings=SETTINGS) -> bool:
    if _has_any(title, settings["title_exclude"]):
        return False
    include = settings["title_include"] if settings["mode"] == "internship" else settings["job_mode_include"]
    return _has_word(title, include)


_GENERIC_REMOTE = re.compile(r"\b(remote|anywhere|worldwide|global|hybrid|wfh|work from home|in|or|and)\b|[^a-z]")


def location_ok(job: Job, settings=SETTINGS) -> bool:
    loc = (job.location or "").lower()
    if settings.get("allow_any_location") or _has_any(loc, settings["locations"]):
        return True
    # Remote with no country attached ("Remote", "Anywhere") is fine; "Remote in USA" is not.
    return (job.remote or "remote" in loc or not loc) and not _GENERIC_REMOTE.sub("", loc)


def fresh_ok(job: Job, settings=SETTINGS) -> bool:
    if not job.posted_at:
        return True
    return job.posted_at >= datetime.now(timezone.utc) - timedelta(days=settings["max_age_days"])


def keep(job: Job, settings=SETTINGS) -> bool:
    if job.extra.get("is_internship") and settings["mode"] == "internship":
        role_ok = not _has_any(job.title, settings["title_exclude"])
    else:
        role_ok = title_ok(job.title, settings)
    return role_ok and location_ok(job, settings) and fresh_ok(job, settings)

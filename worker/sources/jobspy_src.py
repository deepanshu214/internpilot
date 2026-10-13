"""LinkedIn / Indeed / Naukri via python-jobspy, which uses their public (logged-out) job search.
Your LinkedIn account is never touched."""
import html
import logging
from datetime import datetime, time, timezone

from ..models import Job

log = logging.getLogger(__name__)


def _posted(value):
    if value is None or value != value:  # None or NaN
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        return datetime.combine(value, time(), tzinfo=timezone.utc)
    except TypeError:
        return None


def _s(v) -> str:
    return "" if v is None or v != v else html.unescape(str(v)).strip()


def jobspy(cfg: dict) -> list[Job]:
    from jobspy import scrape_jobs

    jobs = []
    for term in cfg["search_terms"]:
        try:
            df = scrape_jobs(site_name=cfg["sites"], search_term=term, location=cfg["location"],
                             results_wanted=cfg["results_wanted"], hours_old=cfg["hours_old"],
                             country_indeed=cfg["location"], linkedin_fetch_description=True, verbose=0,
                             google_search_term=f"{term} jobs near {cfg['location']} since 3 days ago")
        except Exception as e:  # jobspy raises many site-specific errors; one bad site shouldn't stop the run
            log.warning("jobspy '%s' failed: %s", term, e)
            continue
        for row in df.to_dict("records"):
            jobs.append(Job(
                source=f"jobspy:{_s(row.get('site'))}", company=_s(row.get("company")), title=_s(row.get("title")),
                location=_s(row.get("location")), url=_s(row.get("job_url")), jd_text=_s(row.get("description")),
                posted_at=_posted(row.get("date_posted")), remote=bool(row.get("is_remote") is True)))
    return jobs

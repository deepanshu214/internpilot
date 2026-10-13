import logging
from concurrent.futures import ThreadPoolExecutor

from ..config import SETTINGS, WATCHLIST
from ..models import Job
from .ats import FETCHERS
from .bigtech import amazon, workday
from .gmail_alerts import gmail_alerts
from .india import internshala, unstop
from .jobspy_src import jobspy
from .remote_boards import hn_hiring, remoteok, remotive
from .simplify import simplify

log = logging.getLogger(__name__)


def fetch_all(settings=SETTINGS, watchlist=WATCHLIST) -> tuple[list[Job], dict]:
    """Run every source in parallel. Returns (jobs, per-source counts); failures are logged, not raised."""
    tasks = {f"{ats}:{slug}": (FETCHERS[ats], slug) for ats in FETCHERS for slug in watchlist.get(ats) or []}
    if settings["simplify"]["enabled"]:
        tasks["simplify"] = (simplify, settings["simplify"]["url"])
    if settings["jobspy"]["enabled"]:
        tasks["jobspy"] = (jobspy, settings["jobspy"])
    for entry in watchlist.get("workday") or []:
        tasks[f"workday:{entry['tenant']}"] = (workday, entry)
    src = settings.get("sources", {})
    if src.get("internshala"):
        tasks["internshala"] = (internshala, src["internshala"])
    if src.get("unstop"):
        tasks["unstop"] = (unstop, src["unstop"])
    if src.get("amazon"):
        tasks["amazon"] = (amazon, src["amazon"])
    if src.get("gmail_alerts", True):
        tasks["gmail_alerts"] = (lambda _: gmail_alerts(), None)  # no-op until Gmail is authorized
    for name, fn in (("remotive", remotive), ("remoteok", remoteok), ("hn", hn_hiring)):
        if src.get(name):
            tasks[name] = (lambda _, f=fn: f(), None)

    jobs, counts = [], {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {name: pool.submit(fn, arg) for name, (fn, arg) in tasks.items()}
        for name, fut in futures.items():
            try:
                found = fut.result()
            except Exception as e:
                log.warning("source %s failed: %s", name, e)
                counts[name] = -1
                continue
            counts[name] = len(found)
            jobs.extend(found)
    return jobs, counts

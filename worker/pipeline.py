import logging

from . import filters, llm
from .config import SETTINGS
from .db import DB
from .match.score import score_jobs
from .notify import telegram
from .sources import fetch_all

log = logging.getLogger(__name__)


def run_once(db: DB | None = None, settings=SETTINGS) -> dict:
    db = db or DB()
    fetched, counts = fetch_all(settings)
    kept = [j for j in fetched if j.title and j.url and filters.keep(j, settings)]

    unique = {}
    for j in kept:  # dedup within this batch (same role on several boards)
        unique.setdefault(j.id, j)
    seen = db.existing_ids(list(unique))
    new_jobs = [j for jid, j in unique.items() if jid not in seen]
    log.info("fetched %d, kept %d, unique %d, new %d (llm: %s)",
             len(fetched), len(kept), len(unique), len(new_jobs), llm.available() or "none")

    for r in score_jobs(new_jobs, settings):
        db.insert_job(r["job"], r["embedding"])
        db.upsert_match(r["job"].id, r["score"], r["reasons"], r["missing"], r["method"],
                        deadline=r["job"].extra.get("deadline"))

    cfg = settings["match"]
    sent = []
    for row in db.pending_alerts(cfg["alert_threshold"], cfg["max_alerts_per_run"]):
        if telegram.alert(row):
            sent.append(row["id"])
    db.mark_notified(sent)

    summary = {"fetched": len(fetched), "kept": len(kept), "new": len(new_jobs), "alerted": len(sent),
               "failed_sources": [k for k, v in counts.items() if v < 0]}
    db.log("run", str(summary))
    db.kv_set("last_discover", summary)
    return summary


def run_task(db: DB, task: dict) -> dict:
    return run_once(db)

"""Task queue: the dashboard and Telegram buttons insert rows into `tasks`; the worker on your Mac runs them."""
import importlib
import json
import logging
import traceback

from .config import DASHBOARD_URL
from .db import DB, now
from .notify import telegram

log = logging.getLogger(__name__)

HANDLERS = {
    "discover": "worker.pipeline:run_task",
    "tailor": "worker.tailor.service:run_task",
    "find_contacts": "worker.outreach.contacts:run_task",
    "draft_outreach": "worker.outreach.draft:run_task",
    "send_outreach": "worker.outreach.send:run_task",
    "autofill": "worker.apply.autofill:run_task",
    "prep": "worker.docs:run_task",
    "cover_letter": "worker.docs:run_task",
    "referral": "worker.docs:run_task",
    "prepare": "worker.tasks:prepare_task",
}


def _handler(kind: str):
    module, func = HANDLERS[kind].split(":")
    return getattr(importlib.import_module(module), func)


def prepare(db: DB, job_id: str) -> list[str]:
    """'Shortlist' = get everything ready for review: tailored resume, contacts, email drafts."""
    db.set_status(job_id, "shortlisted")
    return [db.enqueue(kind, job_id) for kind in ("tailor", "find_contacts", "draft_outreach")]


def prepare_task(db: DB, task: dict) -> dict:
    return {"queued": prepare(db, task["job_id"])}


def _notify(db: DB, task: dict, result: dict):
    kind, job_id = task["kind"], task.get("job_id")
    job = db.get("jobs", job_id) if job_id else None
    where = f"{job['title']} @ {job['company']}" if job else ""
    link = f"\n{DASHBOARD_URL}/jobs/{job_id}" if DASHBOARD_URL and job_id else ""
    if kind == "draft_outreach" and result.get("drafts"):
        telegram.send(f"📝 {len(result['drafts'])} email draft(s) ready for {where}. Review & approve.{link}")
    elif kind == "send_outreach":
        telegram.send(f"✅ {'(dry run) ' if result.get('dry_run') else ''}Email sent for {where}.{link}")
    elif kind in ("prep", "cover_letter", "referral"):
        telegram.send(f"📄 {kind.replace('_', ' ').title()} ready for {where}.{link}")


def run_one(db: DB) -> dict | None:
    task = db.next_task()
    if not task:
        return None
    try:
        result = _handler(task["kind"])(db, task) or {}
        db.update("tasks", task["id"], {"status": "done", "result": json.dumps(result, default=str),
                                        "finished_at": now()})
        _notify(db, task, result)
        task["status"], task["result"] = "done", result
    except Exception as e:
        log.warning("task %s %s failed: %s", task["kind"], task["id"], e)
        db.update("tasks", task["id"], {"status": "failed", "error": f"{type(e).__name__}: {e}",
                                        "finished_at": now()})
        db.log("task-failed", f"{task['kind']}: {e}\n{traceback.format_exc(limit=3)}", task.get("job_id"))
        if type(e).__name__ != "NotAllowed":
            telegram.send(f"⚠️ {task['kind']} failed: {e}")
        task["status"], task["error"] = "failed", str(e)
    return task


def run_pending(db: DB, limit: int = 20) -> int:
    n = 0
    while n < limit and run_one(db):
        n += 1
    return n

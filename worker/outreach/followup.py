"""One polite follow-up per cold email when there's no reply after N days. Created as a draft for you to approve."""
from datetime import datetime, timezone

from .. import gmail
from ..config import DRY_RUN, PROFILE
from ..db import DB, now
from ..notify import telegram


def followup_body(o: dict, contact: dict | None) -> str:
    name = (contact or {}).get("name")
    greet = f"Hi {name.split()[0]}," if name else "Hi,"
    return (f"{greet}\n\nJust following up on my note below about the internship. I'd still love to learn whether "
            f"my background could be a fit. Happy to share anything else that would help.\n\n"
            f"Thanks for your time,\n{PROFILE['name']}")


def has_reply(o: dict) -> bool:
    if DRY_RUN or not gmail.available() or not o.get("gmail_thread_id") or o["gmail_thread_id"].startswith("dryrun"):
        return False
    return gmail.thread_message_count(o["gmail_thread_id"]) > 1


def run(db: DB) -> dict:
    due = db.query("select * from outreach where kind = 'cold' and status = 'sent' and followup_due is not null"
                   " and followup_due <= ?", (datetime.now(timezone.utc).isoformat(timespec="seconds"),))
    created, replied = 0, 0
    for o in due:
        if has_reply(o):
            db.update("outreach", o["id"], {"status": "replied", "updated_at": now()})
            replied += 1
            continue
        if db.one("select id from outreach where parent_id = ? and kind = 'followup'", (o["id"],)):
            continue
        contact = db.get("contacts", o["contact_id"]) if o.get("contact_id") else None
        subject = o["subject"] if o["subject"].lower().startswith("re:") else f"Re: {o['subject']}"
        db.insert("outreach", {"contact_id": o.get("contact_id"), "job_id": o.get("job_id"), "kind": "followup",
                               "parent_id": o["id"], "variant": o.get("variant"), "project_pitched": o.get("project_pitched"),
                               "subject": subject, "body": followup_body(o, contact), "to_email": o["to_email"],
                               "status": "draft", "created_at": now(), "updated_at": now()})
        db.update("outreach", o["id"], {"followup_due": None, "updated_at": now()})
        created += 1
    if created:
        telegram.send(f"✉️ {created} follow-up draft(s) ready. Approve them in the dashboard.")
    return {"followup_drafts": created, "marked_replied": replied}

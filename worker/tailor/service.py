"""Tailor a resume for one job: select → validate → render (one page) → store PDF in DB + output/resumes/."""
import base64
import re

from ..config import OUTPUT_DIR, PROFILE
from ..db import DB, now
from .render import render_one_page
from .select import select
from .validate import validate_selection


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40]


def diff_summary(sel: dict) -> str:
    master_projects = [p["name"] for p in PROFILE["projects"]]
    lines = [f"Projects: {', '.join(p['name'].split(' — ')[0] for p in sel['projects'])}"]
    dropped = [n.split(" — ")[0] for n in master_projects if n not in {p["name"] for p in sel["projects"]}]
    if dropped:
        lines.append(f"Left out: {', '.join(dropped)}")
    if sel.get("keywords"):
        lines.append(f"JD keywords you have (moved to the front of skills): {', '.join(sel['keywords'][:12])}")
    lines.append(f"Bullets rephrased: {len(sel.get('rephrased', []))}, rewrites rejected by validator: "
                 f"{len(sel.get('rejected', []))}")
    lines.append(f"Method: {sel.get('method', 'heuristic')}")
    return "\n".join(lines)


def tailor(db: DB, job_id: str) -> dict:
    job = db.job_with_match(job_id)
    if not job:
        raise ValueError(f"unknown job {job_id}")
    jd = f"{job['title']} at {job['company']}. {job.get('jd_text') or ''}"
    sel = select(jd, title=job["title"])
    problems = validate_selection(sel)
    if problems:  # should never happen (select already validates); refuse rather than render a fabricated resume
        raise ValueError("selection failed validation: " + "; ".join(problems))
    pdf, sel = render_one_page(sel)

    version = (db.one("select max(version) v from resumes where job_id = ?", (job_id,)) or {}).get("v") or 0
    path = OUTPUT_DIR / "resumes" / f"{_slug(PROFILE['name'])}-{_slug(job['company'])}-{_slug(job['title'])}-v{version + 1}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pdf)
    row = db.insert("resumes", {
        "job_id": job_id, "version": version + 1, "pdf_b64": base64.b64encode(pdf).decode(),
        "selection": sel, "keywords": sel.get("keywords", []), "diff_summary": diff_summary(sel), "created_at": now(),
    })
    if job.get("status") in (None, "new", "shortlisted"):
        db.set_status(job_id, "tailored")
    db.log("tailor", f"resume v{version + 1} ({sel.get('method')})", job_id)
    return {"resume_id": row["id"], "version": version + 1, "path": str(path), "diff": row["diff_summary"]}


def latest_resume(db: DB, job_id: str) -> dict | None:
    return db.one("select * from resumes where job_id = ? order by version desc limit 1", (job_id,))


def resume_attachment(db: DB, job_id: str) -> tuple[str, bytes]:
    """(filename, bytes) of the newest tailored resume, tailoring one if none exists yet."""
    r = latest_resume(db, job_id)
    if not r:
        tailor(db, job_id)
        r = latest_resume(db, job_id)
    return f"{PROFILE['name'].replace(' ', '_')}_Resume.pdf", base64.b64decode(r["pdf_b64"])


def run_task(db: DB, task: dict) -> dict:
    return tailor(db, task["job_id"])


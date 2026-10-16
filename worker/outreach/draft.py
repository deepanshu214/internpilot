"""Write a short, specific cold email for one job + contact. Drafts only: nothing is sent until you approve it."""
import json
import re
from datetime import datetime

from .. import llm
from ..config import PROFILE, SETTINGS
from ..db import DB, now
from ..tailor.select import heuristic_selection
from ..tailor.validate import ALL_SKILLS
from ..match.skills import find_skills
from .company import company_brief, find_domain

PLACEHOLDER = re.compile(r"\[[^\]]*\]|\{[^}]*\}|<[^>]+>|\bXX+\b|lorem", re.I)


def pick_project(job: dict) -> dict:
    """The profile project most relevant to this job (same ranking the resume tailor uses)."""
    sel = heuristic_selection(f"{job['title']} {job.get('jd_text') or ''}", max_projects=len(PROFILE["projects"]),
                              title=job["title"])
    pitchable = {p["name"]: p for p in PROFILE["projects"] if p.get("outreach", True)}
    name = next(e["name"] for e in sel["projects"] if e["name"] in pitchable)
    return pitchable[name]


def first_name(contact: dict | None) -> str | None:
    name = (contact or {}).get("name") or ""
    return name.split()[0].title() if name.strip() else None


def short_role(title: str) -> str:
    return re.sub(r"\s*[\(\[].*?[\)\]]\s*", " ", title).strip()[:70]


def signature() -> str:
    p = PROFILE
    links = " | ".join(v for v in [p["links"].get("github"), p["links"].get("linkedin")] if v)
    return f"Best,\n{p['name']}\n{p['phone']}" + (f"\n{links}" if links else "")


COMPANY_SUFFIX = re.compile(r"[,.]?\s+(inc|llc|ltd|limited|pvt|private|corp|corporation|co)\b\.?", re.I)


def display_company(name: str) -> str:
    """'Pharmatek Solutions Inc.' → 'Pharmatek Solutions', 'Acme Pvt. Ltd.' → 'Acme'."""
    out = name
    while (new := COMPANY_SUFFIX.sub("", out).strip()) != out:
        out = new
    return out or name


def study_year(grad_year: int, today=None) -> int:
    today = today or datetime.now()
    academic_year_end = today.year + (1 if today.month >= 7 else 0)
    return max(1, min(4, 4 - (grad_year - academic_year_end)))


ORDINAL = {1: "first", 2: "second", 3: "third", 4: "final"}


def facts(job: dict, project: dict, brief: str) -> dict:
    p = PROFILE
    exp = p["experience"][0] if p["experience"] else None
    short = p.get("short") or {}
    year = ORDINAL[study_year(p["grad_year"])]
    gpa = f" (GPA {short['gpa']})" if short.get("gpa") else ""
    jd_skills = find_skills(f"{job['title']} {job.get('jd_text') or ''}", ALL_SKILLS)
    return {
        "me": f"{year}-year {short.get('degree', p['degree'])} student at {short.get('school', p['education'][0]['school'])}{gpa}",
        "project_skills_in_jd": sorted(jd_skills & find_skills(" ".join(project["stack"] + project["bullets"]), ALL_SKILLS)),
        "recent_experience": f"{'an' if exp['role'][0].lower() in 'aeiou' else 'a'} {exp['role']} at {exp['org']}" if exp else "",
        "project": {"name": project["name"].split(" — ")[0], "pitch": project["pitch"], "stack": project["stack"],
                    "url": project.get("url") or ""},
        "role": short_role(job["title"]), "company": display_company(job["company"]), "company_brief": brief,
    }


def template_email(job: dict, project: dict, contact: dict | None, brief: str, variant: str) -> tuple[str, str]:
    f = facts(job, project, brief)
    company, proj = f["company"], f["project"]
    greet = f"Hi {first_name(contact)}," if first_name(contact) else f"Hi {company} team,"
    link = f" ({proj['url']})" if proj["url"] else ""
    if brief:
        hook = (f"{company} caught my eye: {brief[0].lower() + brief[1:].rstrip('.')}. "
                f"I'm applying for the {f['role']} role and wanted to reach out directly.")
    else:
        hook = f"I came across the {f['role']} opening at {company} and wanted to reach out directly."
    overlap = f["project_skills_in_jd"]
    fit = (f"It uses {_join(overlap[:3])}, which this role also calls for." if overlap
           else f"It's built with {_join(proj['stack'][:3])}.")
    pitch = proj["pitch"][0].lower() + proj["pitch"][1:]
    body = (f"{greet}\n\n{hook}\n\n"
            f"I recently built {proj['name']}{link}, {pitch} {fit}\n\n"
            f"I'm a {f['me']}"
            + (f" and recently worked as {f['recent_experience']}." if f["recent_experience"] else ".")
            + " I've attached my resume.\n\n"
            f"Would you be open to a 15-minute chat, or could you point me to the right person for this role?\n\n"
            f"{signature()}")
    school = (PROFILE.get("short") or {}).get("school", PROFILE["education"][0]["school"].split(",")[0])
    subject = (f"{proj['name']} → {f['role']} at {company}" if variant == "A"
               else f"{f['role']} application: {school} CSE '{str(PROFILE['grad_year'])[-2:]}")
    return subject[:120], body


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1] if items else ""


SYSTEM = """You write cold emails from a CS student to a recruiter or engineer at a company, about an internship.
Hard rules:
- {lo}-{hi} words in the body (excluding the signature). Plain text. No markdown, no emojis, no placeholders.
- Use ONLY the facts given. Never invent metrics, technologies, experience, mutual connections or praise you can't back up.
- Structure: greeting; one specific line about what the company builds (from company_brief); 1-2 lines on the
  project and why it is relevant to this role (include the project URL if given); one line on background;
  one clear ask (15-minute chat or pointer to the right person); mention the resume is attached.
- Confident, warm, concise. Not desperate, not generic.
Return JSON: {{"subject": "max 9 words", "body": "email body WITHOUT signature"}}"""


def check_email(subject: str, body: str, f: dict, lo: int, hi: int) -> str | None:
    words = len(body.split())
    if not lo - 15 <= words <= hi + 25:
        return f"length {words} words"
    if PLACEHOLDER.search(subject + " " + body):
        return "placeholder text"
    if f["company"].strip() and f["company"].lower().split()[0] not in body.lower():
        return "doesn't mention the company"
    allowed = json.dumps(f) + " " + json.dumps(PROFILE)
    invented = find_skills(body, ALL_SKILLS) - find_skills(allowed, ALL_SKILLS)
    if invented:
        return f"mentions skills you don't have: {', '.join(sorted(invented))}"
    if re.search(r"\d", body):
        nums = set(re.findall(r"\d+(?:\.\d+)?", body)) - set(re.findall(r"\d+(?:\.\d+)?", allowed))
        if nums - {"15"}:
            return f"invented numbers: {', '.join(sorted(nums))}"
    return None


def llm_email(job, project, contact, brief, variant) -> tuple[str, str] | None:
    lo, hi = SETTINGS["outreach"]["word_range"]
    f = facts(job, project, brief)
    f["greeting_name"] = first_name(contact) or f"{job['company']} team"
    f["subject_style"] = "lead with the project" if variant == "A" else "lead with the role and university"
    if not brief:
        f["company_brief"] = ("NONE. No verified information about this company: do not describe, praise or make any "
                              "claim about what the company does. Open with the role instead.")
    for _ in range(2):
        out = llm.chat_json(SYSTEM.format(lo=lo, hi=hi), json.dumps(f))
        if not out or not isinstance(out.get("body"), str) or not isinstance(out.get("subject"), str):
            return None
        body = out["body"].strip()
        body = re.sub(r"\n*(best|regards|thanks|cheers|sincerely)[,!]?\s*\n.*$", "", body, flags=re.I | re.S).strip()
        if check_email(out["subject"], body, f, lo, hi) is None:
            return out["subject"].strip()[:120], f"{body}\n\n{signature()}"
    return None


def next_variant(db: DB) -> str:
    n = db.one("select count(*) n from outreach where kind = 'cold'")["n"]
    return "A" if n % 2 == 0 else "B"


def draft_outreach(db: DB, job_id: str, contact_id: str | None = None) -> dict:
    job = db.job_with_match(job_id)
    contacts = ([db.get("contacts", contact_id)] if contact_id else
                db.query("select * from contacts where job_id = ? or company = ? order by confidence desc",
                         (job_id, job["company"])))
    contacts = [c for c in contacts if c] or [None]
    domain = job.get("company_domain") or find_domain(db, job["company"], job.get("url") or "")
    brief = company_brief(db, job["company"], domain)
    project = pick_project(job)
    resume = db.one("select id from resumes where job_id = ? order by version desc limit 1", (job_id,))

    drafts = []
    for contact in contacts[:2]:  # at most two people per job
        if contact and db.one("select id from outreach where job_id = ? and contact_id = ? and kind = 'cold'",
                              (job_id, contact["id"])):
            continue
        variant = next_variant(db)
        made = llm_email(job, project, contact, brief, variant) if llm.available("write") else None
        subject, body = made or template_email(job, project, contact, brief, variant)
        drafts.append(db.insert("outreach", {
            "contact_id": contact["id"] if contact else None, "job_id": job_id, "kind": "cold", "variant": variant,
            "project_pitched": project["name"], "subject": subject, "body": body,
            "to_email": contact["email"] if contact else None, "resume_id": resume["id"] if resume else None,
            "status": "draft", "created_at": now(), "updated_at": now()}))
    db.log("draft", f"{len(drafts)} outreach drafts", job_id)
    return {"drafts": [d["id"] for d in drafts], "project": project["name"], "brief": brief}


REFERRAL = """Write a LinkedIn message (max 80 words) from a student to an alum / employee at a company asking for a
referral for a specific internship. Use only the given facts. Polite, specific, easy to say yes to; include the
job link. Return JSON: {"message": "..."}"""


def referral_message(db: DB, job_id: str, person: str = "") -> dict:
    job = db.job_with_match(job_id)
    project = pick_project(job)
    f = facts(job, project, "")
    msg = None
    if llm.available("write"):
        out = llm.chat_json(REFERRAL, json.dumps({**f, "person": person or "there", "job_url": job["url"]}))
        msg = out.get("message") if out else None
    if not msg:
        msg = (f"Hi {person or 'there'}, I'm {PROFILE['name']}, a {f['me']}. I'm applying for the {f['role']} role at "
               f"{job['company']} ({job['url']}). I built {f['project']['name']}, {project['pitch'][0].lower()}"
               f"{project['pitch'][1:]} Would you be comfortable referring me, or sharing any advice? Happy to send my resume. Thank you!")
    doc = db.insert("documents", {"job_id": job_id, "kind": "referral", "title": f"Referral ask: {job['company']}",
                                  "content": msg, "created_at": now()})
    return {"document_id": doc["id"], "message": msg}


def run_task(db: DB, task: dict) -> dict:
    return draft_outreach(db, task["job_id"], (task.get("payload") or {}).get("contact_id"))

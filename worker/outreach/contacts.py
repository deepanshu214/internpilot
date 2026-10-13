"""Find people to email at a company: Hunter.io (if you add a key), else the company's role inboxes
(careers@ / hr@ ...). Also builds LinkedIn/Google search links you open yourself (no LinkedIn automation)."""
import logging
import re
from urllib.parse import quote_plus

from ..config import HUNTER_API_KEY
from ..db import DB, now
from ..sources.http import HTTP
from .company import find_domain, has_mx

log = logging.getLogger(__name__)
RECRUITING = re.compile(r"recruit|talent|hiring|\bhr\b|human resources|people|campus|university", re.I)
ENGINEERING = re.compile(r"engineering manager|head of engineering|cto|vp engineering|tech lead|founder|co-founder", re.I)
ROLE_INBOXES = ["careers", "hr", "jobs", "talent", "hiring"]


def linkedin_search_url(company: str) -> str:
    q = f'"{company}" (recruiter OR "talent acquisition" OR "university recruiting" OR HR)'
    return f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(q)}"


def google_search_url(company: str) -> str:
    q = f'site:linkedin.com/in "{company}" (recruiter OR "talent acquisition" OR "campus hiring")'
    return f"https://www.google.com/search?q={quote_plus(q)}"


def guess_emails(first: str, last: str, domain: str) -> list[str]:
    """Common corporate patterns, most likely first. Used when you add a name by hand."""
    f, l = re.sub(r"[^a-z]", "", first.lower()), re.sub(r"[^a-z]", "", last.lower())
    if not f:
        return []
    pats = [f"{f}.{l}", f"{f}", f"{f}{l}", f"{f[0]}{l}", f"{f}_{l}", f"{f[0]}.{l}", f"{l}.{f}"] if l else [f]
    return [f"{p}@{domain}" for p in dict.fromkeys(pats)]


def hunter_domain_search(domain: str) -> list[dict]:
    if not HUNTER_API_KEY:
        return []
    r = HTTP.get("https://api.hunter.io/v2/domain-search", timeout=30,
                 params={"domain": domain, "api_key": HUNTER_API_KEY, "limit": 10})
    if r.status_code != 200:
        log.warning("hunter %s: %s", r.status_code, r.text[:200])
        return []
    people = []
    for e in r.json().get("data", {}).get("emails", []):
        pos = e.get("position") or ""
        rank = 2 if RECRUITING.search(pos) or e.get("department") == "hr" else 1 if ENGINEERING.search(pos) else 0
        people.append({"name": " ".join(filter(None, [e.get("first_name"), e.get("last_name")])) or None,
                       "title": pos or None, "email": e["value"], "confidence": e.get("confidence") or 50,
                       "source": "hunter", "rank": rank})
    return sorted(people, key=lambda p: (p["rank"], p["confidence"]), reverse=True)


def hunter_email_finder(first: str, last: str, domain: str) -> dict | None:
    if not HUNTER_API_KEY:
        return None
    r = HTTP.get("https://api.hunter.io/v2/email-finder", timeout=30, params={
        "domain": domain, "first_name": first, "last_name": last, "api_key": HUNTER_API_KEY})
    data = r.json().get("data") if r.status_code == 200 else None
    return {"email": data["email"], "confidence": data.get("score") or 50} if data and data.get("email") else None


def find_contacts(db: DB, job_id: str, limit: int = 3) -> dict:
    job = db.job_with_match(job_id)
    company = job["company"]
    domain = job.get("company_domain") or find_domain(db, company, job.get("url") or "")
    if domain and not job.get("company_domain"):
        db.update("jobs", job_id, {"company_domain": domain})
    li, google = linkedin_search_url(company), google_search_url(company)

    found = hunter_domain_search(domain)[:limit] if domain else []
    if not found and domain and has_mx(domain):
        # Role inboxes are read by recruiters at most startups; low confidence, clearly labelled.
        found = [{"name": None, "title": f"{box}@ inbox", "email": f"{box}@{domain}", "confidence": 25,
                  "source": "role-inbox"} for box in ROLE_INBOXES[:2]]

    existing = {r["email"] for r in db.query("select email from contacts where company = ?", (company,))}
    saved = []
    for p in found:
        if p["email"] in existing:
            continue
        saved.append(db.insert("contacts", {
            "company": company, "domain": domain, "job_id": job_id, "name": p["name"], "title": p["title"],
            "email": p["email"], "source": p["source"], "confidence": p["confidence"], "linkedin_search_url": li,
            "created_at": now()}))
    db.log("contacts", f"{len(saved)} new contacts (domain={domain})", job_id)
    return {"domain": domain, "contacts": [c["email"] for c in saved], "linkedin_search": li, "google_search": google}


def add_manual_contact(db: DB, job_id: str, name: str, title: str = "", email: str = "") -> dict:
    """You found someone on LinkedIn: give their name; we guess/verify the email."""
    job = db.job_with_match(job_id)
    domain = job.get("company_domain") or find_domain(db, job["company"], job.get("url") or "")
    first, _, last = name.strip().partition(" ")
    confidence, source = 90, "manual"
    if not email and domain:
        hit = hunter_email_finder(first, last.split(" ")[-1] if last else "", domain)
        if hit:
            email, confidence, source = hit["email"], hit["confidence"], "hunter"
        else:
            guesses = guess_emails(first, last.split(" ")[-1] if last else "", domain)
            email, confidence, source = (guesses[0] if guesses else ""), 35, "pattern"
    return db.insert("contacts", {"company": job["company"], "domain": domain, "job_id": job_id, "name": name,
                                  "title": title, "email": email, "source": source, "confidence": confidence,
                                  "linkedin_search_url": linkedin_search_url(job["company"]), "created_at": now()})


def run_task(db: DB, task: dict) -> dict:
    p = task.get("payload") or {}
    if p.get("name"):
        c = add_manual_contact(db, task["job_id"], p["name"], p.get("title", ""), p.get("email", ""))
        return {"contact_id": c["id"], "email": c["email"], "source": c["source"]}
    return find_contacts(db, task["job_id"])

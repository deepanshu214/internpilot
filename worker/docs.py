"""Generated documents per job: interview prep pack, cover letter, referral ask. Stored in `documents` (markdown)."""
import json

from . import llm
from .config import PROFILE
from .db import DB, now
from .match.skills import find_skills, skill_gap
from .outreach.company import company_brief, find_domain
from .outreach.draft import display_company, facts, pick_project, referral_message
from .tailor.validate import ALL_SKILLS

# Starter questions by domain; the LLM (when available) replaces these with JD-specific ones.
DOMAIN_QUESTIONS = {
    "security": ["Walk through the TCP three-way handshake and how a SYN flood abuses it.",
                 "How would you detect a port scan in network traffic?", "Symmetric vs asymmetric encryption: when do you use each?",
                 "What is the OWASP Top 10? Explain one item and its fix.", "How do JWTs work, and what are common mistakes?"],
    "backend": ["Design a URL shortener: API, storage, scaling.", "SQL vs NoSQL: how do you choose?",
                "How do you make an API idempotent?", "Explain database indexing and when an index hurts.",
                "What happens when you type a URL into a browser?"],
    "ml": ["Bias vs variance: how do you diagnose each?", "How does a random forest reduce overfitting?",
           "Precision vs recall: when does each matter?", "How would you handle class imbalance?",
           "Explain how a transformer's attention works at a high level."],
    "web": ["How does the browser render a page?", "Explain CORS.", "Cookies vs localStorage vs sessionStorage.",
            "What causes layout shift and how do you prevent it?"],
}
DSA = ["Two-sum / hash map pattern", "Reverse a linked list", "BFS vs DFS and when to use each",
       "Sliding window (longest substring without repeats)", "Binary search on answer", "Top-K with a heap"]


def _domain(job: dict) -> str:
    text = f"{job['title']} {job.get('jd_text') or ''}".lower()
    for key, words in (("security", ["security", "cyber", "soc", "threat"]), ("ml", ["machine learning", " ml ", "data scien", " ai "]),
                       ("web", ["frontend", "front-end", "react", "web developer"]), ("backend", ["backend", "back-end", "api", "server"])):
        if any(w in f" {text} " for w in words):
            return key
    return "backend"


def prep_pack(db: DB, job_id: str) -> str:
    job = db.job_with_match(job_id)
    brief = company_brief(db, job["company"], job.get("company_domain") or find_domain(db, job["company"], job.get("url") or ""))
    project = pick_project(job)
    have, missing = skill_gap(f"{job['title']} {job.get('jd_text') or ''}")
    body = None
    if llm.available():
        body = llm.chat_text(
            "You are an interview coach for a CS intern candidate. Write a concise markdown prep pack with sections: "
            "## The company (2-3 lines), ## What the role needs (bullets), ## Likely technical questions (8, specific to "
            "the JD) with one-line answer hints, ## Your talking points (map the candidate's real projects to the role; "
            "use only facts given), ## Gaps to brush up on, ## Questions to ask them (4). No fluff.",
            json.dumps({"job": {"title": job["title"], "company": job["company"], "jd": (job.get("jd_text") or "")[:4000]},
                        "company_brief": brief, "candidate_projects": PROFILE["projects"], "skills_matched": have,
                        "skills_missing": missing}), temperature=0.3)
    if not body:
        dom = _domain(job)
        lines = [f"## The company\n{brief or 'Read their website and recent blog posts before the interview.'}",
                 f"## What the role needs\n" + "\n".join(f"- {s}" for s in (have + missing)[:12]),
                 "## Likely technical questions\n" + "\n".join(f"- {q}" for q in DOMAIN_QUESTIONS[dom]),
                 "## DSA warm-up\n" + "\n".join(f"- {q}" for q in DSA),
                 f"## Your talking points\n**{project['name']}**: {project['pitch']}\n" +
                 "\n".join(f"- {b}" for b in project["bullets"]),
                 "## Gaps to brush up on\n" + ("\n".join(f"- {m}" for m in missing) or "- None spotted in the JD"),
                 "## Questions to ask them\n- What does a successful first month look like for an intern?\n"
                 "- What is the team working on this quarter?\n- How are interns mentored and reviewed?\n"
                 "- Is there a chance to convert to a full-time offer?"]
        body = "\n\n".join(lines)
    return _save(db, job_id, "prep", f"Interview prep: {display_company(job['company'])}", body)


def cover_letter(db: DB, job_id: str) -> str:
    job = db.job_with_match(job_id)
    brief = company_brief(db, job["company"], job.get("company_domain") or find_domain(db, job["company"], job.get("url") or ""))
    project = pick_project(job)
    f = facts(job, project, brief)
    text = None
    if llm.available():
        text = llm.chat_text(
            "Write a 200-250 word cover letter for an internship. Use ONLY the facts given; never invent metrics, "
            "tools or experience. Specific, confident, no clichés. Plain text, no placeholders.",
            json.dumps({**f, "projects": PROFILE["projects"][:4], "experience": PROFILE["experience"],
                        "jd": (job.get("jd_text") or "")[:3000]}), temperature=0.4)
        if text and (find_skills(text, ALL_SKILLS) - find_skills(json.dumps(PROFILE) + json.dumps(f), ALL_SKILLS)):
            text = None  # mentioned a skill you don't have → use the template instead
    if not text:
        proj = f["project"]
        text = (f"Dear {f['company']} Hiring Team,\n\n"
                f"I'm applying for the {f['role']} position. I'm a {f['me']}"
                + (f", and I recently worked as {f['recent_experience']}" if f["recent_experience"] else "") + ".\n\n"
                + (f"What draws me to {f['company']} is the work itself: {brief.rstrip('.')}.\n\n" if brief else "")
                + f"The project most relevant to this role is {proj['name']}: {project['pitch']} "
                + " ".join(project["bullets"][:2]) + "\n\n"
                f"I'd welcome the chance to bring the same care to {f['company']}'s team. Thank you for your time.\n\n"
                f"Sincerely,\n{PROFILE['name']}\n{PROFILE['email']} | {PROFILE['phone']}")
    return _save(db, job_id, "cover_letter", f"Cover letter: {display_company(job['company'])}", text)


def _save(db: DB, job_id: str, kind: str, title: str, content: str) -> str:
    return db.insert("documents", {"job_id": job_id, "kind": kind, "title": title, "content": content,
                                   "created_at": now()})["id"]


def run_task(db: DB, task: dict) -> dict:
    kind, job_id = task["kind"], task["job_id"]
    if kind == "prep":
        return {"document_id": prep_pack(db, job_id)}
    if kind == "cover_letter":
        return {"document_id": cover_letter(db, job_id)}
    if kind == "referral":
        return referral_message(db, job_id, (task.get("payload") or {}).get("person", ""))
    raise ValueError(f"unknown document kind {kind}")

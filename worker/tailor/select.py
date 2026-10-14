"""Choose which projects, bullets and skills go on the resume for one job description.
Heuristic ranking always runs; if an LLM is available it may also rephrase bullets to mirror the JD's wording,
and every rephrase goes through validate.check_bullet (rejected ones fall back to the original text)."""
import copy
import json
import logging

from .. import llm
from ..config import PROFILE
from ..match.score import bow, cosine
from ..match.skills import find_skills, profile_skills
from .validate import ALL_SKILLS, check_bullet, check_text, item_text

log = logging.getLogger(__name__)
MAX_PROJECTS = 3


def jd_keywords(jd: str) -> list[str]:
    """Profile skills the JD mentions, in the JD's order of first appearance (most prominent first)."""
    low = jd.lower()
    found = find_skills(jd, profile_skills())
    return sorted(found, key=lambda s: low.find(s.lower()) if s.lower() in low else len(low))


# Project tags → words that signal that domain in a job post.
DOMAIN_WORDS = {
    "security": ["security", "cyber", "infosec", "threat", "vulnerab", "pentest", "appsec", "soc"],
    "networking": ["network", "tcp", "packet", "protocol"], "ids": ["intrusion", "detection", "siem", "soc"],
    "cryptography": ["crypt", "pki", "tls"], "post-quantum": ["quantum"],
    "systems": ["systems", "kernel", "low-level", "operating system", "embedded"], "os": ["operating system", "linux"],
    "ml": ["machine learning", " ml ", "model", "data science", "deep learning"],
    "ai": [" ai ", "artificial intelligence", "llm", "genai", "generative"],
    "nlp": ["nlp", "natural language", "text"], "data": ["data", "analytics"],
    "backend": ["backend", "back-end", "api", "server", "microservice"], "api": ["api", "rest"],
    "databases": ["database", "sql", "postgres"], "web": ["web", "frontend", "front-end", "full stack", "fullstack"],
    "frontend": ["frontend", "front-end", "ui"], "realtime": ["real-time", "realtime", "streaming"],
    "dsa": ["data structures", "algorithms"], "cpp": ["c++"], "edtech": ["edtech", "education", "learning"],
}


def _domain_score(item: dict, jd_low: str, title_low: str) -> float:
    score = 0.0
    for tag in item.get("tags", []):
        words = DOMAIN_WORDS.get(tag, [tag])
        if any(w in title_low for w in words):
            score += 3      # the role itself is in this domain
        elif any(w in jd_low for w in words):
            score += 1
    return score


def _relevance(text: str, jd_bow: dict, jd_skills: set[str]) -> float:
    return 2.0 * len(find_skills(text, list(jd_skills))) + 10 * cosine(bow(text), jd_bow)


def heuristic_selection(jd: str, max_projects: int = MAX_PROJECTS, title: str = "") -> dict:
    jd_bow, kws = bow(jd), jd_keywords(jd)
    jd_skills = set(find_skills(jd, ALL_SKILLS))
    jd_low, title_low = f" {jd.lower()} ", f" {(title or jd[:120]).lower()} "

    def rank_bullets(item):
        # Keep the author's order on the page; the relevance ranking is kept separately for trimming.
        return list(item["bullets"])

    def drop_order(item):  # bullet indices, least relevant first
        return sorted(range(len(item["bullets"])), key=lambda i: _relevance(item["bullets"][i], jd_bow, jd_skills))

    projects = sorted(PROFILE["projects"], reverse=True, key=lambda p: (
        _relevance(item_text(p), jd_bow, jd_skills) + 2 * _domain_score(p, jd_low, title_low)))
    skills = {}
    for group, items in PROFILE["skills"].items():
        hit = [s for s in kws if s in items]
        skills[group] = hit + [s for s in items if s not in hit]
    return {
        "summary": PROFILE["summary"],
        "skills": skills,
        "experience": [{"name": e["org"], "bullets": rank_bullets(e), "drop_order": drop_order(e)}
                       for e in PROFILE["experience"]],
        "projects": [{"name": p["name"], "bullets": rank_bullets(p), "drop_order": drop_order(p)}
                     for p in projects[:max_projects]],
        "dropped_projects": [p["name"] for p in projects[max_projects:]],
        "keywords": kws,
        "rephrased": [],
        "rejected": [],
        "method": "heuristic",
    }


REPHRASE = """You tailor a student's resume to a job description WITHOUT inventing anything.
Rules (a validator enforces them and discards violations):
- Rephrase each bullet only to mirror the job's vocabulary where the meaning is identical.
- Never add a technology, tool, metric, number, team size or outcome that is not in the original bullet or item.
- Keep each bullet about the same length, past tense, no first person.
- Choose which projects best fit the job (pick from the given names only).
Return JSON: {"projects": [names, best first, max 3], "summary": "2 sentences, only facts from the given summary/skills",
"bullets": {"<original bullet>": "<rephrased bullet>", ...}}"""


def llm_selection(jd: str, base: dict, title: str = "") -> dict:
    """Refine the heuristic selection with an LLM. Returns base unchanged when no LLM is available."""
    payload = {
        "summary": PROFILE["summary"],
        "skills": profile_skills(),
        "experience": [{"org": e["org"], "role": e["role"], "bullets": e["bullets"]} for e in PROFILE["experience"]],
        "projects": [{"name": p["name"], "stack": p["stack"], "bullets": p["bullets"]} for p in PROFILE["projects"]],
    }
    out = llm.chat_json(REPHRASE, f"JOB DESCRIPTION:\n{jd[:5000]}\n\nRESUME:\n{json.dumps(payload)}")
    if not out:
        return base
    sel = copy.deepcopy(base)
    sel["method"] = llm.last_provider or "llm"

    names = {p["name"] for p in PROFILE["projects"]}
    picked = [n for n in out.get("projects", []) if n in names][:MAX_PROJECTS]
    if picked:
        by_name = {p["name"]: p for p in PROFILE["projects"]}
        full = {e["name"]: e for e in heuristic_selection(jd, len(names), title)["projects"]}
        sel["projects"] = [full[n] for n in picked if n in full]
        sel["dropped_projects"] = [n for n in names if n not in picked]

    rewrites = out.get("bullets") or {}
    for kind, source_key in (("projects", "name"), ("experience", "org")):
        for entry in sel[kind]:
            item = next(x for x in PROFILE[kind] if x[source_key] == entry["name"])
            new_bullets = []
            for b in entry["bullets"]:
                new = rewrites.get(b)
                if not isinstance(new, str) or new.strip() == b:
                    new_bullets.append(b)
                    continue
                reason = check_bullet(new.strip(), b, item)
                if reason:
                    sel["rejected"].append({"original": b, "rewrite": new, "reason": reason})
                    new_bullets.append(b)
                else:
                    sel["rephrased"].append({"original": b, "rewrite": new.strip()})
                    new_bullets.append(new.strip())
            entry["bullets"] = new_bullets

    summary = out.get("summary")
    if isinstance(summary, str) and summary.strip():
        reason = check_text(summary, PROFILE["summary"] + " " + " ".join(profile_skills()), max_len=420)
        if reason:
            sel["rejected"].append({"original": "summary", "rewrite": summary, "reason": reason})
        else:
            sel["summary"] = summary.strip()
    return sel


def select(jd: str, title: str = "") -> dict:
    base = heuristic_selection(jd, title=title)
    return llm_selection(jd, base, title) if llm.available("write") else base

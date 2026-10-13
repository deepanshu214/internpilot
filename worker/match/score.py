"""Two-stage matching: cheap vector similarity for everything, LLM rubric for the top slice."""
import json
import math
import re
from collections import Counter

from .. import llm
from ..config import PROFILE, SETTINGS
from .skills import skill_gap

_WORD = re.compile(r"[a-z][a-z0-9+#.]{1,}")
_STOP = set("the and for with you your our are will this that from have has can who what all any not but its into "
            "about their they them more such also work team teams role job intern internship experience ability "
            "skills strong including well able using use etc per day".split())


def profile_text() -> str:
    p = PROFILE
    parts = [p["summary"], " ".join(s for g in p["skills"].values() for s in g)]
    for item in p["projects"] + p["experience"]:
        parts.append(" ".join(item.get("bullets", [])) + " " + " ".join(item.get("stack", item.get("tags", []))))
    return "\n".join(parts)


def bow(text: str) -> dict:
    return dict(Counter(w for w in _WORD.findall((text or "").lower()) if w not in _STOP))


def cosine(a, b) -> float:
    if isinstance(a, dict):
        dot = sum(v * b.get(k, 0) for k, v in a.items())
        na, nb = math.sqrt(sum(v * v for v in a.values())), math.sqrt(sum(v * v for v in b.values()))
    else:
        dot = sum(x * y for x, y in zip(a, b))
        na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def job_text(job) -> str:
    return f"{job.title} at {job.company}. {job.location}. {job.jd_text}"[:6000]


def similarities(jobs) -> tuple[list[float], list | None]:
    """Cosine similarity of each job to the profile. Uses Ollama embeddings if available, else bag-of-words."""
    texts = [job_text(j) for j in jobs]
    vecs = llm.embed([profile_text(), *texts]) if jobs else None
    if vecs:
        prof, rest = vecs[0], vecs[1:]
        return [cosine(prof, v) for v in rest], rest
    prof = bow(profile_text())
    return [cosine(prof, bow(t)) for t in texts], None


def settings_hot() -> int:
    return SETTINGS["match"]["hot_threshold"]


def heuristic_score(job, sim_pct: float) -> tuple[int, list[str], list[str]]:
    have, missing = skill_gap(job_text(job))
    # Half coverage (share of the JD's skills you have), half depth (2 matching skills shouldn't look like 8).
    overlap = 0.5 * len(have) / max(1, len(have) + len(missing)) + 0.5 * min(1, len(have) / 6)
    if len(job.jd_text) < 200:  # list-only sources (no JD): can alert, but never "apply today" without a JD
        score = 100 * (0.25 * overlap + 0.55 * sim_pct)
    else:
        score = 100 * (0.55 * overlap + 0.45 * sim_pct)
    score = min(score, settings_hot() - 1)
    reasons = [f"Matches your skills: {', '.join(have[:8])}"] if have else ["Title/role similar to your profile"]
    return round(score), reasons, missing


RUBRIC = """You are a strict technical recruiter screening internship applications.
Score how well the CANDIDATE fits the JOB from 0-100 using this rubric:
- 40 pts: required skills/technologies the candidate demonstrably has
- 25 pts: relevance of the candidate's projects/experience to the team's work
- 20 pts: eligibility (student year, graduation year {grad_year}, degree, location {location}, work authorization)
- 15 pts: nice-to-have skills and domain fit
Hard rules: if the job requires a PhD, a graduation year the candidate can't meet, or work authorization they lack
(e.g. US citizenship / OPT for a US-only role), cap the score at 30.
Return ONLY JSON: {{"score": int, "reasons": [3 short strings on why they fit],
"missing_skills": [short strings], "eligibility_issue": string or null, "best_project": project name}}"""


def llm_score(job, missing_hint: list[str]) -> dict | None:
    p = PROFILE
    candidate = {
        "degree": p["degree"], "grad_year": p["grad_year"], "location": p["location"],
        "skills": p["skills"], "experience": [{k: e[k] for k in ("role", "org", "bullets")} for e in p["experience"]],
        "projects": [{"name": x["name"], "stack": x["stack"], "pitch": x["pitch"]} for x in p["projects"]],
    }
    user = (f"CANDIDATE:\n{json.dumps(candidate)}\n\nJOB: {job.title} at {job.company} ({job.location})\n"
            f"{job.jd_text[:5000]}\n\nKeyword scan suggests missing: {', '.join(missing_hint) or 'none'}")
    out = llm.chat_json(RUBRIC.format(grad_year=p["grad_year"], location=p["location"]), user)
    if not out or not isinstance(out.get("score"), (int, float)):
        return None
    out["score"] = max(0, min(100, int(out["score"])))
    return out


def score_jobs(jobs, settings=SETTINGS) -> list[dict]:
    """Returns one result dict per job: {job, score, reasons, missing, method, embedding}."""
    if not jobs:
        return []
    sims, embeddings = similarities(jobs)
    order = sorted(range(len(jobs)), key=lambda i: sims[i])
    pct = {i: rank / max(1, len(jobs) - 1) for rank, i in enumerate(order)}

    results = []
    for i, job in enumerate(jobs):
        score, reasons, missing = heuristic_score(job, pct[i])
        results.append({"job": job, "score": score, "reasons": reasons, "missing": missing,
                        "method": "heuristic", "embedding": embeddings[i] if embeddings else None, "sim": sims[i]})

    # Stage 2: LLM rubric on the best slice by similarity, capped per run.
    cfg = settings["match"]
    keep_n = max(1, math.ceil(len(jobs) * cfg["prefilter_keep"]))
    shortlist = sorted(results, key=lambda r: (r["sim"], r["score"]), reverse=True)[:keep_n]
    if llm.available():
        for r in sorted(shortlist, key=lambda r: r["score"], reverse=True)[: cfg["llm_max_per_run"]]:
            out = llm_score(r["job"], r["missing"])
            if out:
                r.update(score=out["score"], method=llm.available(),
                         reasons=out.get("reasons") or r["reasons"],
                         missing=out.get("missing_skills") or r["missing"])
                if out.get("eligibility_issue"):
                    r["reasons"] = [f"⚠️ {out['eligibility_issue']}", *r["reasons"]]
                if out.get("best_project"):
                    r["reasons"].append(f"Pitch: {out['best_project']}")
    return results

"""Remote job boards with public APIs, plus Hacker News 'Who is hiring?' threads."""
import re

from ..models import Job, clean_html, from_epoch, from_iso
from .http import HTTP


def remotive() -> list[Job]:
    r = HTTP.get("https://remotive.com/api/remote-jobs", params={"search": "intern"}, timeout=30)
    r.raise_for_status()
    return [Job(source="remotive", company=j["company_name"], title=j["title"],
                location=j.get("candidate_required_location") or "Remote", url=j["url"], remote=True,
                jd_text=clean_html(j.get("description", "")), posted_at=from_iso(j.get("publication_date")))
            for j in r.json().get("jobs", [])]


def remoteok() -> list[Job]:
    r = HTTP.get("https://remoteok.com/api", params={"tag": "intern"}, timeout=30)
    r.raise_for_status()
    return [Job(source="remoteok", company=j.get("company", ""), title=j.get("position", ""),
                location=j.get("location") or "Remote", url=j.get("url", ""), remote=True,
                jd_text=clean_html(j.get("description", "")) + " " + ", ".join(j.get("tags") or []),
                posted_at=from_epoch(j.get("epoch")))
            for j in r.json() if isinstance(j, dict) and j.get("position")]  # first element is a legal notice


def hn_hiring() -> list[Job]:
    """Top-level comments of the latest 'Ask HN: Who is hiring?' that mention interns."""
    stories = HTTP.get("https://hn.algolia.com/api/v1/search_by_date", timeout=30,
                       params={"tags": "story,author_whoishiring", "query": "who is hiring"}).json()["hits"]
    story = next(s for s in stories if s["title"].startswith("Ask HN: Who is hiring?"))
    item = HTTP.get(f"https://hn.algolia.com/api/v1/items/{story['objectID']}", timeout=60).json()
    jobs = []
    for c in item.get("children", []):
        text = clean_html(c.get("text") or "")
        if not re.search(r"\bintern(s|ship|ships)?\b", text, re.I):
            continue
        # Convention: "Company | Role | Location | Remote/Onsite | ..."
        head = [p.strip() for p in text.split("|")]
        company = head[0][:80] if head else "HN"
        location = next((p for p in head[1:5] if re.search(r"remote|india|onsite|hybrid|,", p, re.I)), "")
        jobs.append(Job(source="hn", company=company, title=f"Intern ({head[1][:80] if len(head) > 1 else 'see post'})",
                        location=location, url=f"https://news.ycombinator.com/item?id={c['id']}",
                        remote=bool(re.search(r"\bremote\b", location, re.I)), jd_text=text[:6000],
                        posted_at=from_epoch(c.get("created_at_i")), extra={"is_internship": True}))
    return jobs

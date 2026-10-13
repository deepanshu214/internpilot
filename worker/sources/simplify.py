"""SimplifyJobs' community-maintained internship list (GitHub). Has no JD text, only title/terms."""
import requests

from ..models import Job, from_epoch


def simplify(url: str) -> list[Job]:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    jobs = []
    for j in r.json():
        if not (j.get("active") and j.get("is_visible", True)):
            continue
        locations = j.get("locations") or []
        loc = "; ".join(locations)
        jobs.append(Job(
            source="simplify", company=j.get("company_name", ""), title=j.get("title", ""), location=loc,
            url=j.get("url", ""), posted_at=from_epoch(j.get("date_posted")),
            remote=any("remote" in l.lower() for l in locations),
            jd_text=f"{j.get('title', '')}. Terms: {', '.join(j.get('terms') or [])}. Category: {j.get('category', '')}",
        ))
    return jobs

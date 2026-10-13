"""Indian internship platforms: Internshala (public listing pages) and Unstop (public search API).
Both list internships only, so titles are trusted as internships even without the word "intern"."""
import logging
import re
from datetime import datetime, timedelta, timezone

from bs4 import BeautifulSoup

from ..models import Job, clean_html, from_iso
from .http import HTTP

log = logging.getLogger(__name__)


def _ago(text: str):
    """Internshala shows 'Just now', '3 days ago', '2 weeks ago'."""
    m = re.search(r"(\d+)\s*(hour|day|week|month)", text or "")
    if not m:
        return datetime.now(timezone.utc) if "now" in (text or "").lower() or "today" in (text or "").lower() else None
    n, unit = int(m.group(1)), m.group(2)
    days = {"hour": n / 24, "day": n, "week": 7 * n, "month": 30 * n}[unit]
    return datetime.now(timezone.utc) - timedelta(days=days)


def internshala(categories: list[str], pages: int = 2) -> list[Job]:
    jobs = []
    for cat in categories:
        for page in range(1, pages + 1):
            url = f"https://internshala.com/internships/{cat}/page-{page}/"
            r = HTTP.get(url, timeout=30)
            if r.status_code != 200:
                break
            soup = BeautifulSoup(r.text, "html.parser")
            cards = soup.select("div.individual_internship[internshipid]")
            if not cards:
                break
            for c in cards:
                a = c.select_one("a.job-title-href")
                if not a:
                    continue
                locs = ", ".join(x.get_text(strip=True) for x in c.select(".locations a")) or "India"
                skills = ", ".join(x.get_text(strip=True) for x in c.select(".job_skill"))
                about = c.select_one(".about_job .text")
                stipend = c.select_one(".stipend")
                posted = c.select_one(".status-inactive, .status-success, .status-info, .status")
                jobs.append(Job(
                    source="internshala", company=(c.select_one(".company-name") or a).get_text(strip=True),
                    title=a.get_text(strip=True), location=f"{locs}, India" if "india" not in locs.lower() else locs,
                    url="https://internshala.com" + a["href"], remote="work from home" in locs.lower(),
                    posted_at=_ago(posted.get_text(" ", strip=True) if posted else ""),
                    jd_text=f"{a.get_text(strip=True)}. Skills: {skills}. {about.get_text(' ', strip=True) if about else ''} "
                            f"Stipend: {stipend.get_text(strip=True) if stipend else 'n/a'}",
                    extra={"is_internship": True}))
    return jobs


def unstop(search_terms: list[str], per_page: int = 30) -> list[Job]:
    jobs = []
    for term in search_terms:
        r = HTTP.get("https://unstop.com/api/public/opportunity/search-result", timeout=30, params={
            "opportunity": "internships", "per_page": per_page, "oppstatus": "open", "searchTerm": term})
        r.raise_for_status()
        for o in r.json()["data"]["data"]:
            detail = o.get("jobDetail") or {}
            locs = ", ".join(l.get("city", "") if isinstance(l, dict) else str(l) for l in detail.get("locations") or [])
            wfh = detail.get("type") == "wfh" or o.get("region") == "online"
            eligible = ", ".join(f["name"] for f in o.get("filters") or [] if f.get("type") == "eligible")
            jobs.append(Job(
                source="unstop", company=(o.get("organisation") or {}).get("name", ""), title=o.get("title", ""),
                location=f"{locs}, India" if locs else ("Remote" if wfh else "India"), remote=wfh,
                url=o.get("seo_url") or f"https://unstop.com/{o.get('public_url', '')}",
                posted_at=from_iso(o.get("updated_at")),
                jd_text=f"{clean_html(o.get('details', ''))} Eligible: {eligible}. Deadline: {o.get('end_date', '')}",
                extra={"is_internship": True, "deadline": o.get("end_date")}))
    return jobs

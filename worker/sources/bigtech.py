"""Big-company career sites with public JSON: Workday (NVIDIA, Salesforce, Adobe, Intel, Cisco, ...) and Amazon."""
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from ..filters import location_ok, title_ok
from ..models import Job, clean_html
from .http import HTTP


def _posted_on(text: str):
    """Workday: 'Posted Today', 'Posted Yesterday', 'Posted 5 Days Ago', 'Posted 30+ Days Ago'."""
    t = (text or "").lower()
    if "today" in t:
        days = 0
    elif "yesterday" in t:
        days = 1
    elif m := re.search(r"(\d+)", t):
        days = int(m.group(1))
    else:
        return None
    return datetime.now(timezone.utc) - timedelta(days=days)


def workday(entry: dict) -> list[Job]:
    """entry = {company, host: nvidia.wd5.myworkdayjobs.com, tenant: nvidia, site: NVIDIAExternalCareerSite}"""
    base = f"https://{entry['host']}/wday/cxs/{entry['tenant']}/{entry['site']}"
    postings = []
    for offset in range(0, 100, 20):  # Workday caps page size at 20
        r = HTTP.post(f"{base}/jobs", timeout=30, json={
            "appliedFacets": {}, "limit": 20, "offset": offset, "searchText": entry.get("search", "intern")})
        r.raise_for_status()
        page = r.json().get("jobPostings", [])
        postings += page
        if len(page) < 20:
            break

    def detail(p):
        info = HTTP.get(base + p["externalPath"], timeout=30).json()["jobPostingInfo"]
        locs = [info.get("location", ""), *(info.get("additionalLocations") or [])]
        return Job(source="workday", company=entry["company"], title=info["title"], location="; ".join(filter(None, locs)),
                   url=info.get("externalUrl") or f"https://{entry['host']}/{entry['site']}{p['externalPath']}",
                   jd_text=clean_html(info.get("jobDescription", "")), posted_at=_posted_on(p.get("postedOn")),
                   remote="remote" in (info.get("remoteType") or "").lower())

    # Only fetch descriptions for intern titles in an allowed location. The listing gives the location only
    # inside the URL ("/job/India-Pune/...") or as "3 Locations"; fetch the detail when it's ambiguous.
    def maybe_here(p):
        path_loc = p.get("externalPath", "").split("/")[2] if p.get("externalPath", "").count("/") >= 3 else ""
        multi = "locations" in (p.get("locationsText") or "").lower()
        return multi or location_ok(Job("workday", "", "", path_loc.replace("-", " "), "")) or not path_loc

    wanted = [p for p in postings if title_ok(p.get("title", "")) and maybe_here(p)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(detail, wanted))


def amazon(country_codes: list[str]) -> list[Job]:
    jobs = []
    for cc in country_codes:
        for offset in range(0, 200, 50):
            r = HTTP.get("https://www.amazon.jobs/en/search.json", timeout=30, params={
                "base_query": "intern", "normalized_country_code[]": cc, "result_limit": 50, "offset": offset,
                "sort": "recent"})
            r.raise_for_status()
            page = r.json().get("jobs", [])
            for j in page:
                try:
                    posted = datetime.strptime(" ".join(j["posted_date"].split()), "%B %d, %Y").replace(tzinfo=timezone.utc)
                except (KeyError, ValueError):
                    posted = None
                jobs.append(Job(
                    source="amazon", company="Amazon", title=j["title"], location=j.get("normalized_location", ""),
                    url="https://www.amazon.jobs" + j["job_path"], posted_at=posted,
                    jd_text=clean_html(f"{j.get('description', '')} Basic: {j.get('basic_qualifications', '')} "
                                       f"Preferred: {j.get('preferred_qualifications', '')}")))
            if len(page) < 50:
                break
    return jobs

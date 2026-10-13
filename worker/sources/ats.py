"""Public job-board APIs used by companies' own careers pages. No auth, no scraping."""
from ..models import Job, clean_html, from_epoch, from_iso
from .http import HTTP


def greenhouse(slug: str) -> list[Job]:
    r = HTTP.get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true", timeout=30)
    r.raise_for_status()
    company = slug.title()
    return [
        Job(source="greenhouse", company=company, title=j["title"],
            location=(j.get("location") or {}).get("name", ""), url=j["absolute_url"],
            jd_text=clean_html(j.get("content", "")), posted_at=from_iso(j.get("first_published") or j.get("updated_at")))
        for j in r.json().get("jobs", [])
    ]


def lever(slug: str) -> list[Job]:
    r = HTTP.get(f"https://api.lever.co/v0/postings/{slug}?mode=json", timeout=90)  # big boards are slow
    r.raise_for_status()
    jobs = []
    for j in r.json():
        cats = j.get("categories") or {}
        lists = " ".join(f"{x.get('text', '')}: {clean_html(x.get('content', ''))}" for x in j.get("lists", []))
        jobs.append(Job(
            source="lever", company=slug.title(), title=j["text"], location=cats.get("location", ""),
            url=j["hostedUrl"], jd_text=f"{j.get('descriptionPlain', '')} {lists} {j.get('additionalPlain', '')}".strip(),
            posted_at=from_epoch(j.get("createdAt")), remote=j.get("workplaceType") == "remote"))
    return jobs


def ashby(slug: str) -> list[Job]:
    r = HTTP.get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", timeout=30)
    r.raise_for_status()
    return [
        Job(source="ashby", company=slug.title(), title=j["title"], location=j.get("location", ""),
            url=j["jobUrl"], jd_text=j.get("descriptionPlain") or clean_html(j.get("descriptionHtml", "")),
            posted_at=from_iso(j.get("publishedAt")), remote=bool(j.get("isRemote")))
        for j in r.json().get("jobs", []) if j.get("isListed", True)
    ]


FETCHERS = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}

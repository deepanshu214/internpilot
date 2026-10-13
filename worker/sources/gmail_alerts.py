"""Job-alert emails as a source: LinkedIn, Wellfound, Naukri, Instahyre, Cutshort, Internshala, Glassdoor...
Covers platforms with no public feed. Set up alerts on those sites (to this Gmail) and they flow in here."""
import re
from urllib.parse import parse_qs, unquote, urlparse

from bs4 import BeautifulSoup

from .. import gmail
from ..models import Job

SENDERS = {
    "linkedin": "jobalerts-noreply@linkedin.com OR jobs-listings@linkedin.com OR jobs-noreply@linkedin.com",
    "wellfound": "wellfound.com OR angel.co", "naukri": "naukri.com", "instahyre": "instahyre.com",
    "cutshort": "cutshort.io", "internshala": "internshala.com", "glassdoor": "glassdoor.com",
    "indeed": "indeed.com", "hirist": "hirist.tech", "foundit": "foundit.in",
}
JOB_LINK = re.compile(r"linkedin\.com/(comm/)?jobs/view/\d+|wellfound\.com/(jobs|company/[^/]+/jobs)/|naukri\.com/job-listings"
                      r"|instahyre\.com/job-|cutshort\.io/job/|internshala\.com/(internship|job)/detail|glassdoor\.[a-z.]+/job-listing"
                      r"|indeed\.com/(rc/clk|viewjob|pagead)|hirist\.tech/j/|foundit\.in/job/", re.I)
NOISE = re.compile(r"^(view job|apply|see all jobs|view all|unsubscribe|easy apply|see more|view|apply now|save)$", re.I)


def _unwrap(href: str) -> str:
    """Strip tracking redirects (…?url=https%3A… ) and query noise from alert links."""
    q = parse_qs(urlparse(href).query)
    for key in ("url", "u", "target", "dest", "redirect"):
        if key in q and q[key][0].startswith("http"):
            href = unquote(q[key][0])
    m = re.search(r"(https?://[^?#]+linkedin\.com/(?:comm/)?jobs/view/\d+)", href)
    return m.group(1).replace("/comm/", "/") if m else href.split("?")[0] if "linkedin.com" in href else href


def parse_alert(platform: str, html_body: str) -> list[Job]:
    soup = BeautifulSoup(html_body or "", "html.parser")
    jobs, seen = [], set()
    for a in soup.find_all("a", href=True):
        url = _unwrap(a["href"])
        if not JOB_LINK.search(url) or url in seen:
            continue
        title = a.get_text(" ", strip=True)
        if not title or NOISE.match(title) or len(title) > 140:
            continue
        # Company / location are usually the next short text lines in the same card.
        block = a.find_parent(["td", "div", "li", "table"]) or a.parent
        lines = [t.strip() for t in block.get_text("\n").split("\n") if t.strip() and t.strip() != title]
        lines = [l for l in lines if not NOISE.match(l) and len(l) < 100]
        company = lines[0] if lines else ""
        location = next((l for l in lines[1:4] if re.search(r",|remote|india|hybrid|on-site", l, re.I)), "")
        company = re.split(r"\s+[·•|-]\s+", company)[0]
        seen.add(url)
        jobs.append(Job(source=f"gmail:{platform}", company=company, title=title, location=location, url=url,
                        remote="remote" in location.lower(), jd_text=title,
                        extra={"is_internship": True} if platform == "internshala" else {}))
    return jobs


def gmail_alerts(days: int = 3) -> list[Job]:
    if not gmail.available():
        return []
    jobs = []
    for platform, senders in SENDERS.items():
        for mid in gmail.search(f"newer_than:{days}d from:({senders})", 30):
            msg = gmail.get(mid)
            jobs += parse_alert(platform, msg["html"])
    return jobs

"""Find a company's website domain and a short 'what they build' brief (cached in the companies table)."""
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import requests

import dns.exception
import dns.resolver
from bs4 import BeautifulSoup

from .. import llm
from ..db import DB, now
from ..sources.http import BROWSER_UA

log = logging.getLogger(__name__)

# Hosts that belong to job boards, not to the hiring company.
BOARD_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com", "linkedin.com", "indeed.", "naukri.com", "glassdoor.",
               "internshala.com", "unstop.com", "myworkdayjobs.com", "amazon.jobs", "remotive.com", "remoteok.com",
               "ycombinator.com", "google.com", "simplify.jobs", "workable.com", "smartrecruiters.com", "wellfound.com")
SUFFIXES = r"\b(inc|llc|ltd|limited|pvt|private|corp|corporation|co|company|technologies|technology|tech|solutions|" \
           r"labs|software|systems|services|india|global|group|ai)\b\.?"
TLDS = (".com", ".in", ".ai", ".io", ".co", ".tech", ".app", ".dev")
LEGAL = r"\b(inc|llc|ltd|limited|pvt|private|corp|corporation|co|company|plc|llp|gmbh)\b\.?"
# Parked / for-sale pages mention the company name (it's in the domain) but nobody there will read your email.
PARKED = re.compile(r"domain\s+(?:name\s+)?(?:may\s+be\s+|is\s+)?for\s+sale|buy\s+this\s+domain|this\s+domain\s+is\s+parked|"
                    r"parked\s+(?:free|domain)|sedoparking|hugedomains|afternic|dan\.com|domain\s+has\s+expired|"
                    r"related\s+searches|this\s+domain\s+(?:name\s+)?is\s+available", re.I)


def norm_company(name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())).strip()


def has_mx(domain: str) -> bool:
    try:
        return bool(dns.resolver.resolve(domain, "MX", lifetime=3))
    except (dns.exception.DNSException, ValueError):
        return False


def public_hostname(host: str) -> bool:
    """Real internet domains only: no IP literals, localhost or single-label/internal names."""
    host = (host or "").lower().rstrip(".")
    if not host or "." not in host or host.endswith((".local", ".internal", ".lan", ".localhost")) or host == "localhost":
        return False
    return not re.fullmatch(r"[\d.]+|\[?[0-9a-f:]+\]?", host)


def candidate_domains(company: str, job_url: str = "") -> list[str]:
    out = []
    host = urlparse(job_url or "").hostname or ""
    if host and public_hostname(host) and not any(b in host for b in BOARD_HOSTS):
        out.append(re.sub(r"^(www|careers|jobs|apply)\.", "", host))
    base = norm_company(company)
    core = re.sub(SUFFIXES, " ", base).split()
    stems = []
    for words in (core, base.split()):
        if words:
            stems += ["".join(words), "-".join(words)]
    if core:
        stems.append(core[0])
    for stem in dict.fromkeys(s for s in stems if len(s) >= 3):
        out += [stem + tld for tld in TLDS]
    return list(dict.fromkeys(out))


def _site_matches(domain: str, company: str) -> str | None:
    """Fetch the homepage; return its HTML if the page plausibly belongs to `company`."""
    try:  # plain request, no retries: most candidates don't exist and must fail fast
        r = requests.get(f"https://{domain}", timeout=8, headers={"User-Agent": BROWSER_UA})
    except requests.RequestException:
        return None
    if r.status_code >= 400 or "html" not in r.headers.get("content-type", ""):
        return None
    return r.text if site_belongs_to(domain, company, r.text) else None


def site_belongs_to(domain: str, company: str, html_text: str) -> bool:
    """Strict check that a homepage is really this company's, so outreach never goes to a look-alike or parked domain.
    Accept when the domain spells the full company name (dexterstech.com for "Dexter's Tech"), or the page's
    title/site name contains the full name, or the domain is the core name and the title says so too."""
    if PARKED.search(html_text[:60_000]):
        return False
    soup = BeautifulSoup(html_text[:200_000], "html.parser")
    names = [soup.title.string if soup.title and soup.title.string else ""]
    for attr in ({"property": "og:site_name"}, {"property": "og:title"}, {"name": "application-name"}):
        m = soup.find("meta", attrs=attr)
        if m and m.get("content"):
            names.append(m["content"])
    titles = norm_company(" ".join(names))
    full = re.sub(LEGAL, " ", norm_company(company)).split()          # "dexter s tech"
    core = re.sub(SUFFIXES, " ", " ".join(full)).split()                # "dexter s"
    stem = re.sub(r"[^a-z0-9]", "", domain.lower().removeprefix("www.").split(".")[0])
    if not full:
        return False
    if "".join(full) in stem or re.search(rf"\b{re.escape(' '.join(full))}\b", titles):
        return True
    return bool(core) and stem == "".join(core) and re.search(rf"\b{re.escape(' '.join(core))}\b", titles) is not None


def find_domain(db: DB, company: str, job_url: str = "") -> str | None:
    key = norm_company(company)
    cached = db.get("companies", key, key="name")
    if cached:  # includes "looked before, found nothing" (set the domain by hand in the dashboard)
        return cached.get("domain") or None
    candidates = [d for d in candidate_domains(company, job_url) if public_hostname(d)][:14]
    with ThreadPoolExecutor(max_workers=8) as pool:
        mx = dict(zip(candidates, pool.map(has_mx, candidates)))
    found = next((d for d in candidates if mx[d] and _site_matches(d, company)), None)
    _save(db, key, domain=found)
    return found


def extract_site_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        t.decompose()
    parts = []
    if soup.title and soup.title.string:
        parts.append(soup.title.string.strip())
    for attr in ({"name": "description"}, {"property": "og:description"}):
        m = soup.find("meta", attrs=attr)
        if m and m.get("content"):
            parts.append(m["content"].strip())
    for tag in soup.find_all(["h1", "h2", "p"])[:25]:
        text = tag.get_text(" ", strip=True)
        if 25 <= len(text) <= 400:
            parts.append(text)
    return re.sub(r"\s+", " ", " ".join(dict.fromkeys(parts)))[:3500]


def fallback_brief(html: str) -> str:
    """No LLM: the site's own one-line description (meta description, else <title>)."""
    soup = BeautifulSoup(html, "html.parser")
    for attr in ({"name": "description"}, {"property": "og:description"}):
        m = soup.find("meta", attrs=attr)
        if m and m.get("content", "").strip():
            return m["content"].strip().split(". ")[0].rstrip(".")[:200]
    return (soup.title.string or "").strip()[:150] if soup.title else ""


BRIEF = """Summarize what this company builds in 2 short sentences for a student writing them a cold email:
what the product is, who uses it, and any engineering focus you can infer. Use only facts from the text.
No marketing fluff. If the text is unclear, say what is clear and stop."""


def company_brief(db: DB, company: str, domain: str | None) -> str:
    key = norm_company(company)
    cached = db.get("companies", key, key="name")
    if cached and cached.get("brief"):
        return cached["brief"]
    brief = ""
    if domain:
        html = _site_matches(domain, company) or ""
        text = extract_site_text(html) if html else ""
        if text:
            brief = (llm.chat_text(BRIEF, f"Company: {company}\nWebsite text:\n{text}", purpose="score", temperature=0.2)
                     or fallback_brief(html))
    _save(db, key, domain=domain, brief=brief)
    return brief


def _save(db: DB, key: str, **fields):
    if db.get("companies", key, key="name"):
        db.update("companies", key, {**{k: v for k, v in fields.items() if v}, "fetched_at": now()}, key="name")
    else:
        db.insert("companies", {"name": key, **fields, "fetched_at": now()})

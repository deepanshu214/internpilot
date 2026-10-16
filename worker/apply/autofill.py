"""Apply-assist: open the application in a visible browser, pre-fill it from profile + answers bank, attach the
tailored resume, and STOP. You review every field and press Submit yourself. Nothing here ever clicks submit.

The dashboard queues an `autofill` task; the worker starts this module as a separate process so the browser
can stay open while the worker keeps running:  python -m worker.apply.autofill <job_id>"""
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

from .. import llm
from ..config import OUTPUT_DIR, PROFILE, ROOT, SETTINGS
from ..db import DB, now
from ..match.skills import find_skills
from ..tailor.validate import ALL_SKILLS

log = logging.getLogger(__name__)
CONFIRMED = re.compile(r"thank(s| you) for (applying|your application|submitting)|application (has been )?(submitted|received)"
                       r"|we('ve| have) received your application|successfully (applied|submitted)", re.I)
RESUME_FIELD = re.compile(r"resume|\bcv\b|curriculum", re.I)
COVER_FIELD = re.compile(r"cover letter", re.I)
REVIEW_STYLE = "e => { e.style.outline = '3px solid #f59e0b'; e.style.outlineOffset = '2px'; }"
SUBMIT_STYLE = ("e => { e.style.outline = '4px solid #ef4444'; e.style.outlineOffset = '3px';"
                " e.title = 'InternPilot filled this form. Review every field, then submit yourself.'; }")

# Collects each visible field with the best label text we can find; tags it with data-ip-idx for filling.
DESCRIBE_FIELDS = """() => {
  const out = [];
  const els = [...document.querySelectorAll('input, textarea, select')];
  els.forEach((el, i) => {
    const type = (el.getAttribute('type') || el.tagName).toLowerCase();
    if (['hidden', 'submit', 'button', 'reset', 'image', 'search', 'password'].includes(type)) return;
    const style = getComputedStyle(el);
    const fileInput = type === 'file';
    if (!fileInput && (el.offsetParent === null || style.visibility === 'hidden')) return;
    el.setAttribute('data-ip-idx', String(i));
    const byFor = el.id ? document.querySelector(`label[for="${CSS.escape(el.id)}"]`) : null;
    const wrap = el.closest('label');
    const labelledby = (el.getAttribute('aria-labelledby') || '').split(/\\s+/)
        .map(id => (document.getElementById(id) || {}).innerText || '').join(' ');
    const box = el.closest('.application-question, .field, .form-group, li, fieldset, [class*="question"], [class*="Field"], [class*="field"]');
    const boxLabel = box ? ((box.querySelector('label, legend, .application-label, [class*="label"], [class*="Label"]') || {}).innerText || '') : '';
    const label = (byFor && byFor.innerText) || (wrap && wrap.innerText) || el.getAttribute('aria-label') || labelledby
        || boxLabel || el.getAttribute('placeholder') || el.name || el.id || '';
    out.push({idx: String(i), tag: el.tagName.toLowerCase(), type, name: el.name || '', id: el.id || '',
              label: label.replace(/\\s+/g, ' ').trim().slice(0, 200), value: el.value || '',
              required: el.required || /\\*/.test(label),
              options: el.tagName === 'SELECT' ? [...el.options].map(o => o.text.trim()) : []});
  });
  return out;
}"""


def load_answers(path: Path | None = None) -> list[dict]:
    path = path or ROOT / SETTINGS["apply"]["answers"]
    return yaml.safe_load(path.read_text())["rules"]


def profile_values() -> dict:
    first, _, last = PROFILE["name"].partition(" ")
    return {"name": PROFILE["name"], "first_name": first, "last_name": last, "email": PROFILE["email"],
            "phone": PROFILE["phone"], "linkedin": PROFILE["links"].get("linkedin", ""),
            "github": PROFILE["links"].get("github", ""), "portfolio": PROFILE["links"].get("portfolio", "")
            or PROFILE["links"].get("github", ""), "grad_year": str(PROFILE["grad_year"])}


def answer_for(label: str, rules: list[dict], values: dict | None = None) -> str | None:
    """Value for a field label: str to fill, '' = leave for the human, None = no rule matched."""
    values = values or profile_values()
    for rule in rules:
        if re.search(rule["match"], label or "", re.I):
            return str(rule.get("value") or "").format(**values)
    return None


def draft_free_text(question: str, job: dict) -> str | None:
    """LLM draft for an open question ('Why do you want to join X?'). Validated: no skills you don't have."""
    if not llm.available("write"):
        return None
    text = llm.chat_text(
        "Answer this job-application question for a CS student in 60-120 words, first person, specific and honest. "
        "Use ONLY the facts provided. Never invent experience, metrics or tools.",
        json.dumps({"question": question, "job": {"title": job["title"], "company": job["company"],
                                                  "description": (job.get("jd_text") or "")[:2500]},
                    "profile": {k: PROFILE[k] for k in ("summary", "skills", "projects", "experience")}}))
    if not text or find_skills(text, ALL_SKILLS) - find_skills(json.dumps(PROFILE), ALL_SKILLS):
        return None
    return text


def application_url(url: str) -> str:
    """Jump straight to the form on boards that put it on a separate page."""
    u = url.rstrip("/")
    if "jobs.lever.co" in u and not u.endswith("/apply"):
        return u + "/apply"
    if "jobs.ashbyhq.com" in u and "/application" not in u:
        return u + "/application"
    return url


def fill_page(page, job: dict, resume_path: str | None, rules: list[dict], draft_answers: bool = True) -> dict:
    report = {"filled": [], "review": [], "skipped": []}
    page.wait_for_load_state("domcontentloaded")
    for _ in range(2):  # Greenhouse embeds and some boards need an "Apply" click to reveal the form
        if page.locator("input:visible, textarea:visible").count() > 2:
            break
        name = re.compile(r"^apply( now| for this job)?$", re.I)
        # Only buttons/links that *reveal* a form: never a submit button, never anything inside a form.
        candidates = [loc for loc in (page.get_by_role("link", name=name), page.get_by_role("button", name=name))
                      if loc.count() and not loc.first.evaluate("e => e.type === 'submit' || !!e.closest('form')")]
        if not candidates:
            break
        candidates[0].first.click()
        page.wait_for_timeout(1500)

    values = profile_values()
    for f in page.evaluate(DESCRIBE_FIELDS):
        el = page.locator(f'[data-ip-idx="{f["idx"]}"]')
        label = f["label"] or f["name"]
        try:
            if f["type"] == "file":
                if resume_path and RESUME_FIELD.search(f"{label} {f['name']} {f['id']}") and not COVER_FIELD.search(label):
                    el.set_input_files(resume_path)
                    report["filled"].append({"field": label or "resume", "value": Path(resume_path).name})
                continue
            if f["type"] in ("checkbox", "radio"):
                report["skipped"].append(label)
                continue
            if f["value"]:
                continue  # never overwrite what's already there
            value = answer_for(label, rules, values)
            needs_review = value == ""
            if value is None and f["tag"] == "textarea" and draft_answers:
                value = draft_free_text(label, job)
                needs_review = True
            if not value:
                if f["required"] or needs_review:
                    el.evaluate(REVIEW_STYLE)
                    report["review"].append(label)
                else:
                    report["skipped"].append(label)
                continue
            if f["tag"] == "select":
                opts, v = f["options"], value.lower()
                option = (next((o for o in opts if o.lower() == v), None)
                          or next((o for o in opts if o and (v in o.lower() or o.lower() in v)), None))
                if not option:
                    el.evaluate(REVIEW_STYLE)
                    report["review"].append(label)
                    continue
                el.select_option(label=option)
                value = option
            else:
                el.fill(value)
            if needs_review:
                el.evaluate(REVIEW_STYLE)
                report["review"].append(label)
            report["filled"].append({"field": label, "value": value[:80]})
        except Exception as e:  # one odd field shouldn't stop the rest
            log.info("could not fill %r: %s", label, e)
            report["skipped"].append(label)

    for sel in ("button[type=submit]", "input[type=submit]", "button:has-text('Submit')"):
        loc = page.locator(sel)
        for i in range(loc.count()):
            loc.nth(i).evaluate(SUBMIT_STYLE)
    return report


def wait_for_confirmation(page, minutes: int = 45) -> bool:
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        try:
            if page.is_closed():
                return False
            if CONFIRMED.search(page.inner_text("body", timeout=3000)):
                return True
        except Exception:
            return False
        time.sleep(3)
    return False


def run(job_id: str, headless: bool = False, wait: bool = True) -> dict:
    from playwright.sync_api import sync_playwright

    from ..tailor.service import resume_attachment

    db = DB()
    llm.use_db(db)
    job = db.job_with_match(job_id)
    name, pdf = resume_attachment(db, job_id)
    resume_path = OUTPUT_DIR / "apply" / name
    resume_path.parent.mkdir(parents=True, exist_ok=True)
    resume_path.write_bytes(pdf)

    with sync_playwright() as p:
        # Persistent profile: log in to Workday/LinkedIn etc. once and the browser remembers you.
        ctx = p.chromium.launch_persistent_context(str(OUTPUT_DIR / "browser-profile"), headless=headless, viewport=None)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(application_url(job["url"]), wait_until="domcontentloaded", timeout=60_000)
        report = fill_page(page, job, str(resume_path), load_answers())
        db.log("autofill", f"filled {len(report['filled'])}, review {len(report['review'])}", job_id)
        print(json.dumps(report, indent=2))
        confirmed = wait_for_confirmation(page) if wait else False
        if confirmed:
            db.set_status(job_id, "applied", applied_at=now())
            from ..notify import telegram
            import html
            telegram.send(html.escape(f"📨 Applied: {job['title']} @ {job['company']}"))
        report["confirmed"] = confirmed
        if wait:
            ctx.close()
    return report


def run_task(db: DB, task: dict) -> dict:
    """Start the browser in its own process so the worker keeps processing other tasks."""
    log_path = ROOT / "logs" / "autofill.log"
    log_path.parent.mkdir(exist_ok=True)
    proc = subprocess.Popen([sys.executable, "-m", "worker.apply.autofill", task["job_id"]], cwd=ROOT,
                            stdout=open(log_path, "a"), stderr=subprocess.STDOUT, start_new_session=True)
    return {"pid": proc.pid, "log": str(log_path)}


if __name__ == "__main__":
    from ..logsafe import setup
    setup()
    run(sys.argv[1])

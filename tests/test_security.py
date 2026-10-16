"""Security regressions: secrets never logged, untrusted text can't break or abuse notifications/links/probes."""
import logging

from worker import llm
from worker.logsafe import RedactingFormatter, redact
from worker.models import Job
from worker.notify import telegram
from worker.outreach.company import candidate_domains, public_hostname

TOKEN = "123456789:AAFakeTelegramTokenForTestsOnly000000"


def test_redacts_every_secret_kind():
    line = (f"GET https://api.telegram.org/bot{TOKEN}/getUpdates failed; key gsk_abcDEF1234567890 "
            "AIzaSyA1234567890abcdefghijk postgresql://postgres.ref:S3cret!@aws.pooler.supabase.com:5432/postgres "
            "Authorization: Bearer eyJhbGciOi.abc.def api_key=XYZ987654 refresh_token=1//0gABCDEFGHIJKLMNOPQRSTUV")
    out = redact(line)
    for secret in (TOKEN, "gsk_abcDEF", "AIzaSyA123", "S3cret!", "eyJhbGciOi", "XYZ987654", "1//0gABCDEF"):
        assert secret not in out, secret


def test_log_formatter_redacts_exceptions():
    fmt = RedactingFormatter("%(message)s")
    try:
        raise ConnectionError(f"Max retries exceeded with url: /bot{TOKEN}/getUpdates")
    except ConnectionError:
        import sys
        rec = logging.LogRecord("x", logging.WARNING, __file__, 1, "poll failed", None, sys.exc_info())
    assert TOKEN not in fmt.format(rec)


def test_json_mode_prompt_always_mentions_json(monkeypatch):
    seen = []
    monkeypatch.setattr(llm, "chain", lambda purpose: ["groq_small"])
    monkeypatch.setattr(llm, "under_cap", lambda *a: True)
    monkeypatch.setattr(llm, "_pace", lambda *a: None)
    monkeypatch.setattr(llm, "_call", lambda p, messages, *a: seen.append(messages) or ('{"kind": "oa"}', 10))
    assert llm.chat_json('Classify. Return {"kind": "oa"}', "email text", purpose="score") == {"kind": "oa"}
    assert "json" in seen[0][0]["content"].lower()


def test_telegram_falls_back_to_plain_text(monkeypatch):
    calls = []

    class R:
        def __init__(self, code, text=""):
            self.status_code, self.text = code, text

        def raise_for_status(self):
            if self.status_code >= 400:
                raise telegram.requests.HTTPError(self.status_code)

    def post(url, data, timeout):
        calls.append(dict(data))
        return R(400, "Bad Request: can't parse entities") if "parse_mode" in data else R(200)

    monkeypatch.setattr(telegram, "TELEGRAM_BOT_TOKEN", "x")
    monkeypatch.setattr(telegram, "TELEGRAM_CHAT_ID", "1")
    monkeypatch.setattr(telegram.requests, "post", post)
    assert telegram.send("<b>Intern</b> @ A<B & Co") is True
    assert "parse_mode" not in calls[1] and calls[1]["text"] == "Intern @ A<B & Co"


def test_format_match_escapes_untrusted_text():
    row = {"score": 90, "title": "<script>x</script> Intern", "company": "A&B", "location": "Pune",
           "reasons": '["<i>x</i>"]', "missing_skills": "[]", "source": "t"}
    text = telegram.format_match(row)
    assert "<script>" not in text and "&lt;script&gt;" in text and "A&amp;B" in text


def test_only_public_hostnames_are_probed():
    assert public_hostname("acme.com") and public_hostname("careers.foo.io")
    for bad in ("localhost", "127.0.0.1", "10.0.0.5", "[::1]", "intranet", "router.local", "x.internal"):
        assert not public_hostname(bad), bad
    assert all(public_hostname(d) for d in candidate_domains("Acme", "http://169.254.169.254/latest"))


def test_pipeline_drops_non_web_links(monkeypatch, make_db):
    from worker import pipeline
    db = make_db()
    good = Job("t", "Acme", "Backend Intern", "Pune, India", "https://acme.com/jobs/1", "Python")
    evil = Job("t", "Evil", "Security Intern", "Pune, India", "javascript:alert(1)", "Python")
    monkeypatch.setattr(pipeline, "fetch_all", lambda s: ([good, evil], {}))
    monkeypatch.setattr(telegram, "send", lambda *a, **k: True)
    pipeline.run_once(db)
    assert [r["url"] for r in db.query("select url from jobs")] == ["https://acme.com/jobs/1"]


def test_rewrites_that_change_meaning_are_rejected():
    from worker.config import PROFILE
    from worker.tailor.validate import check_bullet
    adieks = PROFILE["experience"][0]
    volt = next(p for p in PROFILE["projects"] if p["name"] == "VoltSentry")
    # Undersold (the live model once turned "Built…" into "Assisted in…") → rejected
    assert check_bullet("Assisted in building the backend of MoodSpace, a mood-tracking social app, with FastAPI, "
                        "SQLAlchemy and Alembic", adieks["bullets"][0], adieks)
    # Invented wording ("third-party fleets" appears nowhere in the profile) → rejected
    assert check_bullet("Built an inline OCPP 1.6-J security proxy that screens EV-charger traffic for third-party fleets",
                        volt["bullets"][0], volt)
    # Faithful shortening → accepted
    assert check_bullet("Secured the API with JWT access/refresh tokens and bcrypt (cost 12), and encrypted private "
                        "journal notes with AES-256-GCM", adieks["bullets"][1], adieks) is None


def test_parked_and_lookalike_domains_rejected():
    from worker.outreach.company import site_belongs_to
    parked = "<title>dexters.com</title><body>This domain may be for sale.</body>"
    assert not site_belongs_to("dexters.com", "Dexter's Tech", parked)
    assert not site_belongs_to("acme.com", "Acme Robotics", "<title>ACME Anvils</title>")
    assert site_belongs_to("fampay.in", "Fampay", "<title>FamApp</title><meta property='og:site_name' content='FamPay'>")
    assert site_belongs_to("kasparro.ai", "Kasparro AI", "<title>Kasparro</title>")


def test_email_prompt_forbids_company_claims_without_brief(monkeypatch):
    import json as _json
    from worker.outreach import draft
    seen = []
    monkeypatch.setattr(llm, "chat_json", lambda system, user, **k: seen.append(_json.loads(user)) or None)
    job = {"title": "Web Intern", "company": "Dexter's Tech", "jd_text": "HTML CSS JavaScript"}
    draft.llm_email(job, draft.PROFILE["projects"][0], None, "", "A")
    assert seen and seen[0]["company_brief"].startswith("NONE")

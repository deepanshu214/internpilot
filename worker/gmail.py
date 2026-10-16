"""Gmail API: send outreach (or write .eml files in dry-run mode) and read your inbox for application updates.
One-time auth: `.venv/bin/python scripts/gmail_auth.py` (opens a browser for Google consent)."""
import base64
import logging
import re
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, parsedate_to_datetime

from .config import DRY_RUN, GMAIL_CREDENTIALS, GMAIL_TOKEN, OUTBOX_DIR, PROFILE

log = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.readonly"]
_service = None


REAUTH = "cd ~/Desktop/internpilot && .venv/bin/python scripts/gmail_auth.py"
_expired_mtime: float | None = None  # token file mtime when Google rejected it


class AuthExpired(Exception):
    """Google revoked/expired the login (every 7 days while the Google app is in Testing). Re-run gmail_auth.py."""


def available() -> bool:
    if not GMAIL_TOKEN.exists():
        return False
    # A fresh login (new token file) clears an earlier expiry without restarting the worker.
    return _expired_mtime is None or GMAIL_TOKEN.stat().st_mtime != _expired_mtime


def expired() -> bool:
    return GMAIL_TOKEN.exists() and not available()


def _mark_expired():
    global _expired_mtime, _service
    _expired_mtime = GMAIL_TOKEN.stat().st_mtime if GMAIL_TOKEN.exists() else None
    _service = None


def _execute(request):
    from google.auth.exceptions import RefreshError
    try:
        return request.execute()
    except RefreshError as e:
        _mark_expired()
        raise AuthExpired(f"Gmail login expired: run {REAUTH}") from e


def service():
    global _service, _expired_mtime
    if _service is not None and _expired_mtime is not None and available():
        _service, _expired_mtime = None, None  # re-authorized since the expiry: rebuild with the new token
    if _service is None:
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN), SCOPES)
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as e:
                _mark_expired()
                raise AuthExpired(f"Gmail login expired: run {REAUTH}") from e
            GMAIL_TOKEN.write_text(creds.to_json())
            GMAIL_TOKEN.chmod(0o600)
        _service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    return _service


def authorize():
    """Interactive OAuth (run by scripts/gmail_auth.py)."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(GMAIL_CREDENTIALS), SCOPES)
    creds = flow.run_local_server(port=0)
    GMAIL_TOKEN.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    GMAIL_TOKEN.write_text(creds.to_json())
    GMAIL_TOKEN.chmod(0o600)
    return creds


def build_message(to: str, subject: str, body: str, attachments=(), in_reply_to: str | None = None,
                  sender_name: str | None = None) -> EmailMessage:
    """attachments: iterable of (filename, bytes, mime 'application/pdf')."""
    msg = EmailMessage()
    msg["To"] = to
    msg["From"] = formataddr((sender_name or PROFILE["name"], PROFILE["email"]))
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body)
    for filename, data, mime in attachments:
        maintype, subtype = mime.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    return msg


def send(to: str, subject: str, body: str, attachments=(), thread_id: str | None = None,
         in_reply_to: str | None = None, dry_run: bool = DRY_RUN) -> dict:
    """Returns {id, threadId, dry_run, path?}. In dry-run mode nothing leaves your machine."""
    msg = build_message(to, subject, body, attachments, in_reply_to)
    if dry_run:
        OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", f"{to}-{subject}".lower())[:60]
        path = OUTBOX_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{slug}.eml"
        path.write_bytes(bytes(msg))
        log.info("DRY RUN: wrote %s", path)
        return {"id": f"dryrun-{path.stem}", "threadId": thread_id or f"dryrun-{path.stem}", "dry_run": True,
                "path": str(path)}
    raw = base64.urlsafe_b64encode(bytes(msg)).decode()
    body_ = {"raw": raw}
    if thread_id:
        body_["threadId"] = thread_id
    sent = _execute(service().users().messages().send(userId="me", body=body_))
    return {"id": sent["id"], "threadId": sent.get("threadId"), "dry_run": False}


def search(query: str, max_results: int = 100) -> list[str]:
    """Message ids matching a Gmail search query (e.g. 'newer_than:14d from:greenhouse.io')."""
    ids, token = [], None
    while len(ids) < max_results:
        resp = _execute(service().users().messages().list(userId="me", q=query, pageToken=token,
                                                          maxResults=min(100, max_results - len(ids))))
        ids += [m["id"] for m in resp.get("messages", [])]
        token = resp.get("nextPageToken")
        if not token:
            break
    return ids


def thread_message_count(thread_id: str) -> int:
    t = _execute(service().users().threads().get(userId="me", id=thread_id, format="minimal"))
    return len(t.get("messages", []))


def get(message_id: str) -> dict:
    m = _execute(service().users().messages().get(userId="me", id=message_id, format="full"))
    return parse_message(m)


def parse_message(m: dict) -> dict:
    """Gmail API message resource → {id, threadId, from, to, subject, date, message_id, snippet, text, html}."""
    payload = m.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}
    texts, htmls = [], []

    def walk(part):
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and mime in ("text/plain", "text/html"):
            decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
            (texts if mime == "text/plain" else htmls).append(decoded)
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload)
    try:
        date = parsedate_to_datetime(headers.get("date", "")).isoformat()
    except (TypeError, ValueError):
        date = None
    return {"id": m.get("id"), "threadId": m.get("threadId"), "from": headers.get("from", ""),
            "to": headers.get("to", ""), "subject": headers.get("subject", ""), "date": date,
            "message_id": headers.get("message-id"), "snippet": m.get("snippet", ""),
            "text": "\n".join(texts), "html": "\n".join(htmls)}

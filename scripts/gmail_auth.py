"""One-time Gmail authorization. Needs secrets/gmail_credentials.json (OAuth "Desktop app" client from
Google Cloud Console, see SETUP_TONIGHT.md). Opens your browser for consent and saves secrets/gmail_token.json."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from worker import gmail  # noqa: E402
from worker.config import GMAIL_CREDENTIALS  # noqa: E402

if not GMAIL_CREDENTIALS.exists():
    sys.exit(f"Missing {GMAIL_CREDENTIALS}. Download the OAuth client JSON there first.")
gmail.authorize()
profile = gmail.service().users().getProfile(userId="me").execute()
print(f"Authorized as {profile['emailAddress']} ({profile['messagesTotal']} messages).")

import os
import json
import base64
import tempfile

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

# In-memory token for Render (non-persistent)
_MEMORY_CREDS = None


def _load_client_secret_file():
    """
    Returns a path to a client_secret.json file.
    - If GOOGLE_CREDENTIALS_JSON env var exists, writes it to a temp file and returns that path.
    - Else falls back to local credentials.json (for development).
    """
    env_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")

    if env_json:
        data = json.loads(env_json)
        tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json")
        json.dump(data, tmp)
        tmp.flush()
        tmp.close()
        return tmp.name

    # Local dev fallback
    if os.path.exists("credentials.json"):
        return "credentials.json"

    raise RuntimeError(
        "Missing OAuth client secrets. "
        "Set GOOGLE_CREDENTIALS_JSON on Render or provide credentials.json locally."
    )


def _get_service():
    """
    Builds and returns Gmail API service.
    Token handling:
    - Local: uses token.json for persistence
    - Render: uses in-memory creds (token resets on restart)
    """
    global _MEMORY_CREDS
    creds = None

    running_on_render = bool(os.environ.get("RENDER")) or bool(os.environ.get("RENDER_SERVICE_ID"))

    # ---------- Load existing token ----------
    if running_on_render:
        # Render: in-memory token only
        creds = _MEMORY_CREDS
    else:
        # Local: use token.json
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # ---------- Refresh / Login ----------
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            client_secret_path = _load_client_secret_file()
            flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES)

            # IMPORTANT:
            # For Render, run_local_server opens a local port on the server (not accessible to you).
            # This will NOT work unless you change to a web-based OAuth flow.
            # For now, keep this working locally, and we'll convert to web OAuth for Render next.
            creds = flow.run_local_server(port=0)

        # ---------- Save token ----------
        if running_on_render:
            _MEMORY_CREDS = creds
        else:
            with open("token.json", "w") as token:
                token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def fetch_emails(max_results=10):
    service = _get_service()
    res = service.users().messages().list(
        userId="me",
        labelIds=["INBOX"],
        maxResults=max_results
    ).execute()

    messages = res.get("messages", [])
    out = []

    for m in messages:
        msg_id = m["id"]
        msg = service.users().messages().get(
            userId="me",
            id=msg_id,
            format="metadata",
            metadataHeaders=["From", "Subject"]
        ).execute()

        headers = msg.get("payload", {}).get("headers", [])
        snippet = msg.get("snippet", "")

        sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "Unknown")
        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "No subject")

        out.append({
            "id": msg_id,
            "threadId": msg.get("threadId"),
            "sender": sender,
            "subject": subject,
            "snippet": snippet
        })

    return out


def fetch_email_body(message_id):
    service = _get_service()
    msg = service.users().messages().get(
        userId="me",
        id=message_id,
        format="full"
    ).execute()

    def _walk(parts):
        for p in parts or []:
            mime = p.get("mimeType", "")
            body = p.get("body", {}).get("data")
            if mime == "text/plain" and body:
                return body
            nested = _walk(p.get("parts"))
            if nested:
                return nested
        return None

    payload = msg.get("payload", {})
    data = payload.get("body", {}).get("data") or _walk(payload.get("parts"))

    if not data:
        return msg.get("snippet", "")

    decoded = base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="ignore")
    return decoded

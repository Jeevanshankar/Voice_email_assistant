import os
import json
import base64
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

# Default redirect (Render production)
REDIRECT_URI = os.environ.get(
    "OAUTH_REDIRECT_URI",
    "https://voxmail.onrender.com/oauth2callback"
)


# ==============================
# OAuth Flow Builder
# ==============================
def _get_flow():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        raise Exception("Missing GOOGLE_CREDENTIALS_JSON environment variable")

    client_config = json.loads(creds_json)

    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )

    return flow


# ==============================
# Save token.json
# ==============================
def save_token(creds_json_string):
    with open("token.json", "w") as token:
        token.write(creds_json_string)


# ==============================
# Gmail Service Builder
# ==============================
def _get_service():
    creds = None

    # Load existing token
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    # If no valid creds → refresh or require login
    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            save_token(creds.to_json())

        else:
            flow = _get_flow()
            auth_url, _ = flow.authorization_url(
                access_type="offline",
                prompt="consent"
            )

            # IMPORTANT: Must match app.py expectation
            raise Exception(f"AUTH_REQUIRED::{auth_url}")

    return build("gmail", "v1", credentials=creds)


# ==============================
# Fetch Email List
# ==============================
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

        sender = next(
            (h["value"] for h in headers if h["name"].lower() == "from"),
            "Unknown"
        )

        subject = next(
            (h["value"] for h in headers if h["name"].lower() == "subject"),
            "No subject"
        )

        out.append({
            "id": msg_id,
            "threadId": msg.get("threadId"),
            "sender": sender,
            "subject": subject,
            "snippet": snippet
        })

    return out


# ==============================
# Fetch Full Email Body
# ==============================
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

    decoded = base64.urlsafe_b64decode(
        data.encode("utf-8")
    ).decode("utf-8", errors="ignore")

    return decoded

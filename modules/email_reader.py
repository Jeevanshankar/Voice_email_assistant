import os, base64
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]

def _get_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)

def fetch_emails(max_results=5):
    service = _get_service()
    res = service.users().messages().list(userId="me", maxResults=max_results).execute()
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
    msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()

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

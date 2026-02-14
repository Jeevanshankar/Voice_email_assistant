import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from modules.email_reader import _get_service


def send_email(to_email: str, subject: str, body: str):
    service = _get_service()

    msg = MIMEMultipart()
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    sent = service.users().messages().send(
        userId="me",
        body={"raw": raw}
    ).execute()

    return {"id": sent.get("id"), "threadId": sent.get("threadId")}


def reply_email(to_email: str, subject: str, body: str, thread_id: str = None):
    """
    Simple reply:
    - If you pass thread_id, Gmail will group it in that thread.
    - For perfect threading, you'd also add In-Reply-To/References using Message-ID,
      but thread_id alone is good enough for most cases.
    """
    service = _get_service()

    msg = MIMEMultipart()
    msg["To"] = to_email
    msg["Subject"] = f"Re: {subject}" if subject else "Re:"
    msg.attach(MIMEText(body, "plain", "utf-8"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    payload = {"raw": raw}
    if thread_id:
        payload["threadId"] = thread_id

    sent = service.users().messages().send(
        userId="me",
        body=payload
    ).execute()

    return {"id": sent.get("id"), "threadId": sent.get("threadId")}

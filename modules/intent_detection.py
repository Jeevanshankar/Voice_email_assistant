import re

def detect_intent(text):
    # ==========================
    # SAFETY CHECK
    # ==========================
    if not text:
        return {"intent": "unknown", "message": None, "recipient": None}

    text = str(text).lower().strip()

    # Fix common Whisper mis-hearings
    text = text.replace("minebox", "inbox")
    text = text.replace("mail box", "inbox")
    text = text.replace("mailbox", "inbox")

    intent_data = {
        "intent": "unknown",
        "message": None,
        "recipient": None
    }

    # ==========================
    # READ INBOX
    # ==========================
    if any(word in text for word in ["inbox", "emails", "email", "mails"]):
        if any(word in text for word in ["read", "open", "check", "show"]):
            intent_data["intent"] = "read_inbox"
            return intent_data

    # ==========================
    # NEXT EMAIL
    # ==========================
    if any(word in text for word in ["next", "forward"]):
        intent_data["intent"] = "next_email"
        return intent_data

    # ==========================
    # PREVIOUS EMAIL
    # ==========================
    if any(word in text for word in ["previous", "back", "before"]):
        intent_data["intent"] = "previous_email"
        return intent_data

    # ==========================
    # OPEN CURRENT EMAIL (FULL BODY)
    # ==========================
    if "open" in text and ("email" in text or "mail" in text):
        intent_data["intent"] = "open_email"
        return intent_data


    # ==========================
    # READ EMAIL NUMBER
    # ==========================
    match = re.search(r"(email|mail) (number )?(\d+)", text)
    if match:
        intent_data["intent"] = "read_email_number"
        intent_data["number"] = int(match.group(3))
        return intent_data
    

    # ==========================
    # SEND EMAIL
    # ==========================
    if "send" in text and "email" in text:
        match = re.search(r"send email to (.+?) saying (.+)", text)
        if match:
            intent_data["recipient"] = match.group(1).strip()
            intent_data["message"] = match.group(2).strip()
        intent_data["intent"] = "send_email"
        return intent_data

    # ==========================
    # SUMMARIZE
    # ==========================
    if any(word in text for word in ["summarize", "summary"]):
        intent_data["intent"] = "summarize_email"
        return intent_data

    # ==========================
    # REPLY
    # ==========================
    if "reply" in text:
        match = re.search(r"reply (.+)", text)
        if match:
            intent_data["message"] = match.group(1).strip()
        intent_data["intent"] = "reply_email"
        return intent_data

    return intent_data

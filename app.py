from flask import Flask, render_template, request, jsonify
import os
import re

from modules.speech_recognition import transcribe_audio
from modules.intent_detection import detect_intent

from modules.email_reader import fetch_emails, fetch_email_body
from modules.email_sender import send_email as gmail_send_email
from modules.email_sender import reply_email as gmail_reply_email

from modules.summarizer import summarize_text

app = Flask(__name__)

# ====== EMAIL MEMORY STORAGE ======
EMAIL_CACHE = []
CURRENT_INDEX = 0


# ====== SERVE FRONTEND ======
@app.route("/")
def home():
    try:
        return render_template("index.html")
    except Exception as e:
        return jsonify({"error": f"Failed to render index.html: {str(e)}"}), 500


# ====== SPEECH TO TEXT ENDPOINT ======
@app.route("/api/stt", methods=["POST"])
def speech_to_text():
    try:
        if "audio" not in request.files:
            return jsonify({"error": "No audio uploaded"}), 400

        audio_file = request.files["audio"]
        temp_path = "uploaded_audio.webm"
        audio_file.save(temp_path)

        try:
            text = transcribe_audio(temp_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        return jsonify({"text": text})

    except Exception as e:
        return jsonify({"error": f"STT failed: {str(e)}"}), 500


# ====== INTENT PROCESSING ENDPOINT ======
@app.route("/api/intent", methods=["POST"])
def get_intent():
    try:
        data = request.get_json(force=True) or {}
        text = data.get("text", "")

        intent_data = detect_intent(text)

        # Return only the keys frontend needs
        resp = {
            "intent": intent_data.get("intent"),
            "message": intent_data.get("message"),
            "recipient": intent_data.get("recipient"),
        }

        # Optional keys
        if "number" in intent_data:
            resp["number"] = intent_data["number"]
        if "subject" in intent_data:
            resp["subject"] = intent_data["subject"]

        return jsonify(resp)

    except Exception as e:
        return jsonify({"error": f"Intent detection failed: {str(e)}"}), 500


# ====== ACTION ENDPOINT ======
@app.route("/api/action", methods=["POST"])
def email_action():
    global EMAIL_CACHE, CURRENT_INDEX
    try:
        data = request.get_json(force=True) or {}
        print("Received /api/action:", data)

        intent = (data.get("intent") or "").strip()
        message = data.get("message")
        recipient = data.get("recipient")
        number = data.get("number")
        subject = data.get("subject")  # optional

        if not intent:
            return jsonify({"error": "Missing intent"}), 400

        # ==========================
        # READ INBOX
        # ==========================
        if intent == "read_inbox":
            EMAIL_CACHE = fetch_emails(max_results=5) or []
            CURRENT_INDEX = 0
            return jsonify({
                "intent": "read_inbox",
                "emails": EMAIL_CACHE,
                "index": CURRENT_INDEX
            })

        # ==========================
        # NEXT EMAIL
        # ==========================
        if intent == "next_email":
            if not EMAIL_CACHE:
                return jsonify({"error": "Inbox empty. Say 'read my inbox' first."}), 400
            CURRENT_INDEX = min(CURRENT_INDEX + 1, len(EMAIL_CACHE) - 1)
            return jsonify({
                "intent": "next_email",
                "email": EMAIL_CACHE[CURRENT_INDEX],
                "index": CURRENT_INDEX
            })

        # ==========================
        # PREVIOUS EMAIL
        # ==========================
        if intent == "previous_email":
            if not EMAIL_CACHE:
                return jsonify({"error": "Inbox empty. Say 'read my inbox' first."}), 400
            CURRENT_INDEX = max(CURRENT_INDEX - 1, 0)
            return jsonify({
                "intent": "previous_email",
                "email": EMAIL_CACHE[CURRENT_INDEX],
                "index": CURRENT_INDEX
            })

        # ==========================
        # READ EMAIL NUMBER (1..N)
        # ==========================
        if intent == "read_email_number":
            if not EMAIL_CACHE:
                return jsonify({"error": "Inbox empty. Say 'read my inbox' first."}), 400
            if not isinstance(number, int):
                return jsonify({"error": "No valid email number provided. Say: 'email 2' or 'email number 2'."}), 400
            if number < 1 or number > len(EMAIL_CACHE):
                return jsonify({"error": f"Email number must be between 1 and {len(EMAIL_CACHE)}"}), 400

            CURRENT_INDEX = number - 1
            return jsonify({
                "intent": "read_email_number",
                "email": EMAIL_CACHE[CURRENT_INDEX],
                "index": CURRENT_INDEX
            })

        # ==========================
        # OPEN CURRENT EMAIL (FULL BODY)
        # ==========================
        if intent == "open_email":
            if not EMAIL_CACHE:
                return jsonify({"error": "Inbox empty. Say 'read my inbox' first."}), 400

            msg_id = EMAIL_CACHE[CURRENT_INDEX].get("id")
            if not msg_id:
                return jsonify({"error": "No message id found for current email."}), 500

            body = fetch_email_body(msg_id)
            return jsonify({
                "intent": "open_email",
                "email": EMAIL_CACHE[CURRENT_INDEX],
                "index": CURRENT_INDEX,
                "body": body
            })

        # ==========================
        # SUMMARIZE CURRENT EMAIL (REAL)
        # ==========================
        if intent == "summarize_email":
            if not EMAIL_CACHE:
                return jsonify({"error": "Inbox empty. Say 'read my inbox' first."}), 400

            msg_id = EMAIL_CACHE[CURRENT_INDEX].get("id")
            if not msg_id:
                return jsonify({"error": "No message id found for current email."}), 500

            body = fetch_email_body(msg_id)
            summary = summarize_text(body)

            return jsonify({
                "intent": "summarize_email",
                "email": EMAIL_CACHE[CURRENT_INDEX],
                "index": CURRENT_INDEX,
                "summary": summary
            })

        # ==========================
        # SEND EMAIL (REAL)
        # ==========================
        if intent == "send_email":
            to = recipient
            body = message
            subj = subject or "Voice Email Assistant"

            if not to or "@" not in to:
                return jsonify({"error": "Recipient must be an email address for now (example: abc@gmail.com)."}), 400
            if not body:
                return jsonify({"error": "Missing email message body."}), 400

            result = gmail_send_email(to, subj, body)
            return jsonify({"intent": "send_email", "status": "sent", "details": result})

        # ==========================
        # REPLY EMAIL (REAL)
        # ==========================
        if intent == "reply_email":
            if not EMAIL_CACHE:
                return jsonify({"error": "Inbox empty. Say 'read my inbox' first."}), 400
            if not message:
                return jsonify({"error": "Missing reply message."}), 400

            current = EMAIL_CACHE[CURRENT_INDEX]
            sender_field = current.get("sender", "")

            # Extract email from "Name <email@x.com>"
            m = re.search(r"<([^>]+)>", sender_field)
            to = m.group(1) if m else sender_field

            if not to or "@" not in to:
                return jsonify({"error": f"Could not extract a valid email address from sender: {sender_field}"}), 400

            result = gmail_reply_email(to, current.get("subject", ""), message)
            return jsonify({"intent": "reply_email", "status": "sent", "details": result})

        return jsonify({"error": f"Unknown intent: {intent}"}), 400

    except Exception as e:
        print("Exception in /api/action:", str(e))
        return jsonify({"error": f"Server error: {str(e)}"}), 500


# ====== RUN SERVER ======
if __name__ == "__main__":
    app.run(debug=True)

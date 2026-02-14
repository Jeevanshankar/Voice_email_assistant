from flask import Flask, render_template, request, jsonify, redirect, session
import re
import os
import json

from werkzeug.middleware.proxy_fix import ProxyFix
from google_auth_oauthlib.flow import Flow

from modules.intent_detection import detect_intent
from modules.email_reader import fetch_emails, fetch_email_body, save_token
from modules.email_sender import send_email as gmail_send_email
from modules.email_sender import reply_email as gmail_reply_email

app = Flask(__name__)

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change_this_secret")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

EMAIL_CACHE = []
CURRENT_INDEX = 0

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


def _client_config():
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not raw:
        raise RuntimeError("Missing GOOGLE_CREDENTIALS_JSON in Render environment.")

    cfg = json.loads(raw)

    if "web" not in cfg:
        raise RuntimeError("OAuth JSON must be Web application type.")

    return cfg


def _redirect_uri():
    return request.url_root.rstrip("/") + "/oauth2callback"


def _build_auth_url():
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=_redirect_uri(),
    )

    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    session["oauth_state"] = state
    return auth_url


def _auth_required_response():
    return jsonify({
        "error": "AUTH_REQUIRED",
        "auth_url": _build_auth_url()
    }), 401


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/oauth2callback")
def oauth2callback():
    try:
        state = request.args.get("state")
        expected_state = session.get("oauth_state")

        if expected_state and state != expected_state:
            return "OAuth state mismatch", 400

        code = request.args.get("code")
        if not code:
            return "Missing OAuth code", 400

        flow = Flow.from_client_config(
            _client_config(),
            scopes=SCOPES,
            redirect_uri=_redirect_uri(),
            state=state
        )

        flow.fetch_token(code=code)
        creds = flow.credentials

        # ✅ SAVE CREDENTIAL OBJECT (not string)
        save_token(creds)

        return redirect("/")

    except Exception as e:
        return f"OAuth failed: {str(e)}", 500


@app.route("/api/intent", methods=["POST"])
def get_intent():
    data = request.get_json(force=True) or {}
    text = data.get("text", "")
    intent_data = detect_intent(text)

    return jsonify(intent_data)


@app.route("/api/action", methods=["POST"])
def email_action():
    global EMAIL_CACHE, CURRENT_INDEX

    try:
        data = request.get_json(force=True) or {}
        intent = (data.get("intent") or "").strip()
        message = data.get("message")
        recipient = data.get("recipient")
        number = data.get("number")
        subject = data.get("subject")

        if not intent:
            return jsonify({"error": "Missing intent"}), 400

        # Require OAuth if token not present
        if intent in [
            "read_inbox", "next_email", "previous_email",
            "read_email_number", "open_email",
            "send_email", "reply_email"
        ]:
            if not os.path.exists("token.json"):
                return _auth_required_response()

        if intent == "read_inbox":
            EMAIL_CACHE = fetch_emails(max_results=10) or []
            CURRENT_INDEX = 0
            return jsonify({"emails": EMAIL_CACHE})

        if intent == "next_email":
            CURRENT_INDEX = min(CURRENT_INDEX + 1, len(EMAIL_CACHE) - 1)
            return jsonify({"email": EMAIL_CACHE[CURRENT_INDEX]})

        if intent == "previous_email":
            CURRENT_INDEX = max(CURRENT_INDEX - 1, 0)
            return jsonify({"email": EMAIL_CACHE[CURRENT_INDEX]})

        if intent == "read_email_number":
            if not isinstance(number, int):
                return jsonify({"error": "Say: email 2"}), 400

            CURRENT_INDEX = number - 1
            return jsonify({"email": EMAIL_CACHE[CURRENT_INDEX]})

        if intent == "open_email":
            msg_id = EMAIL_CACHE[CURRENT_INDEX].get("id")
            body = fetch_email_body(msg_id)
            return jsonify({"body": body})

        if intent == "send_email":
            if not recipient or "@" not in recipient:
                return jsonify({"error": "Invalid email address"}), 400

            result = gmail_send_email(
                recipient,
                subject or "Voice Email Assistant",
                message
            )
            return jsonify({"status": "sent", "details": result})

        if intent == "reply_email":
            current = EMAIL_CACHE[CURRENT_INDEX]
            sender_field = current.get("sender", "")

            m = re.search(r"<([^>]+)>", sender_field)
            to = m.group(1) if m else sender_field

            result = gmail_reply_email(
                to,
                current.get("subject", ""),
                message,
                thread_id=current.get("threadId")
            )

            return jsonify({"status": "sent", "details": result})

        return jsonify({"error": "Unknown intent"}), 400

    except Exception as e:
        err = str(e)

        print("Exception in /api/action:", err)

        if "AUTH_REQUIRED" in err:
            return jsonify({
            "error": "AUTH_REQUIRED",
            "auth_url": _build_auth_url()
        }), 401

    return jsonify({
        "error": "SERVER_ERROR",
        "message": err
    }), 500

if __name__ == "__main__":
    app.run()

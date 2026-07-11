# api/index.py
from flask import Flask, request
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
from datetime import date
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
slack_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
verifier = SignatureVerifier(signing_secret=os.getenv("SLACK_SIGNING_SECRET"))

def verify_slack_request(request) -> bool:
    body = request.get_data()
    headers = request.headers
    return verifier.is_valid_request(body, headers)

@app.route("/")
def health_check():
    return "TaskLoop is alive"

@app.route("/slack/commands", methods=["POST"])
def slack_commands():
    if not verify_slack_request(request):
        return "Invalid request", 403

    trigger_id = request.form.get("trigger_id")

    modal_view = {
        "type": "modal",
        "callback_id": "transcript_submission",
        "title": {"type": "plain_text", "text": "TaskLoop", "emoji": True},
        "submit": {"type": "plain_text", "text": "Submit", "emoji": True},
        "close": {"type": "plain_text", "text": "Cancel", "emoji": True},
        "blocks": [
            {
                "type": "input",
                "block_id": "datepicker_block",
                "label": {"type": "plain_text", "text": "Select a meeting date"},
                "element": {
                    "type": "datepicker",
                    "action_id": "datepicker_action",
                    "initial_date": date.today().isoformat(),
                    "placeholder": {"type": "plain_text", "text": "Select a date"}
                }
            },
            {
                "type": "input",
                "block_id": "transcript_block",
                "label": {"type": "plain_text", "text": "Paste your meeting transcript"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "transcript_input",
                    "multiline": True
                }
            }
        ]
    }

    slack_client.views_open(trigger_id=trigger_id, view=modal_view)
    return "", 200
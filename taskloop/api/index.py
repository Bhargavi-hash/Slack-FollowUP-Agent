from flask import Flask, request
from verify import verify_slack_request
from slack_sdk import WebClient
from datetime import date
import os

app = Flask(__name__)
slack_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))

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
        "submit": {"type": "plain_text", "text": "Extract", "emoji": True},
        "close": {"type": "plain_text", "text": "Cancel", "emoji": True},
        "blocks": [
            {
                "type": "input",
                "block_id": "transcript_block",
                "label": {"type": "plain_text", "text": "Paste your transcript"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "transcript_input",
                    "multiline": True
                }
            },
            {
                "type": "input",
                "block_id": "datepicker_block",
                "label": {"type": "plain_text", "text": "Select a date"},
                "element": {
                    "type": "datepicker",
                    "action_id": "datepicker_action",
                    "initial_date": date.today().isoformat(),
                    "placeholder": {"type": "plain_text", "text": "Select a date"}
                }
            }
        ]
    }

    slack_client.views_open(trigger_id=trigger_id, view=modal_view)
    return "", 200
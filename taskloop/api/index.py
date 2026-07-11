import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from flask import Flask, request, redirect
import requests
from slack_sdk import WebClient
from slack_sdk.signature import SignatureVerifier
from datetime import date
from extraction import extract_action_items
from resolution import resolve_owner
from posting import post_action_item
from token_store import save_installation
from qstash import QStash, Receiver
import json
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
slack_client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))
qstash_client = QStash(
    os.getenv("QSTASH_TOKEN"),
    base_url="https://qstash-us-east-1.upstash.io"
)
verifier = SignatureVerifier(signing_secret=os.getenv("SLACK_SIGNING_SECRET"))

current_key = os.getenv("QSTASH_CURRENT_SIGNING_KEY")
next_key = os.getenv("QSTASH_NEXT_SIGNING_KEY")
print(f"DEBUG - current_key present: {bool(current_key)}, starts with: {current_key[:8] if current_key else None}")
print(f"DEBUG - next_key present: {bool(next_key)}, starts with: {next_key[:8] if next_key else None}")

qstash_receiver = Receiver(
    current_signing_key=current_key,
    next_signing_key=next_key,
)


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
    channel_id = request.form.get("channel_id")

    modal_view = {
        "type": "modal",
        "callback_id": "transcript_submission",
        "private_metadata": channel_id,
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

@app.route("/slack/interactivity", methods=["POST"])
def slack_interactivity():
    if not verify_slack_request(request):
        return "Invalid request", 403

    payload = json.loads(request.form.get("payload"))

    transcript = payload["view"]["state"]["values"]["transcript_block"]["transcript_input"]["value"]
    meeting_date = payload["view"]["state"]["values"]["datepicker_block"]["datepicker_action"]["selected_date"]
    channel_id = payload["view"]["private_metadata"]

    qstash_client.message.publish_json(
        url="https://slack-follow-up-agent.vercel.app/slack/process",
        body={
            "transcript": transcript,
            "meeting_date": meeting_date,
            "channel_id": channel_id
        }
    )

    return "", 200


@app.route("/slack/process", methods=["POST"])
def slack_process():
    
    signature = request.headers.get("Upstash-Signature") or request.headers.get("upstash-signature")
    body = request.get_data(as_text=True)

    try:
        qstash_receiver.verify(signature=signature, body=body, url="https://slack-follow-up-agent.vercel.app/slack/process")
    except Exception as e:
        print(f"QSTASH VERIFY FAILED: {type(e).__name__}: {e}")
        return "Invalid Request", 403

    data = request.get_json()

    transcript = data["transcript"]
    meeting_date = data["meeting_date"]
    channel_id = data["channel_id"]

    items = extract_action_items(transcript, meeting_date)
    for item in items:
        resolution = resolve_owner(item["owner_name"])
        post_action_item(channel_id, item["task"], resolution, item.get("due_date"))

    return "", 200


@app.route("/slack/install")
def slack_install():
    client_id = os.getenv("SLACK_CLIENT_ID")
    redirect_uri = "https://slack-follow-up-agent.vercel.app/slack/oauth_redirect"
    scopes = "chat:write"  # bot scopes
    user_scopes = "chat:write,canvases:write"  # user scopes, per your manifest

    slack_auth_url = (
        f"https://slack.com/oauth/v2/authorize"
        f"?client_id={client_id}"
        f"&scope={scopes}"
        f"&user_scope={user_scopes}"
        f"&redirect_uri={redirect_uri}"
    )

    return redirect(slack_auth_url)

@app.route("/slack/oauth_redirect")
def slack_oauth_redirect():
    code = request.args.get("code")

    response = requests.post("https://slack.com/api/oauth.v2.access", data={
        "client_id": os.getenv("SLACK_CLIENT_ID"),
        "client_secret": os.getenv("SLACK_CLIENT_SECRET"),
        "code": code,
        "redirect_uri": "https://slack-follow-up-agent.vercel.app/slack/oauth_redirect"
    })
    data = response.json()

    if not data.get("ok"):
        return f"Installation failed: {data.get('error')}", 400

    bot_token = data['access_token']
    user_token = data['authed_user']['access_token']
    team_id = data['team']['id']   

    save_installation(team_id=team_id, bot_token=bot_token, user_token=user_token)

    return f"Installation successful! Team ID: {team_id}. You can close this tab."
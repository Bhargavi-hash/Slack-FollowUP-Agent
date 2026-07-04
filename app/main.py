from __future__ import annotations

import logging
import os
from datetime import date
from typing import Dict, List

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from extraction.extract_actions import extract_actions
from posting.post_items import post_action_items
from resolution.resolve_owner import resolve_items_owners


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def _lookup_slack_users_with_mcp(owner_name: str) -> List[Dict[str, str]]:
    """
    Placeholder for Slack official MCP server lookup.
    Replace with the concrete MCP client call to mcp.slack.com user lookup tool.
    """
    logger.info("MCP lookup requested for owner: %s", owner_name)
    return []


def _build_modal(trigger_id: str) -> Dict[str, object]:
    return {
        "type": "modal",
        "callback_id": "extract_actions_submit",
        "title": {"type": "plain_text", "text": "Extract Actions"},
        "submit": {"type": "plain_text", "text": "Extract"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": trigger_id,
        "blocks": [
            {
                "type": "input",
                "block_id": "meeting_date_block",
                "label": {"type": "plain_text", "text": "When did this meeting happen?"},
                "element": {
                    "type": "datepicker",
                    "action_id": "meeting_date",
                    "initial_date": date.today().isoformat(),
                },
            },
            {
                "type": "input",
                "block_id": "transcript_block",
                "label": {"type": "plain_text", "text": "Transcript"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "transcript_input",
                    "multiline": True,
                    "placeholder": {"type": "plain_text", "text": "Paste transcript text here"},
                },
            },
        ],
    }


def create_app() -> App:
    app = App(token=os.environ["SLACK_BOT_TOKEN"], signing_secret=os.environ["SLACK_SIGNING_SECRET"])

    @app.command("/extract-actions")
    def handle_extract_actions_command(ack, body, client):
        ack()
        client.views_open(trigger_id=body["trigger_id"], view=_build_modal(body["channel_id"]))

    @app.view("extract_actions_submit")
    def handle_extract_actions_submit(ack, body, client, logger):
        ack()

        state = body["view"]["state"]["values"]
        transcript = state["transcript_block"]["transcript_input"]["value"]
        meeting_date_raw = state["meeting_date_block"]["meeting_date"]["selected_date"]
        meeting_date = date.fromisoformat(meeting_date_raw)

        channel_id = body["view"].get("private_metadata")
        if not channel_id:
            logger.error("Missing channel id in modal metadata")
            return

        extracted_items = extract_actions(transcript=transcript, meeting_date=meeting_date)
        resolved_items = resolve_items_owners(extracted_items, _lookup_slack_users_with_mcp)
        post_action_items(client=client, channel_id=channel_id, items=resolved_items)

    return app


if __name__ == "__main__":
    bolt_app = create_app()
    app_token = os.environ.get("SLACK_APP_TOKEN")
    if not app_token:
        raise RuntimeError("SLACK_APP_TOKEN is required for Socket Mode")
    SocketModeHandler(bolt_app, app_token).start()

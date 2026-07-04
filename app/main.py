from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import date
from typing import Dict, List, Optional

import requests
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from extraction.extract_actions import extract_actions
from posting.post_items import post_action_items
from resolution.resolve_owner import resolve_items_owners


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

SLACK_MCP_URL = "https://mcp.slack.com/mcp"
SLACK_MCP_PROTOCOL_VERSION = "2025-06-18"
SLACK_MCP_USER_SEARCH_TOOL = "slack_search_users"


def _mcp_call(method: str, params: Optional[dict], session_id: Optional[str] = None) -> requests.Response:
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN is not set")

    body = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method}
    if params is not None:
        body["params"] = params

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    response = requests.post(SLACK_MCP_URL, json=body, headers=headers, timeout=10)
    response.raise_for_status()
    return response


def _mcp_result(response: requests.Response, request_id: str) -> dict:
    content_type = response.headers.get("Content-Type", "")
    if "text/event-stream" in content_type:
        payload = None
        for line in response.text.splitlines():
            if not line.startswith("data:"):
                continue
            chunk = json.loads(line[len("data:"):].strip())
            if chunk.get("id") == request_id:
                payload = chunk
        if payload is None:
            raise RuntimeError("No matching JSON-RPC response found in MCP event stream")
    else:
        payload = response.json()

    if "error" in payload:
        raise RuntimeError(f"Slack MCP error: {payload['error']}")
    return payload.get("result", {})


def _normalize_mcp_user(user: dict) -> Dict[str, str]:
    profile = user.get("profile") if isinstance(user.get("profile"), dict) else {}
    return {
        "id": user.get("id", ""),
        "name": user.get("name", ""),
        "real_name": user.get("real_name") or profile.get("real_name", ""),
        "display_name": profile.get("display_name") or user.get("display_name", ""),
    }


def _lookup_slack_users_with_mcp(owner_name: str) -> List[Dict[str, str]]:
    """
    Looks up Slack users by name via Slack's official MCP server (mcp.slack.com),
    using the slack_search_users tool over JSON-RPC 2.0 / Streamable HTTP.
    Requires the search:read.users bot scope in addition to chat:write/commands.
    """
    logger.info("MCP lookup requested for owner: %s", owner_name)

    try:
        init_response = _mcp_call(
            "initialize",
            {
                "protocolVersion": SLACK_MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "slack-followup-agent", "version": "1.0.0"},
            },
        )
        session_id = init_response.headers.get("Mcp-Session-Id")
        _mcp_result(init_response, json.loads(init_response.request.body)["id"])

        search_response = _mcp_call(
            "tools/call",
            {"name": SLACK_MCP_USER_SEARCH_TOOL, "arguments": {"query": owner_name}},
            session_id=session_id,
        )
        result = _mcp_result(search_response, json.loads(search_response.request.body)["id"])

        if result.get("isError"):
            raise RuntimeError(f"{SLACK_MCP_USER_SEARCH_TOOL} tool error: {result}")

        users: List[dict] = []
        for block in result.get("content", []):
            if block.get("type") != "text":
                continue
            try:
                parsed = json.loads(block["text"])
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(parsed, list):
                users.extend(parsed)
            elif isinstance(parsed, dict):
                users.extend(parsed.get("users") or parsed.get("results") or [])

        return [_normalize_mcp_user(user) for user in users if isinstance(user, dict)]
    except Exception:
        logger.exception("Slack MCP user lookup failed for owner: %s", owner_name)
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

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import date
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv
from flask import Flask, request as flask_request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_bolt.oauth.oauth_settings import OAuthSettings
from slack_sdk.oauth.installation_store.file import FileInstallationStore
from slack_sdk.oauth.state_store.file import FileOAuthStateStore

from extraction.extract_actions import extract_actions
from posting.post_items import post_action_items
from resolution.resolve_owner import resolve_items_owners


load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

SLACK_MCP_URL = "https://mcp.slack.com/mcp"
SLACK_MCP_PROTOCOL_VERSION = "2025-06-18"
SLACK_MCP_USER_SEARCH_TOOL = "slack_search_users"

SLACK_BOT_SCOPES = ["commands", "chat:write", "search:read.users"]
SLACK_USER_SCOPES = ["chat:write", "canvases:write"]
INSTALLATION_STORE_DIR = os.environ.get("SLACK_INSTALLATION_DIR", "./.slack_installations")
OAUTH_STATE_STORE_DIR = os.environ.get("SLACK_OAUTH_STATE_DIR", "./.slack_oauth_state")


def _mcp_call(token: str, method: str, params: Optional[dict], session_id: Optional[str] = None) -> requests.Response:
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


def _lookup_slack_users_with_mcp(owner_name: str, user_token: Optional[str]) -> List[Dict[str, str]]:
    """
    Looks up Slack users by name via Slack's official MCP server (mcp.slack.com),
    using the slack_search_users tool over JSON-RPC 2.0 / Streamable HTTP.
    Slack's MCP server rejects bot tokens, so this uses the OAuth-installing
    user's token (xoxp-...) rather than SLACK_BOT_TOKEN.
    """
    logger.info("MCP lookup requested for owner: %s", owner_name)

    if not user_token:
        logger.error("No Slack user token available for MCP lookup (owner=%s)", owner_name)
        return []

    try:
        init_response = _mcp_call(
            user_token,
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
            user_token,
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
    installation_store = FileInstallationStore(base_dir=INSTALLATION_STORE_DIR)
    state_store = FileOAuthStateStore(expiration_seconds=600, base_dir=OAUTH_STATE_STORE_DIR)

    oauth_settings = OAuthSettings(
        client_id=os.environ["SLACK_CLIENT_ID"],
        client_secret=os.environ["SLACK_CLIENT_SECRET"],
        scopes=SLACK_BOT_SCOPES,
        user_scopes=SLACK_USER_SCOPES,
        installation_store=installation_store,
        state_store=state_store,
    )

    app = App(signing_secret=os.environ["SLACK_SIGNING_SECRET"], oauth_settings=oauth_settings)

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

        team_id = body.get("team", {}).get("id")
        installation = (
            installation_store.find_installation(enterprise_id=None, team_id=team_id) if team_id else None
        )
        user_token = installation.user_token if installation else None

        extracted_items = extract_actions(transcript=transcript, meeting_date=meeting_date)
        resolved_items = resolve_items_owners(
            extracted_items, lambda owner_name: _lookup_slack_users_with_mcp(owner_name, user_token)
        )
        post_action_items(client=client, channel_id=channel_id, items=resolved_items)

    return app


def _run_oauth_server(bolt_app: App, port: int) -> None:
    """
    Serves Bolt's built-in /slack/install and /slack/oauth_redirect endpoints.
    Needed because the OAuth install flow is plain HTTP, while events/interactivity
    run over Socket Mode below. Point an ngrok tunnel at this port and use that as
    the manifest's redirect_urls host.
    """
    flask_app = Flask(__name__)
    oauth_handler = SlackRequestHandler(bolt_app)

    @flask_app.route("/slack/install", methods=["GET"])
    def install():
        return oauth_handler.handle(flask_request)

    @flask_app.route("/slack/oauth_redirect", methods=["GET"])
    def oauth_redirect():
        return oauth_handler.handle(flask_request)

    flask_app.run(port=port, use_reloader=False)


if __name__ == "__main__":
    bolt_app = create_app()

    oauth_port = int(os.environ.get("SLACK_OAUTH_PORT", "3000"))
    threading.Thread(target=_run_oauth_server, args=(bolt_app, oauth_port), daemon=True).start()

    app_token = os.environ.get("SLACK_APP_TOKEN")
    if not app_token:
        raise RuntimeError("SLACK_APP_TOKEN is required for Socket Mode")
    SocketModeHandler(bolt_app, app_token).start()

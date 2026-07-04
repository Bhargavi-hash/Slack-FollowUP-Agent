from __future__ import annotations

from typing import Dict, List


def _owner_text(item: Dict[str, str]) -> str:
    if item.get("owner_resolution") == "resolved" and item.get("slack_user_id"):
        return f"<@{item['slack_user_id']}>"

    owner = item.get("owner_name", "Unknown")
    return owner


def _resolution_note(item: Dict[str, str]) -> str:
    status = item.get("owner_resolution")
    if status in {"ambiguous", "not_found"}:
        return "\n:warning: couldn't confirm who this is in Slack; posted as plain text name."
    return ""


def build_action_item_blocks(item: Dict[str, str]) -> List[Dict[str, object]]:
    owner = _owner_text(item)
    task = item.get("task", "")
    due = item.get("due") or "Not specified"
    quote = item.get("source_quote", "")

    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Action:* {task}\n*Owner:* {owner}\n*Due:* {due}{_resolution_note(item)}",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Source quote: \"{quote}\"",
                }
            ],
        },
        {"type": "divider"},
    ]


def post_action_items(client, channel_id: str, items: List[Dict[str, str]]) -> None:
    if not items:
        client.chat_postMessage(
            channel=channel_id,
            text="No grounded action items found in this transcript.",
        )
        return

    for item in items:
        blocks = build_action_item_blocks(item)
        fallback = f"Action item for {item.get('owner_name', 'Unknown')}: {item.get('task', '')}"
        client.chat_postMessage(channel=channel_id, text=fallback, blocks=blocks)

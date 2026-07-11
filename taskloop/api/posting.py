import os
from slack_sdk import WebClient
from dotenv import load_dotenv
load_dotenv()

def post_action_item(channel: str, task: str, resolution: dict, bot_token: str, due_date: str = None) -> dict:
    """
    Posts a single action item to a Slack channel.
    - If resolution["resolution"] == "resolved", @mention the real user
    - Otherwise, show the plain name with a warning, never guess
    """
    client = WebClient(token=bot_token)   # build a fresh client per call, using the right workspace's token

    due_str = f" (due: {due_date})" if due_date else ""
    if resolution["resolution"] == "resolved":
        message_text = f"<@{resolution['user_id']}> — {task}{due_str}"
    elif resolution["resolution"] == "ambiguous":
        candidates = ", ".join(resolution["candidates"])
        message_text = f"⚠️ Couldn't confirm who this is (candidates: {candidates}) — {task}{due_str}"
    else:  # not_found
        message_text = f"⚠️ Couldn't find a matching Slack user — {task}{due_str}"

    response = client.chat_postMessage(channel=channel, text=message_text)
    return response
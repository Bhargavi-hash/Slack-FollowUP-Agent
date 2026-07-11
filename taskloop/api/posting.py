import os
from slack_sdk import WebClient
from dotenv import load_dotenv

load_dotenv()
client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))

def post_action_item(channel: str, task: str, resolution: dict, due_date: str = None) -> dict:
    """
    Posts a single action item to a Slack channel.
    - If resolution["resolution"] == "resolved", @mention the real user
    - Otherwise, show the plain name with a warning, never guess
    """
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

if __name__ == "__main__":
    from taskloop.api.resolution import resolve_owner

    test_cases = [
        ("do the drawing part", resolve_owner("Alice")),
        ("do something", resolve_owner("Alex")),
        ("do something else", resolve_owner("Zach")),
    ]

    for task, resolution in test_cases:
        result = post_action_item("C0BF6GCSETC", task, resolution)
        print(result["ok"])
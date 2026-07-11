import requests
from dotenv import load_dotenv
import os
import json
import re

load_dotenv()
SLACK_USER_TOKEN=os.getenv("SLACK_USER_TOKEN")

def slack_mcp_lookup(name: str) -> list[dict]:
    """
    Real Slack user lookup via the official Slack MCP server.
    Same interface as mock_lookup_slack_user: takes a name, returns a 
    list of matching user dicts.
    """
    response = requests.post(
        "https://mcp.slack.com/mcp",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {os.getenv('SLACK_USER_TOKEN')}"
        },
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "method": "tools/call",
            "params": {
                "name": "slack_search_users",
                "arguments": {"query": name}
            }
        }
    )

    data = response.json()
    
    inner_text = data["result"]["content"][0]["text"]
    inner_data = json.loads(inner_text)

    results_markdown = inner_data["results"]

    names = re.findall(r"Name: (.+)", results_markdown)
    user_ids = re.findall(r"User ID: (\w+)", results_markdown)

    matches = []


    for n, uid in zip(names, user_ids):
        matches.append({"user_id": uid, "name": n.strip()})

    return matches

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    print(slack_mcp_lookup("Aliza"))
import requests
import os
from dotenv import load_dotenv

load_dotenv()
SLACK_USER_TOKEN = os.getenv("SLACK_USER_TOKEN")  # the xoxp- token from earlier

response = requests.post(
    "https://mcp.slack.com/mcp",
    headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {SLACK_USER_TOKEN}"
    },
    json={
        "jsonrpc": "2.0",
        "id": "1",
        "method": "tools/list",
        "params": {}
    }
)

print(response.status_code)
print(response.json())
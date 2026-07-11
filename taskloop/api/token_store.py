# token_store.py
from upstash_redis import Redis
from dotenv import load_dotenv
import json

load_dotenv()

redis = Redis.from_env()

def save_installation(team_id: str, bot_token: str, user_token: str) -> None:
    """Store a workspace's tokens after successful OAuth install."""
    data = {"bot_token": bot_token, "user_token": user_token}
    redis.set(f"team:{team_id}", json.dumps(data))

def get_installation(team_id: str) -> dict | None:
    """Retrieve a workspace's stored tokens. Returns None if not installed."""
    raw = redis.get(f"team:{team_id}")
    if raw is None:
        return None
    return json.loads(raw)


if __name__ == "__main__":
    save_installation("T999", "xoxb-fake-bot-token", "xoxp-fake-user-token")
    result = get_installation("T999")
    print(result)

    missing = get_installation("T000_DOES_NOT_EXIST")
    print(missing)
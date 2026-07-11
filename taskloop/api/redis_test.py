# redis_test.py
from upstash_redis import Redis
from dotenv import load_dotenv
import json

load_dotenv()
redis = Redis.from_env()

data = {"team_id": "T123", "user_token": "xoxp-fake-for-now"}
redis.set("team:T123", json.dumps(data))

retrieved = json.loads(redis.get("team:T123"))
print(retrieved)
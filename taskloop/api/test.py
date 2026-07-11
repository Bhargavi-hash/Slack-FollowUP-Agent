import os
from dotenv import load_dotenv
from qstash import Receiver

load_dotenv()

receiver = Receiver(
    current_signing_key=os.getenv("QSTASH_CURRENT_SIGNING_KEY"),
    next_signing_key=os.getenv("QSTASH_NEXT_SIGNING_KEY"),
)

# Paste the EXACT signature value from your last debug log
signature = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOiIiLCJib2R5IjoiTWU1Qlk1TG1fVzE0Zkk4WTcwbjVXbU9vXzJxakZPQXhVbUx5RGdIOGFHQT0iLCJleHAiOjE3ODM3OTQ2NTUsImlhdCI6MTc4Mzc5NDM1NSwiaXNzIjoiVXBzdGFzaCIsImp0aSI6Imp3dF83d2RBdXFtSlJuM0tIMVJmRGRhdDdSVlpRbzFzIiwibmJmIjotNjIxMzU1OTY4MDAsInN1YiI6Imh0dHBzOi8vc2xhY2stZm9sbG93LXVwLWFnZW50LnZlcmNlbC5hcHAvc2xhY2svcHJvY2VzcyJ9.LmrSe8w9JOSaSAqpoOVBg87pM25_F5eE8h6UIoT7Z0A"

# Paste the EXACT body from your qstash log (the JSON string, exactly as shown)
body = '{"transcript": "Alright, let\\u2019s go through everything...", "meeting_date": "2026-07-11", "channel_id": "C0BF6GCSETC"}'
# ^ use the FULL exact body from your earlier message, not truncated

result = receiver.verify(signature=signature, body=body, url="https://slack-follow-up-agent.vercel.app/slack/process")
print("Verification result:", result)
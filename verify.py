from slack_sdk.signature import SignatureVerifier
import os
from dotenv import load_dotenv

load_dotenv()
verifier = SignatureVerifier(signing_secret=os.getenv("SLACK_SIGNING_SECRET"))

def verify_slack_request(request) -> bool:
    """
    Verifies an incoming Flask request actually came from Slack.
    Args:
        request: a Flask request object
    """
    
    body = request.get_data()
    headers = request.headers

    return verifier.is_valid_request(body, headers)

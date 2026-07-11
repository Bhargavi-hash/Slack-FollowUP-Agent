from google import genai
from dotenv import load_dotenv
import json

load_dotenv()
client = genai.Client()

def extract_action_items(transcript: str, meeting_date: str) -> list[dict]:
    """
    Extracts action items from a meeting transcript.
    Args:
        transcript: The raw meeting transcript text
        meeting_date: The date the meeting happened, YYYY-MM-DD (for 
                       resolving relative dates like "by Friday")
    Returns a list of dicts, each with: owner_name, task, due_date, source_quote
    """

    prompt = f"""
        The meeting happened on {meeting_date}.

        Extract action items from this transcript. For each action item, provide:
        - owner_name: the person's name exactly as it appears in the transcript
        - task: what they need to do
        - due_date: resolved to an actual YYYY-MM-DD date if a relative date like 
          "Friday" was mentioned, relative to the meeting date above
        - source_quote: the exact line from the transcript this was extracted from

        IMPORTANT: Only extract items that are explicitly stated or clearly implied.
        Do not invent action items that weren't actually discussed. If there are 
        no real action items, return an empty list.

        Respond with ONLY a JSON array, no other text, no markdown code fences.

        Transcript:
        {transcript}
    """

    response = client.models.generate_content(
        model='gemini-3.1-flash-lite',
        contents=prompt
    )

    text = response.text.strip()

    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    items = json.loads(text)

    verified_items = []
    for item in items:
        if item["source_quote"] in transcript:
            verified_items.append(item)
        else:
            print(f"WARNING: dropped item with unverifiable quote: {item}")
    
    return verified_items

if __name__ == "__main__":
    from test_trascripts import TRANSCRIPTS

    for index, ts in enumerate(TRANSCRIPTS):
        print(f"----------- Transcript {index} ------------")
        items = extract_action_items(ts, '2026-07-10')
        print(items)

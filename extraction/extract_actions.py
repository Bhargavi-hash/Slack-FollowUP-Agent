from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Callable, Iterable, List, Optional


@dataclass
class ActionItem:
    owner_name: str
    task: str
    due: Optional[str]
    source_quote: str


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_]*", "", text).strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


def _weekday_from_name(name: str) -> int:
    mapping = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    return mapping[name.lower()]


def _next_weekday(from_date: date, target_weekday: int) -> date:
    delta = (target_weekday - from_date.weekday()) % 7
    if delta == 0:
        delta = 7
    return from_date + timedelta(days=delta)


def _parse_due_phrase(due_phrase: str, meeting_date: date) -> Optional[str]:
    phrase = due_phrase.strip().lower().rstrip(".?!")
    weekday_match = re.search(r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", phrase)
    if weekday_match:
        weekday = _weekday_from_name(weekday_match.group(1))
        return _next_weekday(meeting_date, weekday).isoformat()

    iso_match = re.search(r"(20\d{2}-\d{2}-\d{2})", phrase)
    if iso_match:
        return iso_match.group(1)

    us_match = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})", phrase)
    if us_match:
        month, day, year = us_match.group(1).split("/")
        year_i = int(year)
        if year_i < 100:
            year_i += 2000
        try:
            return date(year_i, int(month), int(day)).isoformat()
        except ValueError:
            return None

    return None


def _extract_owner_and_task(line: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    owner = None
    task = None
    due_phrase = None

    patterns = [
        r"^(?P<owner>[A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)?)\s+will\s+(?P<task>.+)$",
        r"^(?P<owner>[A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)?),\s*[Cc]an you\s+(?P<task>.+)$",
        r"^[Cc]an you\s+(?P<owner>[A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)?)\s+(?P<task>.+)$",
        r"^(?P<owner>[A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)?)\s+to\s+(?P<task>.+)$",
    ]

    for pattern in patterns:
        match = re.match(pattern, line)
        if match:
            owner = match.group("owner").strip()
            raw_task = match.group("task").strip()
            due_match = re.search(r"\b(?:by|before|due|on)\s+(.+)$", raw_task, flags=re.IGNORECASE)
            if due_match:
                due_phrase = due_match.group(1).strip()
                task = re.sub(r"\b(?:by|before|due|on)\s+.+$", "", raw_task, flags=re.IGNORECASE).strip()
            else:
                task = raw_task
            break

    if owner and task:
        task = task.rstrip(". ")

    return owner, task, due_phrase


def _is_action_like(line: str) -> bool:
    lowered = line.lower()
    return any(
        token in lowered
        for token in [
            " will ",
            "can you",
            "action:",
            "todo:",
            " needs to ",
            " to ",
        ]
    )


def _ground_items(items: Iterable[ActionItem], transcript: str) -> List[ActionItem]:
    grounded: List[ActionItem] = []
    for item in items:
        quote = item.source_quote.strip()
        if not quote:
            continue
        if quote not in transcript:
            continue
        grounded.append(item)
    return grounded


def _deterministic_extract(transcript: str, meeting_date: date) -> List[ActionItem]:
    items: List[ActionItem] = []
    for raw_line in transcript.splitlines():
        line = raw_line.strip()
        if not line or not _is_action_like(f" {line} "):
            continue

        owner, task, due_phrase = _extract_owner_and_task(line)
        if not owner or not task:
            continue

        due = _parse_due_phrase(due_phrase, meeting_date) if due_phrase else None
        items.append(
            ActionItem(
                owner_name=owner,
                task=task,
                due=due,
                source_quote=line,
            )
        )

    deduped: List[ActionItem] = []
    seen = set()
    for item in items:
        key = (item.owner_name.lower(), item.task.lower(), item.source_quote)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return _ground_items(deduped, transcript)


def _gemini_extract(transcript: str, meeting_date: date) -> List[ActionItem]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")

    try:
        import google.generativeai as genai
    except ImportError as exc:
        raise RuntimeError("google-generativeai is required for Gemini extraction") from exc

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = (
        "You extract action items from meeting transcripts. Return ONLY JSON: an array of "
        "objects with keys owner_name, task, due, source_quote.\n"
        "Rules:\n"
        "1) Extract only explicit or clearly implied action items.\n"
        "2) Never invent items.\n"
        "3) source_quote must be a verbatim snippet from transcript.\n"
        "4) due must be ISO date YYYY-MM-DD if derivable; otherwise null.\n"
        f"Meeting date: {meeting_date.isoformat()}\n"
        "Transcript:\n"
        f"{transcript}"
    )

    response = model.generate_content(prompt)
    raw = _strip_json_fence(response.text or "[]")
    parsed = json.loads(raw)
    if not isinstance(parsed, list):
        raise ValueError("Gemini output is not a list")

    items: List[ActionItem] = []
    for obj in parsed:
        if not isinstance(obj, dict):
            continue
        owner = str(obj.get("owner_name", "")).strip()
        task = str(obj.get("task", "")).strip()
        quote = str(obj.get("source_quote", "")).strip()
        due_raw = obj.get("due")
        due = str(due_raw).strip() if due_raw else None
        if not owner or not task or not quote:
            continue
        items.append(ActionItem(owner_name=owner, task=task, due=due, source_quote=quote))

    return _ground_items(items, transcript)


def extract_actions(
    transcript: str,
    meeting_date: date,
    extractor: Optional[Callable[[str, date], List[ActionItem]]] = None,
) -> List[dict]:
    if not transcript.strip():
        return []

    if extractor is not None:
        items = extractor(transcript, meeting_date)
    else:
        try:
            items = _gemini_extract(transcript, meeting_date)
        except Exception:
            items = _deterministic_extract(transcript, meeting_date)

    return [asdict(item) for item in items]

from datetime import date
from pathlib import Path
from typing import Dict, List

from extraction.extract_actions import extract_actions
from resolution.resolve_owner import resolve_items_owners, resolve_owner_name


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _mock_slack_mcp_lookup(owner_name: str) -> List[Dict[str, str]]:
    directory = {
        "Alice": [{"id": "U_ALICE", "display_name": "Alice", "real_name": "Alice Johnson"}],
        "Sam": [
            {"id": "U_SAM_1", "display_name": "Sam", "real_name": "Sam Patel"},
            {"id": "U_SAM_2", "display_name": "Sam", "real_name": "Sam Chen"},
        ],
        "Priya": [{"id": "U_PRIYA", "display_name": "Priya", "real_name": "Priya Rao"}],
    }
    return directory.get(owner_name, [])


def test_owner_resolution_resolved_path() -> None:
    result = resolve_owner_name("Alice", _mock_slack_mcp_lookup)
    assert result.status == "resolved"
    assert result.user_id == "U_ALICE"


def test_owner_resolution_ambiguous_path() -> None:
    result = resolve_owner_name("Sam", _mock_slack_mcp_lookup)
    assert result.status == "ambiguous"
    assert sorted(result.candidate_user_ids or []) == ["U_SAM_1", "U_SAM_2"]


def test_owner_resolution_not_found_path() -> None:
    result = resolve_owner_name("Zara", _mock_slack_mcp_lookup)
    assert result.status == "not_found"
    assert result.user_id is None


def test_ambiguous_transcript_falls_back_without_mismention() -> None:
    transcript = (FIXTURES_DIR / "transcript_ambiguous.txt").read_text(encoding="utf-8")
    extracted = extract_actions(transcript, date(2026, 7, 4))
    resolved = resolve_items_owners(extracted, _mock_slack_mcp_lookup)

    by_owner = {item["owner_name"]: item for item in resolved}

    assert by_owner["Sam"]["owner_resolution"] == "ambiguous"
    assert by_owner["Sam"]["slack_user_id"] is None
    assert by_owner["Priya"]["owner_resolution"] == "resolved"
    assert by_owner["Priya"]["slack_user_id"] == "U_PRIYA"


def test_not_found_owner_falls_back_without_mismention() -> None:
    transcript = "Zara will share the legal checklist by Friday."
    extracted = extract_actions(transcript, date(2026, 7, 4))
    resolved = resolve_items_owners(extracted, _mock_slack_mcp_lookup)

    assert len(resolved) == 1
    assert resolved[0]["owner_name"] == "Zara"
    assert resolved[0]["owner_resolution"] == "not_found"
    assert resolved[0]["slack_user_id"] is None

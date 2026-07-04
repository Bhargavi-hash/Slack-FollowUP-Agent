from datetime import date
from pathlib import Path

from extraction.extract_actions import extract_actions


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def test_extraction_clean_fixture_has_grounded_items() -> None:
    transcript = _read_fixture("transcript_clean.txt")
    items = extract_actions(transcript, date(2026, 7, 4))

    assert len(items) == 3
    assert {item["owner_name"] for item in items} == {"Alice", "Bob", "Carla"}
    assert all(item["source_quote"] in transcript for item in items)

    by_owner = {item["owner_name"]: item for item in items}
    assert by_owner["Alice"]["due"] == "2026-07-10"
    assert by_owner["Bob"]["due"] == "2026-07-12"
    assert by_owner["Carla"]["due"] == "2026-07-07"


def test_extraction_ambiguous_fixture_extracts_items_without_invention() -> None:
    transcript = _read_fixture("transcript_ambiguous.txt")
    items = extract_actions(transcript, date(2026, 7, 4))

    assert len(items) == 2
    assert {item["owner_name"] for item in items} == {"Sam", "Priya"}
    assert all(item["source_quote"] in transcript for item in items)


def test_extraction_no_actions_fixture_returns_empty() -> None:
    transcript = _read_fixture("transcript_no_actions.txt")
    items = extract_actions(transcript, date(2026, 7, 4))

    assert items == []

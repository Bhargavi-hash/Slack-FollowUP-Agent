from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional


@dataclass
class OwnerResolution:
    status: str
    owner_name: str
    user_id: Optional[str] = None
    candidate_user_ids: Optional[List[str]] = None


def _name_tokens(name: str) -> List[str]:
    return [token.lower() for token in name.strip().split() if token.strip()]


def _candidate_matches_name(owner_name: str, candidate: Dict[str, str]) -> bool:
    owner_tokens = _name_tokens(owner_name)
    if not owner_tokens:
        return False

    candidate_names = [
        candidate.get("display_name", ""),
        candidate.get("real_name", ""),
        candidate.get("name", ""),
    ]
    candidate_token_sets = [set(_name_tokens(candidate_name)) for candidate_name in candidate_names if candidate_name]

    owner_first = owner_tokens[0]
    owner_full = set(owner_tokens)

    for token_set in candidate_token_sets:
        if not token_set:
            continue
        if owner_full.issubset(token_set):
            return True
        if owner_first in token_set:
            return True
    return False


def resolve_owner_name(
    owner_name: str,
    lookup_candidates: Callable[[str], List[Dict[str, str]]],
) -> OwnerResolution:
    candidates = lookup_candidates(owner_name)
    matches = [candidate for candidate in candidates if _candidate_matches_name(owner_name, candidate)]

    if len(matches) == 1:
        return OwnerResolution(
            status="resolved",
            owner_name=owner_name,
            user_id=matches[0].get("id"),
        )

    if len(matches) > 1:
        return OwnerResolution(
            status="ambiguous",
            owner_name=owner_name,
            candidate_user_ids=[candidate.get("id") for candidate in matches if candidate.get("id")],
        )

    return OwnerResolution(status="not_found", owner_name=owner_name)


def resolve_items_owners(
    items: List[Dict[str, str]],
    lookup_candidates: Callable[[str], List[Dict[str, str]]],
) -> List[Dict[str, str]]:
    resolved_items: List[Dict[str, str]] = []
    for item in items:
        owner_name = item.get("owner_name", "")
        resolution = resolve_owner_name(owner_name, lookup_candidates)

        enriched = dict(item)
        enriched["owner_resolution"] = resolution.status
        enriched["slack_user_id"] = resolution.user_id
        enriched["candidate_user_ids"] = resolution.candidate_user_ids or []
        resolved_items.append(enriched)

    return resolved_items

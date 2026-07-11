def mock_lookup_slack_user(name: str) -> list[dict]:
    """
    Fake version of a Slack user lookup, standing in for the real MCP call.
    Simulates a workspace with a few known users, including one intentional
    name collision (two "Alex"es) to test ambiguity handling.
    """
    fake_workspace = [
        {"id": "U001", "real_name": "Alice Johnson"},
        {"id": "U002", "real_name": "Bob Smith"},
        {"id": "U003", "real_name": "Tina Rodriguez"},
        {"id": "U004", "real_name": "Alex Chen"},
        {"id": "U005", "real_name": "Alex Martinez"},   # intentional collision
    ]
    
    users = []

    for user in fake_workspace:
        if name.lower() in user["real_name"].lower():
            users.append({
                "user_id": user["id"],
                "name": user["real_name"]
            })
    
    return users

def resolve_owner(name: str, lookup_fn=mock_lookup_slack_user) -> dict:
    """
    Resolves an extracted owner name to a real Slack user.
    Returns one of three outcomes:
      {"resolution": "resolved", "user_id": ..., "name": ...}
      {"resolution": "ambiguous", "candidates": [...]}
      {"resolution": "not_found"}
    """
    matches = lookup_fn(name)
    
    if not matches:
        return {"resolution": "not_found"}
    if len(matches) > 1:
        return {"resolution": "ambiguous", "candidates": [m["name"] for m in matches]}
    
    return {"resolution": "resolved", "user_id": matches[0]["user_id"], "name": matches[0]["name"]}
    
if __name__ == "__main__":
    print(resolve_owner("Alice"))   # expect: resolved
    print(resolve_owner("Alex"))    # expect: ambiguous, 2 candidates
    print(resolve_owner("Zach"))    # expect: not_found
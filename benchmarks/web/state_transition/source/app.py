"""Non-executed benchmark source for session-state representation."""


def session_state(authenticated: bool) -> dict[str, str]:
    return {"state": "authenticated" if authenticated else "anonymous"}

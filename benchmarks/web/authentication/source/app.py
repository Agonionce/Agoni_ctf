"""Non-executed benchmark source showing an authentication boundary."""


def admin_view(authenticated: bool) -> tuple[int, dict[str, str]]:
    if not authenticated:
        return 403, {"error": "forbidden", "state": "anonymous"}
    return 200, {"state": "authenticated"}

"""Non-executed authorization benchmark source."""


def reports_view(allowed: bool) -> tuple[int, dict[str, str]]:
    return (200, {"state": "available"}) if allowed else (403, {"error": "access denied"})

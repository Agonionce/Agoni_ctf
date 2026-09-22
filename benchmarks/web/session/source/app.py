"""Non-executed session benchmark source."""


def account_view(active: bool) -> tuple[int, dict[str, str]]:
    return (200, {"state": "authenticated"}) if active else (401, {"error": "authentication required"})

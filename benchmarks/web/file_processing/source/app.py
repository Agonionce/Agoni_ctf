"""Non-executed file-processing benchmark source."""


def process_file(name: str) -> dict[str, str]:
    return {"status": "accepted" if name.endswith(".txt") else "rejected"}

"""Non-executed JSON API benchmark source."""


def list_items(page: int) -> dict[str, object]:
    return {"items": [{"id": 1, "name": "sample"}], "page": page, "total": 1}

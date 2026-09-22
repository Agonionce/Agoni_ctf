"""Non-executed benchmark source for a business-state transition."""


def update_cart(quantity: int, action: str) -> dict[str, int | str]:
    count = quantity if action == "add" else 0
    return {"status": "updated", "cart_count": count}

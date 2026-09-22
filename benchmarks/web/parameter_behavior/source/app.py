"""Non-executed benchmark source for input-dependent rendering."""


def search_view(query: str) -> str:
    return f"<html><title>Search</title><p>{len(query)} result units</p></html>"

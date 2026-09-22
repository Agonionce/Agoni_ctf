"""Web challenge knowledge classification only; no HTTP runtime."""

from agent.domains.base import RuleDomain


class WebDomain(RuleDomain):
    def __init__(self) -> None:
        super().__init__(
            name="web",
            description="Reasoning patterns for authorized web CTF challenges.",
            skill_names=("web_general", "authentication", "sql_injection", "xss", "ssrf"),
            signals=(
                "web", "http", "https", "php", "cookie", "session", "login",
                "html", "javascript", "sql", "request", "response", "url",
            ),
            skill_signals={
                "authentication": ("login", "cookie", "session", "authentication", "jwt"),
                "sql_injection": ("sql", "database", "query", "sqli", "mysql", "sqlite"),
                "xss": ("xss", "cross-site scripting", "javascript", "html injection"),
                "ssrf": ("ssrf", "server-side request", "internal url", "metadata endpoint"),
            },
        )

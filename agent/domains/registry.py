"""Domain registry exposed to routing and CLI layers."""

from __future__ import annotations

from typing import Iterable

from agent.domains.base import Domain
from agent.domains.crypto import CryptoDomain
from agent.domains.misc import MiscDomain
from agent.domains.pwn import PwnDomain
from agent.domains.reverse import ReverseDomain
from agent.domains.web import WebDomain


class DomainRegistry:
    def __init__(self, domains: Iterable[Domain] = ()) -> None:
        self._domains: dict[str, Domain] = {}
        for domain in domains:
            self.register(domain)

    def register(self, domain: Domain) -> None:
        if domain.name in self._domains:
            raise ValueError(f"duplicate domain: {domain.name}")
        self._domains[domain.name] = domain

    def get(self, name: str) -> Domain:
        try:
            return self._domains[name]
        except KeyError as error:
            raise KeyError(f"unknown domain: {name}") from error

    def all(self) -> list[Domain]:
        return list(self._domains.values())

    def names(self) -> list[str]:
        return list(self._domains)


def build_default_domain_registry() -> DomainRegistry:
    return DomainRegistry(
        [WebDomain(), PwnDomain(), ReverseDomain(), CryptoDomain(), MiscDomain()]
    )

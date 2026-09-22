"""R3 deterministic domain intelligence and skill selection."""

from agent.domains.context import SkillContextBuilder
from agent.domains.loader import SkillLoader
from agent.domains.manager import DomainRuntimeManager, build_default_runtime_manager
from agent.domains.registry import DomainRegistry, build_default_domain_registry
from agent.domains.router import DomainSelection, DomainSkillRouter, SkillRouter
from agent.domains.runtime_context import DomainRuntimeContextBuilder

__all__ = [
    "DomainRegistry",
    "DomainRuntimeContextBuilder",
    "DomainRuntimeManager",
    "DomainSelection",
    "DomainSkillRouter",
    "SkillRouter",
    "SkillContextBuilder",
    "SkillLoader",
    "build_default_domain_registry",
    "build_default_runtime_manager",
]

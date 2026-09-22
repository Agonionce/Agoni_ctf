"""Domain errors for the Agonionce R0 runtime."""


class RuntimeDomainError(Exception):
    """Base class for expected runtime failures."""


class ContractValidationError(RuntimeDomainError, ValueError):
    """Raised when a typed runtime contract is invalid."""


class PlannerOutputError(RuntimeDomainError):
    """Raised when a Planner response cannot become an ActionProposal."""


class BudgetExceeded(RuntimeDomainError):
    """Raised when a RunBudget disallows another runtime operation."""


class RuntimeConfigurationError(RuntimeDomainError, ValueError):
    """Raised when runtime configuration is invalid."""

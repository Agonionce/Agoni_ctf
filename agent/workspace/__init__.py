"""R1 isolated challenge workspace support."""

from agent.workspace.manager import Workspace, WorkspaceManager
from agent.workspace.path import (
    PUBLIC_WORKSPACE_SCOPES,
    ResolvedWorkspacePath,
    WorkspacePathResolver,
)

__all__ = [
    "PUBLIC_WORKSPACE_SCOPES",
    "ResolvedWorkspacePath",
    "Workspace",
    "WorkspaceManager",
    "WorkspacePathResolver",
]

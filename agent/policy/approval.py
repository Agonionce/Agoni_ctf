"""Action-level approval state independent from CLI rendering."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass
class ApprovalRequest:
    request_id: str
    tool_name: str
    arguments: Dict[str, Any]
    reason: str
    risk_level: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    decided_at: Optional[datetime] = None
    decision_note: str = ""


class ApprovalManager:
    """Own pending/approved/rejected state for individual ToolCall values."""

    def __init__(self) -> None:
        self._requests: Dict[str, ApprovalRequest] = {}

    def request(
        self,
        *,
        tool_name: str,
        arguments: Dict[str, Any],
        reason: str,
        risk_level: str,
    ) -> ApprovalRequest:
        request = ApprovalRequest(
            request_id=str(uuid.uuid4()),
            tool_name=tool_name,
            arguments=dict(arguments),
            reason=reason,
            risk_level=risk_level,
        )
        self._requests[request.request_id] = request
        return request

    def approve(self, request_id: str, note: str = "") -> ApprovalRequest:
        return self._decide(request_id, ApprovalStatus.APPROVED, note)

    def reject(self, request_id: str, note: str = "") -> ApprovalRequest:
        return self._decide(request_id, ApprovalStatus.REJECTED, note)

    def get(self, request_id: str) -> Optional[ApprovalRequest]:
        return self._requests.get(request_id)

    def list(self) -> List[ApprovalRequest]:
        return list(self._requests.values())

    def _decide(
        self,
        request_id: str,
        status: ApprovalStatus,
        note: str,
    ) -> ApprovalRequest:
        request = self._requests[request_id]
        if request.status is not ApprovalStatus.PENDING:
            raise ValueError("approval request is already decided")
        request.status = status
        request.decided_at = datetime.now(timezone.utc)
        request.decision_note = note
        return request

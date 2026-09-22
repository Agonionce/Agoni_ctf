"""R14 presentation contracts for the loopback-only local workbench."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ChallengeStatus = Literal[
    "not_started",
    "analyzing",
    "waiting",
    "needs_help",
    "completed",
    "not_solved",
    "paused",
]


class ChallengeMaterial(BaseModel):
    """One imported file projection with its recorded local path."""

    name: str
    kind: Literal["attachment", "source"]


class ChallengeSummary(BaseModel):
    """Concise challenge row used by the local catalog."""

    challenge_id: str
    name: str
    domain: str
    status: ChallengeStatus
    status_label: str
    created_at: str


class ChallengeDetail(ChallengeSummary):
    """Complete local operator detail for one challenge."""

    description: str
    target_url: str | None = None
    materials: list[ChallengeMaterial] = Field(default_factory=list)


class ChallengeCollection(BaseModel):
    items: list[ChallengeSummary]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["agonionce-local-ui"] = "agonionce-local-ui"


class ErrorResponse(BaseModel):
    code: str
    message: str
    existing_challenge_id: str | None = None


class RunMilestoneView(BaseModel):
    title: str
    detail: str
    state: Literal["current", "attention", "done"]
    occurred_at: str


class PendingDecisionView(BaseModel):
    decision_id: str
    kind: Literal["action", "answer"]
    title: str
    summary: str
    risk_label: str
    created_at: str
    candidate_value: str | None = None
    candidate_source: str | None = None
    candidate_evidence: str | None = None


class RunView(BaseModel):
    status: str
    status_label: str
    active: bool
    milestones: list[RunMilestoneView] = Field(default_factory=list)
    pending_decision: PendingDecisionView | None = None
    can_start: bool
    can_abort: bool
    can_resume: bool
    completion_available: bool


class DecisionRequest(BaseModel):
    decision: Literal["approve", "reject"]


class OutcomeRecord(BaseModel):
    title: str
    detail: str
    status_label: str
    certainty_label: str
    occurred_at: str | None = None
    artifact_paths: list[str] = Field(default_factory=list)


class ArtifactOutcome(BaseModel):
    artifact_id: str | None = Field(default=None, exclude=True)
    name: str
    kind_label: str
    created_at: str | None = None
    path: str | None = None


class FlagOutcomeView(BaseModel):
    """The single challenge result the operator needs to verify."""

    status: Literal["found", "not_found", "conflict"]
    status_label: str
    value: str | None = None
    source: str | None = None
    evidence: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    reason: str | None = None


class WebEndpointOutcome(BaseModel):
    path: str
    methods: list[str] = Field(default_factory=list)
    parameters: list[str] = Field(default_factory=list)
    response_formats: list[str] = Field(default_factory=list)
    access_label: str = "访问状态未知"


class WebOutcome(BaseModel):
    available: bool = False
    phase_label: str = "尚未形成 Web 观察"
    authentication_label: str = "认证状态未知"
    technologies: list[str] = Field(default_factory=list)
    endpoints: list[WebEndpointOutcome] = Field(default_factory=list)


class ChallengeOutcomes(BaseModel):
    flag: FlagOutcomeView = Field(
        default_factory=lambda: FlagOutcomeView(
            status="not_found",
            status_label="尚未找到 Flag",
            reason="本轮尚未结束。",
        )
    )
    facts: list[OutcomeRecord] = Field(default_factory=list)
    findings: list[OutcomeRecord] = Field(default_factory=list)
    hypotheses: list[OutcomeRecord] = Field(default_factory=list)
    experiments: list[OutcomeRecord] = Field(default_factory=list)
    evidence: list[OutcomeRecord] = Field(default_factory=list)
    artifacts: list[ArtifactOutcome] = Field(default_factory=list)
    web: WebOutcome = Field(default_factory=WebOutcome)


class ChallengeDocuments(BaseModel):
    available: bool = False
    report: str = ""
    writeup: str = ""
    lessons: str = ""


class ExperienceCandidateView(BaseModel):
    candidate_id: str
    category_label: str
    kind_label: str
    pattern: str
    strategy: str
    lesson: str
    confidence_label: str
    status: Literal["PENDING", "APPROVED", "REJECTED"]
    status_label: str


class ExperienceCandidateCollection(BaseModel):
    items: list[ExperienceCandidateView] = Field(default_factory=list)


class CandidateReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]

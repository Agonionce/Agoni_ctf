"""Bounded R10.2 research context, hypothesis generation, and prioritization."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from agent.domains.manager import DomainRuntimeManager
from agent.intelligence.models import (
    ArtifactReference,
    HypothesisSource,
    HypothesisStatus,
    IntelligenceState,
    OpenQuestionStatus,
    Priority,
    artifact_references,
    enum_from,
    utc_now_iso,
)
from agent.runtime.contracts import AnalysisResult, Observation


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_/-]{2,}", value.lower()))


def _candidate_id(domain: str, statement: str) -> str:
    digest = hashlib.sha256(
        f"{domain.strip().lower()}\0{statement.strip().lower()}".encode("utf-8")
    ).hexdigest()[:12]
    return f"candidate-{digest}"


@dataclass
class HypothesisCandidate:
    """A non-executable research candidate offered to the Planner."""

    statement: str
    domain: str
    source: HypothesisSource
    confidence: float
    priority: Priority
    suggested_goal: str
    expected_result: str
    related_artifacts: list[ArtifactReference] = field(default_factory=list)
    experience_influence: list[str] = field(default_factory=list)
    rationale: str = ""
    evidence_value: float = 0.0
    experiment_type: str = ""
    evidence_type: str = ""
    experiment_context: dict[str, Any] = field(default_factory=dict)
    hypothesis_id: str = ""
    score: float = 0.0
    priority_reasons: list[str] = field(default_factory=list)
    candidate_id: str = ""

    def __post_init__(self) -> None:
        if not self.statement.strip() or not self.domain.strip():
            raise ValueError("candidate statement and domain must be non-empty")
        if not isinstance(self.source, HypothesisSource):
            raise ValueError("candidate source is invalid")
        if not isinstance(self.priority, Priority):
            raise ValueError("candidate priority is invalid")
        if not 0 <= self.confidence <= 1:
            raise ValueError("candidate confidence must be in [0, 1]")
        if not 0 <= self.evidence_value <= 1:
            raise ValueError("candidate evidence_value must be in [0, 1]")
        if not self.suggested_goal.strip() or not self.expected_result.strip():
            raise ValueError("candidate experiment guidance must be non-empty")
        if not self.candidate_id:
            self.candidate_id = _candidate_id(self.domain, self.statement)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "hypothesis_id": self.hypothesis_id,
            "statement": self.statement[:1000],
            "domain": self.domain,
            "source": self.source.value,
            "confidence": self.confidence,
            "priority": self.priority.value,
            "suggested_goal": self.suggested_goal[:1000],
            "expected_result": self.expected_result[:1000],
            "related_artifacts": [
                {
                    "artifact_id": item.artifact_id,
                    "relation_type": item.relation_type,
                }
                for item in self.related_artifacts
            ],
            "experience_influence": list(self.experience_influence),
            "rationale": self.rationale[:1000],
            "evidence_value": self.evidence_value,
            "experiment_type": self.experiment_type,
            "evidence_type": self.evidence_type,
            "experiment_context": dict(self.experiment_context),
            "score": self.score,
            "priority_reasons": list(self.priority_reasons),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HypothesisCandidate":
        return cls(
            candidate_id=str(data.get("candidate_id", "")),
            hypothesis_id=str(data.get("hypothesis_id", "")),
            statement=str(data["statement"]),
            domain=str(data.get("domain") or "misc"),
            source=enum_from(
                data.get("source"), HypothesisSource, HypothesisSource.INTELLIGENCE
            ),
            confidence=float(data.get("confidence", 0.5)),
            priority=enum_from(data.get("priority"), Priority, Priority.MEDIUM),
            suggested_goal=str(data["suggested_goal"]),
            expected_result=str(data["expected_result"]),
            related_artifacts=artifact_references(data.get("related_artifacts")),
            experience_influence=[
                str(item) for item in _list(data.get("experience_influence"))
            ],
            rationale=str(data.get("rationale", "")),
            evidence_value=float(data.get("evidence_value", 0.0)),
            experiment_type=str(data.get("experiment_type", "")),
            evidence_type=str(data.get("evidence_type", "")),
            experiment_context=(
                dict(data.get("experiment_context", {}))
                if isinstance(data.get("experiment_context"), Mapping)
                else {}
            ),
            score=float(data.get("score", 0.0)),
            priority_reasons=[
                str(item) for item in _list(data.get("priority_reasons"))
            ],
        )


@dataclass(frozen=True)
class ResearchContext:
    """Small checkpoint-safe view used to make the next research decision."""

    iteration: int
    source_step: int
    observation_id: str
    observation_summary: str
    analyzer_summary: str
    domain: str
    phase: str
    phase_goal: str
    expected_observations: tuple[str, ...]
    intelligence_summary: dict[str, Any]
    previous_experiments: tuple[dict[str, Any], ...]
    relevant_experience: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "source_step": self.source_step,
            "observation_id": self.observation_id,
            "observation_summary": self.observation_summary,
            "analyzer_summary": self.analyzer_summary,
            "domain": self.domain,
            "phase": self.phase,
            "phase_goal": self.phase_goal,
            "expected_observations": list(self.expected_observations),
            "intelligence_summary": dict(self.intelligence_summary),
            "previous_experiments": [dict(item) for item in self.previous_experiments],
            "relevant_experience": [dict(item) for item in self.relevant_experience],
        }


@dataclass(frozen=True)
class ExperimentDecisionRecord:
    iteration: int
    source_step: int
    decision: str
    candidate_id: str = ""
    hypothesis_id: str = ""
    goal: str = ""
    expected_result: str = ""
    priority_score: float = 0.0
    phase: str = ""
    experience_influence: tuple[str, ...] = ()
    rationale: str = ""
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "source_step": self.source_step,
            "decision": self.decision,
            "candidate_id": self.candidate_id,
            "hypothesis_id": self.hypothesis_id,
            "goal": self.goal[:1000],
            "expected_result": self.expected_result[:1000],
            "priority_score": self.priority_score,
            "phase": self.phase,
            "experience_influence": list(self.experience_influence),
            "rationale": self.rationale[:1000],
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExperimentDecisionRecord":
        return cls(
            iteration=int(data["iteration"]),
            source_step=int(data["source_step"]),
            decision=str(data["decision"]),
            candidate_id=str(data.get("candidate_id", "")),
            hypothesis_id=str(data.get("hypothesis_id", "")),
            goal=str(data.get("goal", "")),
            expected_result=str(data.get("expected_result", "")),
            priority_score=float(data.get("priority_score", 0.0)),
            phase=str(data.get("phase", "")),
            experience_influence=tuple(
                str(item) for item in _list(data.get("experience_influence"))
            ),
            rationale=str(data.get("rationale", "")),
            created_at=str(data.get("created_at") or utc_now_iso()),
        )


class DomainExperimentAdapter:
    """Expose phase-driven research hints without selecting or executing Tools."""

    def build_context(self, manager: DomainRuntimeManager | None) -> dict[str, Any]:
        if manager is None or manager.current_state is None:
            return {
                "domain": "misc",
                "phase": "UNKNOWN",
                "phase_goal": "Gather evidence before proposing a bounded experiment.",
                "expected_observations": [],
                "hypothesis_candidates": [],
            }
        runtime, state = manager.current()
        phase = runtime.phase(state.phase)
        candidates: list[dict[str, Any]] = []
        if state.domain == "web":
            from agent.domains.web.research.experiments import WebExperimentCatalog

            candidates.extend(
                WebExperimentCatalog().proposals(
                    getattr(state, "application_model"),
                    getattr(state, "sessions", []),
                    state.phase,
                )
            )
        if not candidates:
            expected = phase.expected_observations[0]
            candidates.append(
                {
                    "statement": f"The {state.domain} {state.phase} phase can produce evidence for {expected}.",
                    "confidence": 0.35,
                    "priority": "MEDIUM",
                    "goal": f"collect bounded evidence for {expected}",
                    "expected_result": f"{expected} recorded",
                    "evidence_value": 0.5,
                }
            )
        return {
            "domain": state.domain,
            "phase": state.phase,
            "phase_goal": phase.goal,
            "expected_observations": list(phase.expected_observations),
            "hypothesis_candidates": candidates,
        }

    def apply_feedback(
        self,
        manager: DomainRuntimeManager | None,
        feedback: Mapping[str, Any],
    ) -> bool:
        if manager is None or manager.current_state is None:
            return False
        manager.record_experiment_feedback(dict(feedback))
        return True


class ResearchContextBuilder:
    def __init__(self, *, experiment_limit: int = 5, experience_limit: int = 5) -> None:
        self.experiment_limit = experiment_limit
        self.experience_limit = experience_limit

    def build(
        self,
        *,
        iteration: int,
        observation: Observation,
        analysis: AnalysisResult,
        intelligence: IntelligenceState,
        runtime_records: Sequence[Any],
        domain_context: Mapping[str, Any],
        experience_context: Mapping[str, Any],
    ) -> ResearchContext:
        experience = experience_context.get("relevant_experience", [])
        bounded_experience = [
            {
                "id": str(item.get("id", "")),
                "domain": str(item.get("domain", "")),
                "category": str(item.get("category", "")),
                "trigger": str(item.get("trigger", ""))[:300],
                "pattern": str(item.get("pattern", ""))[:300],
                "strategy": str(item.get("strategy", ""))[:300],
                "lesson": str(item.get("lesson", ""))[:300],
                "confidence": float(item.get("confidence", 0.0)),
            }
            for item in _list(experience)[: self.experience_limit]
            if isinstance(item, Mapping)
        ]
        previous = []
        for item in list(runtime_records)[-self.experiment_limit :]:
            evaluation = getattr(item, "evaluation", None)
            previous.append(
                {
                    "experiment_id": str(getattr(item, "experiment_id", "")),
                    "hypothesis_id": str(getattr(item, "hypothesis_id", "")),
                    "status": str(getattr(getattr(item, "status", ""), "value", "")),
                    "evaluation": str(getattr(getattr(evaluation, "status", ""), "value", "")),
                    "evidence_count": len(getattr(item, "evidence_ids", [])),
                }
            )
        return ResearchContext(
            iteration=iteration,
            source_step=observation.step_id,
            observation_id=observation.observation_id,
            observation_summary=observation.objective[:500],
            analyzer_summary=analysis.summary[:1000],
            domain=str(domain_context.get("domain") or "misc"),
            phase=str(domain_context.get("phase") or "UNKNOWN"),
            phase_goal=str(domain_context.get("phase_goal") or "")[:500],
            expected_observations=tuple(
                str(item)[:200]
                for item in _list(domain_context.get("expected_observations"))[:5]
            ),
            intelligence_summary={
                "facts": len(intelligence.facts),
                "findings": len(intelligence.findings),
                "open_hypotheses": sum(
                    item.status is HypothesisStatus.OPEN
                    for item in intelligence.hypotheses
                ),
                "failed_attempts": len(intelligence.failed_attempts),
                "open_questions": [
                    item.question[:300]
                    for item in intelligence.open_questions
                    if item.status is OpenQuestionStatus.OPEN
                ][:5],
            },
            previous_experiments=tuple(previous),
            relevant_experience=tuple(bounded_experience),
        )


class HypothesisGenerator:
    """Generate multiple deterministic candidates from existing state only."""

    def __init__(self, *, limit: int = 8) -> None:
        if limit <= 0:
            raise ValueError("hypothesis candidate limit must be positive")
        self.limit = limit

    def generate(
        self,
        *,
        analysis: AnalysisResult,
        observation: Observation,
        intelligence: IntelligenceState,
        domain_context: Mapping[str, Any],
        research_context: ResearchContext,
    ) -> list[HypothesisCandidate]:
        domain = research_context.domain
        observation_artifacts = [
            ArtifactReference(artifact_id, "hypothesis_source")
            for result in observation.tool_results
            for artifact_id in result.artifact_refs
            if artifact_id.strip()
        ]
        candidates: list[HypothesisCandidate] = []
        for suggestion in analysis.knowledge_updates:
            if suggestion.kind != "hypothesis" or suggestion.operation != "add":
                continue
            payload = suggestion.payload
            statement = str(payload.get("statement", "")).strip()
            if not statement:
                continue
            references = list(suggestion.artifact_refs) or observation_artifacts
            candidates.append(
                self._candidate(
                    statement=statement,
                    domain=str(payload.get("domain") or domain),
                    source=HypothesisSource.ANALYZER,
                    confidence=_numeric_confidence(payload.get("confidence"), analysis.confidence),
                    priority=enum_from(payload.get("priority"), Priority, Priority.MEDIUM),
                    goal=str(payload.get("experiment_goal") or f"test whether {statement}"),
                    expected=str(payload.get("expected_result") or "observable evidence recorded"),
                    artifacts=references,
                    rationale="Analyzer proposed a testable explanation.",
                    evidence_value=0.8 if references else 0.55,
                    experiment_type=str(payload.get("experiment_type", "")),
                    evidence_type=str(payload.get("evidence_type", "")),
                    experiment_context=(
                        dict(payload.get("experiment_context", {}))
                        if isinstance(payload.get("experiment_context"), Mapping)
                        else {}
                    ),
                )
            )
        for hypothesis in intelligence.hypotheses:
            if hypothesis.status is not HypothesisStatus.OPEN:
                continue
            candidates.append(
                self._candidate(
                    statement=hypothesis.statement,
                    domain=hypothesis.domain,
                    source=hypothesis.source,
                    confidence=_numeric_confidence(hypothesis.confidence, 0.5),
                    priority=hypothesis.priority,
                    goal=f"collect discriminating evidence for {hypothesis.statement}",
                    expected="observable evidence recorded",
                    artifacts=hypothesis.related_artifacts,
                    influence=hypothesis.experience_influence,
                    rationale="An OPEN IntelligenceState hypothesis requires evaluation.",
                    evidence_value=0.7 if hypothesis.related_artifacts else 0.45,
                    hypothesis_id=hypothesis.id,
                )
            )
        for question in intelligence.open_questions:
            if question.status is not OpenQuestionStatus.OPEN:
                continue
            candidates.append(
                self._candidate(
                    statement=f"Evidence can resolve the open question: {question.question}",
                    domain=domain,
                    source=HypothesisSource.INTELLIGENCE,
                    confidence=0.4,
                    priority=question.priority,
                    goal=f"collect evidence that resolves: {question.question}",
                    expected="question-relevant evidence recorded",
                    artifacts=observation_artifacts,
                    rationale="An unresolved IntelligenceState question has decision value.",
                    evidence_value=0.65,
                )
            )
        for item in _list(domain_context.get("hypothesis_candidates")):
            if not isinstance(item, Mapping) or not str(item.get("statement", "")).strip():
                continue
            candidates.append(
                self._candidate(
                    statement=str(item["statement"]),
                    domain=domain,
                    source=HypothesisSource.DOMAIN_RUNTIME,
                    confidence=float(item.get("confidence", 0.4)),
                    priority=enum_from(item.get("priority"), Priority, Priority.MEDIUM),
                    goal=str(item.get("goal") or "collect phase-relevant evidence"),
                    expected=str(item.get("expected_result") or "phase evidence recorded"),
                    artifacts=observation_artifacts,
                    rationale=f"The {research_context.phase} domain phase identified an evidence gap.",
                    evidence_value=float(item.get("evidence_value", 0.5)),
                    experiment_type=str(item.get("experiment_type", "")),
                    evidence_type=str(item.get("evidence_type", "")),
                    experiment_context=(
                        dict(item.get("context", {}))
                        if isinstance(item.get("context"), Mapping)
                        else {}
                    ),
                )
            )
        for experience in research_context.relevant_experience:
            experience_id = str(experience.get("id", ""))
            category = str(experience.get("category", "pattern"))
            candidates.append(
                self._candidate(
                    statement=f"Current {domain} evidence may match the reusable {category} pattern.",
                    domain=domain,
                    source=HypothesisSource.EXPERIENCE,
                    confidence=min(0.7, float(experience.get("confidence", 0.4))),
                    priority=Priority.MEDIUM,
                    goal=str(experience.get("strategy") or f"test the {category} pattern"),
                    expected="pattern-relevant evidence recorded",
                    artifacts=observation_artifacts,
                    influence=[experience_id] if experience_id else [],
                    rationale="A sanitized retrieved experience supplied a strategy, not a conclusion.",
                    evidence_value=0.55,
                )
            )
        resolved = {
            item.statement.strip().lower()
            for item in intelligence.hypotheses
            if item.status is not HypothesisStatus.OPEN
        }
        merged: dict[str, HypothesisCandidate] = {}
        for candidate in candidates:
            normalized = candidate.statement.strip().lower()
            if normalized in resolved:
                continue
            self._apply_experience(candidate, research_context.relevant_experience)
            current = merged.get(normalized)
            if current is None:
                merged[normalized] = candidate
                continue
            current.related_artifacts = _unique_artifacts(
                [*current.related_artifacts, *candidate.related_artifacts]
            )
            current.experience_influence = list(
                dict.fromkeys(
                    [*current.experience_influence, *candidate.experience_influence]
                )
            )
            if _source_rank(candidate.source) > _source_rank(current.source):
                current.source = candidate.source
            if _priority_rank(candidate.priority) > _priority_rank(current.priority):
                current.priority = candidate.priority
            current.confidence = max(current.confidence, candidate.confidence)
            current.evidence_value = max(current.evidence_value, candidate.evidence_value)
            if not current.experiment_type and candidate.experiment_type:
                current.experiment_type = candidate.experiment_type
            if not current.evidence_type and candidate.evidence_type:
                current.evidence_type = candidate.evidence_type
            if not current.experiment_context and candidate.experiment_context:
                current.experiment_context = dict(candidate.experiment_context)
            if candidate.hypothesis_id:
                current.hypothesis_id = candidate.hypothesis_id
        return list(merged.values())[: self.limit]

    @staticmethod
    def _candidate(
        *,
        statement: str,
        domain: str,
        source: HypothesisSource,
        confidence: float,
        priority: Priority,
        goal: str,
        expected: str,
        artifacts: Iterable[ArtifactReference],
        rationale: str,
        evidence_value: float,
        influence: Iterable[str] = (),
        hypothesis_id: str = "",
        experiment_type: str = "",
        evidence_type: str = "",
        experiment_context: Mapping[str, Any] | None = None,
    ) -> HypothesisCandidate:
        return HypothesisCandidate(
            statement=statement,
            domain=domain,
            source=source,
            confidence=max(0.0, min(1.0, float(confidence))),
            priority=priority,
            suggested_goal=goal,
            expected_result=expected,
            related_artifacts=_unique_artifacts(artifacts),
            experience_influence=list(dict.fromkeys(influence)),
            rationale=rationale,
            evidence_value=max(0.0, min(1.0, float(evidence_value))),
            hypothesis_id=hypothesis_id,
            experiment_type=experiment_type,
            evidence_type=evidence_type,
            experiment_context=dict(experiment_context or {}),
        )

    @staticmethod
    def _apply_experience(
        candidate: HypothesisCandidate,
        experience: Sequence[Mapping[str, Any]],
    ) -> None:
        candidate_tokens = _tokens(
            f"{candidate.domain} {candidate.statement} {candidate.suggested_goal}"
        )
        for item in experience:
            record_tokens = _tokens(
                " ".join(
                    str(item.get(key, ""))
                    for key in ("domain", "category", "trigger", "pattern", "strategy", "lesson")
                )
            )
            if candidate_tokens.intersection(record_tokens):
                record_id = str(item.get("id", ""))
                if record_id and record_id not in candidate.experience_influence:
                    candidate.experience_influence.append(record_id)


class ExperimentPrioritizer:
    """Rank candidates by value while penalizing repeated failed tests."""

    def rank(
        self,
        candidates: Sequence[HypothesisCandidate],
        *,
        phase: str,
        runtime_records: Sequence[Any],
    ) -> list[HypothesisCandidate]:
        for candidate in candidates:
            reasons = [f"priority={candidate.priority.value.lower()}"]
            score = {Priority.LOW: 0.1, Priority.MEDIUM: 0.2, Priority.HIGH: 0.3}[
                candidate.priority
            ]
            score += candidate.confidence * 0.3
            score += candidate.evidence_value * 0.25
            if candidate.source is HypothesisSource.DOMAIN_RUNTIME:
                score += 0.1
                reasons.append(f"phase={phase.lower()}")
            if candidate.experience_influence:
                score += min(0.1, 0.025 * len(candidate.experience_influence))
                reasons.append("experience-influenced")
            previous_failures = sum(
                str(getattr(item, "hypothesis_id", "")) == candidate.hypothesis_id
                and (
                    str(getattr(getattr(item, "status", ""), "value", "")) == "FAILED"
                    or str(
                        getattr(
                            getattr(getattr(item, "evaluation", None), "status", ""),
                            "value",
                            "",
                        )
                    )
                    == "CONTRADICTED"
                )
                for item in runtime_records
                if candidate.hypothesis_id
            )
            if previous_failures:
                score -= min(0.35, previous_failures * 0.15)
                reasons.append(f"previous-failures={previous_failures}")
            candidate.score = round(max(0.0, score), 4)
            candidate.priority_reasons = reasons
        return sorted(
            candidates,
            key=lambda item: (
                item.score,
                _priority_rank(item.priority),
                item.confidence,
                item.candidate_id,
            ),
            reverse=True,
        )


def _numeric_confidence(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    return {
        "LOW": 0.25,
        "MEDIUM": 0.5,
        "HIGH": 0.75,
        "CONFIRMED": 1.0,
    }.get(str(getattr(value, "value", value)).upper(), default)


def _unique_artifacts(
    references: Iterable[ArtifactReference],
) -> list[ArtifactReference]:
    result: list[ArtifactReference] = []
    seen: set[tuple[str, str]] = set()
    for item in references:
        key = (item.artifact_id, item.relation_type)
        if item.artifact_id.strip() and key not in seen:
            result.append(item)
            seen.add(key)
    return result


def _priority_rank(priority: Priority) -> int:
    return {Priority.LOW: 1, Priority.MEDIUM: 2, Priority.HIGH: 3}[priority]


def _source_rank(source: HypothesisSource) -> int:
    return {
        HypothesisSource.EXPERIENCE: 1,
        HypothesisSource.INTELLIGENCE: 2,
        HypothesisSource.DOMAIN_RUNTIME: 3,
        HypothesisSource.ANALYZER: 4,
        HypothesisSource.MANUAL: 5,
    }[source]


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []

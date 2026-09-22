"""Bounded R6 experiment context for Planner decisions."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict

from agent.intelligence.models import HypothesisStatus
from agent.intelligence.store import IntelligenceStore


class ExperimentContextBuilder:
    """Expose only bounded current hypotheses, recent experiments, and evidence."""

    def __init__(
        self,
        store: IntelligenceStore,
        *,
        hypothesis_limit: int = 5,
        experiment_limit: int = 5,
        evidence_limit: int = 8,
    ) -> None:
        for name, value in (
            ("hypothesis_limit", hypothesis_limit),
            ("experiment_limit", experiment_limit),
            ("evidence_limit", evidence_limit),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be an integer > 0")
        self.store = store
        self.hypothesis_limit = hypothesis_limit
        self.experiment_limit = experiment_limit
        self.evidence_limit = evidence_limit

    def build(self, runtime_state: Any = None) -> Dict[str, Any]:
        current_hypotheses = [
            item
            for item in self.store.state.hypotheses
            if item.status is HypothesisStatus.OPEN
        ][-self.hypothesis_limit :]
        recent_experiments = self.store.state.experiments[-self.experiment_limit :]
        recent_evidence = self.store.state.evidence[-self.evidence_limit :]
        runtime_records = list(getattr(runtime_state, "records", []))[
            -self.experiment_limit :
        ]
        active_candidates = list(
            getattr(runtime_state, "active_candidates", [])
        )[: self.hypothesis_limit]
        decision_history = list(
            getattr(runtime_state, "decision_history", [])
        )[-self.experiment_limit :]
        follow_up_suggestions = list(
            getattr(runtime_state, "follow_up_suggestions", [])
        )[-self.experiment_limit :]
        return {
            "current_hypotheses": [
                {
                    "id": item.id,
                    "statement": item.statement[:500],
                    "status": item.status.value,
                    "confidence": (
                        item.confidence.value
                        if hasattr(item.confidence, "value")
                        else item.confidence
                    ),
                    "domain": item.domain,
                    "source": item.source.value,
                    "priority": item.priority.value,
                    "evidence_refs": list(item.evidence_refs[-5:]),
                    "experience_influence": list(item.experience_influence[-5:]),
                }
                for item in current_hypotheses
            ],
            "recent_experiments": [asdict(item) for item in recent_experiments],
            "evidence_summary": [
                {
                    "evidence_id": item.evidence_id,
                    "experiment_id": item.experiment_id,
                    "hypothesis_id": item.hypothesis_id,
                    "observation_id": item.observation_id,
                    "source": item.source,
                    "observation": item.observation[:1000],
                    "artifact_refs": [asdict(reference) for reference in item.artifact_refs],
                    "timestamp": item.timestamp,
                }
                for item in recent_evidence
            ],
            "experiment_runtime": [
                {
                    "experiment_id": item.experiment_id,
                    "hypothesis_id": item.hypothesis_id,
                    "status": item.status.value,
                    "evidence_count": len(item.evidence_ids),
                    "evaluation": (
                        item.evaluation.status.value
                        if item.evaluation is not None
                        else None
                    ),
                    "evaluation_rationale": (
                        item.evaluation.rationale
                        if item.evaluation is not None
                        else ""
                    ),
                }
                for item in runtime_records
            ],
            "autonomous_experiment_loop": {
                "iteration": int(getattr(runtime_state, "loop_iteration", 0)),
                "active_candidates": [
                    {
                        "candidate_id": item.candidate_id,
                        "hypothesis_id": item.hypothesis_id,
                        "statement": item.statement[:500],
                        "source": item.source.value,
                        "confidence": item.confidence,
                        "priority": item.priority.value,
                        "score": item.score,
                        "suggested_goal": item.suggested_goal[:500],
                        "expected_result": item.expected_result[:500],
                        "experience_influence": list(item.experience_influence),
                        "priority_reasons": list(item.priority_reasons),
                    }
                    for item in active_candidates
                ],
                "follow_up_suggestions": [
                    dict(item) for item in follow_up_suggestions
                ],
                "decision_history": [
                    item.to_dict() for item in decision_history
                ],
            },
            "limits": {
                "current_hypotheses": self.hypothesis_limit,
                "recent_experiments": self.experiment_limit,
                "evidence_summary": self.evidence_limit,
                "experiment_runtime": self.experiment_limit,
                "active_candidates": self.hypothesis_limit,
                "decision_history": self.experiment_limit,
            },
        }

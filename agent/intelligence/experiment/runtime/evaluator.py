"""Evidence construction and deterministic R10.1 experiment evaluation."""

from __future__ import annotations

import json
import re
from typing import Mapping
from typing import Iterable, Sequence

from agent.intelligence.experiment.models import EvidenceRecord, Experiment
from agent.intelligence.experiment.runtime.experiment_runtime import (
    ExperimentEvaluation,
    ExperimentEvaluationStatus,
)
from agent.intelligence.models import ArtifactReference
from agent.runtime.contracts import ToolResult


class EvidenceProvenanceError(ValueError):
    """Raised when a ToolResult cannot support a traceable evidence record."""


class EvidenceFactory:
    """Convert one ToolResult into evidence with mandatory provenance."""

    def __init__(self, *, output_limit: int = 4000) -> None:
        if not isinstance(output_limit, int) or isinstance(output_limit, bool) or output_limit <= 0:
            raise ValueError("evidence output_limit must be an integer > 0")
        self.output_limit = output_limit

    def create(
        self,
        tool_result: ToolResult,
        *,
        experiment_id: str,
        hypothesis_id: str,
        observation_id: str,
    ) -> EvidenceRecord:
        for name, value in (
            ("experiment_id", experiment_id),
            ("hypothesis_id", hypothesis_id),
            ("observation_id", observation_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise EvidenceProvenanceError(f"evidence requires {name}")
        artifact_ids = list(
            dict.fromkeys(item for item in tool_result.artifact_refs if item.strip())
        )
        if not artifact_ids:
            raise EvidenceProvenanceError("evidence requires at least one artifact reference")
        observation = self._observation(tool_result)
        return EvidenceRecord(
            experiment_id=experiment_id,
            hypothesis_id=hypothesis_id,
            observation_id=observation_id,
            source=f"ToolResult:{tool_result.tool_name}:{tool_result.call_id}",
            observation=observation,
            artifact_refs=[
                ArtifactReference(item, "experiment_evidence")
                for item in artifact_ids
            ],
        )

    def _observation(self, result: ToolResult) -> str:
        parts = [
            f"tool={result.tool_name}",
            f"call_id={result.call_id}",
            f"success={str(result.success).lower()}",
            f"exit_code={result.exit_code if result.exit_code is not None else 'none'}",
        ]
        for name, value in (
            ("stdout", result.stdout),
            ("stderr", result.stderr),
            ("error", result.error or ""),
        ):
            if value:
                parts.append(f"{name}={value[:self.output_limit]}")
        metadata = result.metadata
        web_evidence = metadata.get("web_evidence") if isinstance(metadata, Mapping) else None
        if isinstance(web_evidence, list) and web_evidence:
            parts.append(
                "web_evidence="
                + json.dumps(web_evidence[:16], ensure_ascii=False, sort_keys=True)[
                    : self.output_limit
                ]
            )
        response_repeat = metadata.get("response_repeat") if isinstance(metadata, Mapping) else None
        if isinstance(response_repeat, Mapping):
            previous = response_repeat.get("previous_observations", 0)
            parts.append(f"response_repeat=true; previous_observations={previous}")
        return "; ".join(parts)


class ExperimentEvaluator:
    """Classify evidence without modifying a Hypothesis or executing a Tool."""

    _STOP_WORDS = frozenset(
        {
            "a",
            "an",
            "and",
            "is",
            "of",
            "the",
            "to",
            "with",
        }
    )
    _CONTRADICTIONS = {
        "changed": {"unchanged", "same", "identical"},
        "changes": {"unchanged", "same", "identical"},
        "different": {"same", "identical", "unchanged"},
        "differs": {"same", "identical", "unchanged"},
        "present": {"absent", "missing"},
        "contains": {"absent", "missing"},
        "success": {"failed", "failure", "denied", "error"},
    }

    def evaluate(
        self,
        experiment: Experiment,
        evidence: Sequence[EvidenceRecord],
        tool_results: Sequence[ToolResult],
    ) -> ExperimentEvaluation:
        evidence_ids = tuple(item.evidence_id for item in evidence)
        if not evidence:
            return ExperimentEvaluation(
                experiment.experiment_id,
                ExperimentEvaluationStatus.INCONCLUSIVE,
                "No provenance-complete evidence was produced.",
                evidence_ids,
            )
        if not tool_results or any(not item.success for item in tool_results):
            return ExperimentEvaluation(
                experiment.experiment_id,
                ExperimentEvaluationStatus.INCONCLUSIVE,
                "Controlled execution did not complete successfully.",
                evidence_ids,
            )
        expected_tokens = self._tokens(experiment.expected_result)
        observed_tokens = self._tokens(" ".join(item.observation for item in evidence))
        if "response_repeat" in observed_tokens and self._expects_change(expected_tokens):
            return ExperimentEvaluation(
                experiment.experiment_id,
                ExperimentEvaluationStatus.CONTRADICTED,
                "Captured response fingerprint matches an earlier observation, contrary to the expected change.",
                evidence_ids,
            )
        for expected, contradictory in self._CONTRADICTIONS.items():
            if expected in expected_tokens and contradictory.intersection(observed_tokens):
                return ExperimentEvaluation(
                    experiment.experiment_id,
                    ExperimentEvaluationStatus.CONTRADICTED,
                    "Evidence contains an explicit outcome contrary to the expected result.",
                    evidence_ids,
                )
        significant = expected_tokens - self._STOP_WORDS
        overlap = significant.intersection(observed_tokens)
        if significant and len(overlap) / len(significant) >= 0.6:
            return ExperimentEvaluation(
                experiment.experiment_id,
                ExperimentEvaluationStatus.SUPPORTED,
                "Evidence matches the material terms of the expected result.",
                evidence_ids,
            )
        return ExperimentEvaluation(
            experiment.experiment_id,
            ExperimentEvaluationStatus.INCONCLUSIVE,
            "Evidence is traceable but does not determine the expected result.",
            evidence_ids,
        )

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return set(re.findall(r"[a-z0-9_]+", value.lower()))

    @staticmethod
    def _expects_change(tokens: set[str]) -> bool:
        return bool(tokens.intersection({"change", "changed", "changes", "different", "differs", "difference"}))

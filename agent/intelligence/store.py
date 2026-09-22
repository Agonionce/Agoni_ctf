"""CRUD and JSON persistence for structured IntelligenceState."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, TypeVar

from agent.intelligence.experiment.models import EvidenceRecord, Experiment
from agent.intelligence.models import (
    ArtifactLink,
    ArtifactReference,
    AttackSurface,
    Credential,
    EndpointFinding,
    Fact,
    FailedAttempt,
    Finding,
    Hypothesis,
    IntelligenceState,
    OpenQuestion,
)


ItemT = TypeVar("ItemT")


class IntelligenceStore:
    """The only CRUD entry point for R2 challenge knowledge."""

    def __init__(self, state: IntelligenceState) -> None:
        self.state = state

    @classmethod
    def create(cls, challenge_id: str) -> "IntelligenceStore":
        return cls(IntelligenceState(challenge_id=challenge_id))

    @classmethod
    def load(cls, path: str | Path) -> "IntelligenceStore":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise ValueError("intelligence JSON must be an object")
        return cls(IntelligenceState.from_dict(raw))

    def save(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(f"{destination.suffix}.tmp")
        temporary.write_text(
            json.dumps(self.state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(destination)
        return destination

    def add_fact(self, item: Fact) -> Fact:
        return self._add("facts", item, item.artifact_refs)

    def add_hypothesis(self, item: Hypothesis) -> Hypothesis:
        return self._add("hypotheses", item, item.related_artifacts)

    def add_failed_attempt(self, item: FailedAttempt) -> FailedAttempt:
        return self._add("failed_attempts", item, item.artifact_refs)

    def add_finding(self, item: Finding) -> Finding:
        return self._add("findings", item, item.related_artifacts)

    def add_credential(self, item: Credential) -> Credential:
        return self._add("credentials", item, [])

    def add_attack_surface(self, item: AttackSurface) -> AttackSurface:
        return self._add("attack_surface", item, item.artifact_refs)

    def add_endpoint_finding(self, item: EndpointFinding) -> EndpointFinding:
        existing = next(
            (
                current
                for current in self.state.endpoint_findings
                if current.path == item.path and current.method == item.method
            ),
            None,
        )
        if existing is not None:
            existing.parameters = sorted(
                {*existing.parameters, *item.parameters}
            )
            sources = {
                source.strip()
                for source in [*existing.source.split(","), *item.source.split(",")]
                if source.strip()
            }
            existing.source = ", ".join(sorted(sources))
            order = {
                "LOW": 0,
                "MEDIUM": 1,
                "HIGH": 2,
                "CONFIRMED": 3,
            }
            if order[item.confidence.value] > order[existing.confidence.value]:
                existing.confidence = item.confidence
            existing.artifact_refs = list(
                dict.fromkeys([*existing.artifact_refs, *item.artifact_refs])
            )
            self._link_artifacts(
                "endpoint_findings",
                existing.id,
                item.artifact_refs,
            )
            self.state.touch()
            return existing
        return self._add("endpoint_findings", item, item.artifact_refs)

    def add_open_question(self, item: OpenQuestion) -> OpenQuestion:
        return self._add("open_questions", item, [])

    def add_experiment(self, item: Experiment) -> Experiment:
        return self._add("experiments", item, [])

    def add_evidence(self, item: EvidenceRecord) -> EvidenceRecord:
        return self._add("evidence", item, item.artifact_refs)

    def get_fact(self, item_id: str) -> Optional[Fact]:
        return self._get("facts", item_id)

    def get_hypothesis(self, item_id: str) -> Optional[Hypothesis]:
        return self._get("hypotheses", item_id)

    def get_failed_attempt(self, item_id: str) -> Optional[FailedAttempt]:
        return self._get("failed_attempts", item_id)

    def get_finding(self, item_id: str) -> Optional[Finding]:
        return self._get("findings", item_id)

    def get_credential(self, item_id: str) -> Optional[Credential]:
        return self._get("credentials", item_id)

    def get_attack_surface(self, item_id: str) -> Optional[AttackSurface]:
        return self._get("attack_surface", item_id)

    def get_endpoint_finding(self, item_id: str) -> Optional[EndpointFinding]:
        return self._get("endpoint_findings", item_id)

    def get_open_question(self, item_id: str) -> Optional[OpenQuestion]:
        return self._get("open_questions", item_id)

    def get_experiment(self, item_id: str) -> Optional[Experiment]:
        return self._get("experiments", item_id, identity_field="experiment_id")

    def get_evidence(self, item_id: str) -> Optional[EvidenceRecord]:
        return self._get("evidence", item_id, identity_field="evidence_id")

    def update_fact(self, item_id: str, **changes: Any) -> Fact:
        return self._update("facts", item_id, changes)

    def update_hypothesis(self, item_id: str, **changes: Any) -> Hypothesis:
        item = self._update("hypotheses", item_id, changes)
        references = changes.get("related_artifacts", [])
        self._link_artifacts("hypotheses", item_id, references)
        return item

    def update_failed_attempt(self, item_id: str, **changes: Any) -> FailedAttempt:
        return self._update("failed_attempts", item_id, changes)

    def update_finding(self, item_id: str, **changes: Any) -> Finding:
        return self._update("findings", item_id, changes)

    def update_credential(self, item_id: str, **changes: Any) -> Credential:
        return self._update("credentials", item_id, changes)

    def update_attack_surface(self, item_id: str, **changes: Any) -> AttackSurface:
        return self._update("attack_surface", item_id, changes)

    def update_endpoint_finding(
        self,
        item_id: str,
        **changes: Any,
    ) -> EndpointFinding:
        return self._update("endpoint_findings", item_id, changes)

    def update_open_question(self, item_id: str, **changes: Any) -> OpenQuestion:
        return self._update("open_questions", item_id, changes)

    def remove(self, collection: str, item_id: str) -> bool:
        items = self._collection(collection)
        if collection == "hypotheses" and any(
            item.hypothesis_id == item_id for item in self.state.experiments
        ):
            raise ValueError("cannot remove a hypothesis with experiments")
        if collection == "experiments" and any(
            item.experiment_id == item_id for item in self.state.evidence
        ):
            raise ValueError("cannot remove an experiment with evidence")
        if collection == "evidence" and any(
            item_id in item.evidence_refs for item in self.state.hypotheses
        ):
            raise ValueError("cannot remove evidence referenced by a hypothesis")
        identity_field = {
            "experiments": "experiment_id",
            "evidence": "evidence_id",
        }.get(collection, "id")
        for index, item in enumerate(items):
            if getattr(item, identity_field, None) == item_id:
                items.pop(index)
                self.state.artifact_links = [
                    link for link in self.state.artifact_links if link.entity_id != item_id
                ]
                self.state.touch()
                return True
        return False

    def query_facts(
        self,
        *,
        category: str | None = None,
        keywords: Iterable[str] = (),
    ) -> List[Fact]:
        required = [word.lower() for word in keywords if word.strip()]
        results = []
        for fact in self.state.facts:
            if category is not None and fact.category != category:
                continue
            haystack = f"{fact.category} {fact.content}".lower()
            if all(word in haystack for word in required):
                results.append(fact)
        return results

    def query_failed_attempts(
        self,
        *,
        category: str | None = None,
        keywords: Iterable[str] = (),
    ) -> List[FailedAttempt]:
        required = [word.lower() for word in keywords if word.strip()]
        results = []
        for attempt in self.state.failed_attempts:
            if category is not None and attempt.category != category:
                continue
            haystack = " ".join(
                [
                    attempt.category,
                    attempt.target,
                    attempt.method,
                    attempt.input_payload,
                    attempt.result,
                    attempt.reason,
                ]
            ).lower()
            if all(word in haystack for word in required):
                results.append(attempt)
        return results

    def summary(self, *, mask_credentials: bool = True) -> Dict[str, Any]:
        return {
            "challenge_id": self.state.challenge_id,
            "facts": len(self.state.facts),
            "hypotheses": len(self.state.hypotheses),
            "failed_attempts": len(self.state.failed_attempts),
            "findings": len(self.state.findings),
            "credentials": [
                item.safe_dict() if mask_credentials else item
                for item in self.state.credentials
            ],
            "attack_surface": len(self.state.attack_surface),
            "endpoint_findings": len(self.state.endpoint_findings),
            "open_questions": len(self.state.open_questions),
            "experiments": len(self.state.experiments),
            "evidence": len(self.state.evidence),
            "artifact_links": len(self.state.artifact_links),
        }

    def _add(
        self,
        collection: str,
        item: ItemT,
        artifact_refs: Iterable[ArtifactReference],
    ) -> ItemT:
        items = self._collection(collection)
        identity_field = {
            "experiments": "experiment_id",
            "evidence": "evidence_id",
        }.get(collection, "id")
        item_id = getattr(item, identity_field, None)
        if any(getattr(current, identity_field, None) == item_id for current in items):
            raise ValueError(f"duplicate intelligence id: {item_id or ''}")
        items.append(item)
        self._link_artifacts(collection, str(item_id), artifact_refs)
        self.state.touch()
        return item

    def _get(
        self,
        collection: str,
        item_id: str,
        *,
        identity_field: str = "id",
    ) -> Optional[Any]:
        return next(
            (
                item
                for item in self._collection(collection)
                if getattr(item, identity_field, None) == item_id
            ),
            None,
        )

    def _update(self, collection: str, item_id: str, changes: Dict[str, Any]) -> Any:
        item = self._get(collection, item_id)
        if item is None:
            raise KeyError(item_id)
        allowed = set(vars(item)) - {"id", "created_at"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"unknown or immutable fields: {', '.join(sorted(unknown))}")
        for field_name, value in changes.items():
            setattr(item, field_name, value)
        self.state.touch()
        return item

    def _collection(self, name: str) -> List[Any]:
        if name not in {
            "facts",
            "hypotheses",
            "failed_attempts",
            "findings",
            "credentials",
            "attack_surface",
            "endpoint_findings",
            "open_questions",
            "experiments",
            "evidence",
        }:
            raise ValueError(f"unknown intelligence collection: {name}")
        return getattr(self.state, name)

    def _link_artifacts(
        self,
        collection: str,
        item_id: str,
        artifact_refs: Iterable[ArtifactReference],
    ) -> None:
        entity_type = {
            "facts": "fact",
            "hypotheses": "hypothesis",
            "failed_attempts": "failed_attempt",
            "findings": "finding",
            "credentials": "credential",
            "attack_surface": "attack_surface",
            "endpoint_findings": "endpoint_finding",
            "open_questions": "open_question",
            "experiments": "experiment",
            "evidence": "evidence",
        }[collection]
        for reference in artifact_refs:
            link = ArtifactLink(
                artifact_id=reference.artifact_id,
                relation_type=reference.relation_type,
                entity_type=entity_type,
                entity_id=item_id,
            )
            if link not in self.state.artifact_links:
                self.state.artifact_links.append(link)

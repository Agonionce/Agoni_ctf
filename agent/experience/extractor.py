"""Rule-driven R7 experience extraction with no LLM or external service."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable, Sequence

from agent.experience.models import ExperienceRecord
from agent.intelligence.experiment.models import EvidenceRecord, Experiment, ExperimentStatus
from agent.intelligence.models import HypothesisStatus, IntelligenceState
from agent.runtime.contracts import RunState, RunStatus


@dataclass(frozen=True)
class _ExperienceRule:
    domain: str
    category: str
    keywords: tuple[str, ...]
    trigger: str
    pattern: str
    strategy: str
    lesson: str
    failure: str


_RULES = (
    _ExperienceRule(
        domain="web",
        category="sql_injection",
        keywords=("sql", "database", "union", "syntax error", "sqli"),
        trigger="A parameter changes database-like response behavior.",
        pattern="Database behavior should be identified before payload selection.",
        strategy=(
            "Use low-impact controlled comparisons to identify database behavior "
            "before selecting a payload family."
        ),
        lesson=(
            "Different responses are reusable evidence about behavior, not proof of "
            "a specific exploit path."
        ),
        failure=(
            "A failed UNION-style test should not be repeated before database "
            "behavior and input handling are better understood."
        ),
    ),
    _ExperienceRule(
        domain="web",
        category="authentication",
        keywords=("authentication", "login", "cookie", "session", "auth"),
        trigger="A login flow depends on cookies, sessions, or state transitions.",
        pattern="Authentication behavior should be mapped before testing bypass ideas.",
        strategy="Compare authorized state transitions and session changes one variable at a time.",
        lesson="Session evidence is challenge-specific; only the analysis sequence is reusable.",
        failure="Repeating credential guesses is not a substitute for understanding the state model.",
    ),
    _ExperienceRule(
        domain="reverse",
        category="binary_analysis",
        keywords=("binary", "elf", "disassembly", "decompile", "checksec", "assembly"),
        trigger="A binary requires structural triage before deeper analysis.",
        pattern="Binary properties and protections should be identified before technique selection.",
        strategy="Perform deterministic format, architecture, protection, and string triage first.",
        lesson="Early structural evidence narrows later static or dynamic analysis choices.",
        failure="Deep analysis without basic triage often repeats work or follows the wrong architecture.",
    ),
    _ExperienceRule(
        domain="crypto",
        category="crypto_pattern",
        keywords=("cipher", "rsa", "aes", "encoding", "hash", "modulus", "crypto"),
        trigger="Ciphertext or parameters expose a recognizable cryptographic structure.",
        pattern="Classify the primitive and representation before attempting recovery.",
        strategy="Separate encoding, primitive identification, parameter checks, and recovery tests.",
        lesson="A structural match guides experiments but does not by itself reveal the solution.",
        failure="Brute force before classification wastes budget and obscures useful structure.",
    ),
)


class ExperienceExtractor:
    """Extract generic reusable records from a completed run using local rules."""

    TERMINAL_STATUSES = {
        RunStatus.SOLVED,
        RunStatus.BLOCKED,
        RunStatus.FAILED,
        RunStatus.BUDGET_EXHAUSTED,
        RunStatus.ABORTED,
    }

    def extract(
        self,
        run_state: RunState,
        intelligence_state: IntelligenceState,
        experiment_history: Sequence[Experiment] | None = None,
        evidence: Sequence[EvidenceRecord] | None = None,
    ) -> list[ExperienceRecord]:
        if run_state.status not in self.TERMINAL_STATUSES:
            raise ValueError("experience extraction requires a completed run")
        if intelligence_state.challenge_id != run_state.challenge.challenge_id:
            raise ValueError("run and intelligence state belong to different challenges")
        experiments = list(
            intelligence_state.experiments
            if experiment_history is None
            else experiment_history
        )
        evidence_records = list(
            intelligence_state.evidence if evidence is None else evidence
        )
        if not experiments or not evidence_records:
            return []
        self._validate_history(intelligence_state, experiments, evidence_records)

        signal_text = self._signal_text(
            run_state,
            intelligence_state,
            experiments,
            evidence_records,
        )
        confirmed = any(
            item.status is HypothesisStatus.CONFIRMED
            for item in intelligence_state.hypotheses
        )
        failed = any(item.status is ExperimentStatus.FAILED for item in experiments)
        confidence = min(
            0.95,
            0.6 + (0.1 if confirmed else 0.0) + (0.1 if failed else 0.0) + 0.1,
        )
        records: list[ExperienceRecord] = []
        for rule in _RULES:
            matches = sum(keyword in signal_text for keyword in rule.keywords)
            domain_match = (run_state.challenge.category or "").lower() == rule.domain
            if matches < 2 and not (domain_match and matches >= 1):
                continue
            domain = self._record_domain(run_state, rule)
            records.append(
                ExperienceRecord(
                    id=self._stable_id(run_state.run_id, rule.category, rule.pattern),
                    domain=domain,
                    category=rule.category,
                    trigger=rule.trigger,
                    pattern=rule.pattern,
                    strategy=rule.strategy,
                    lesson=rule.lesson,
                    failure=rule.failure,
                    source_run=run_state.run_id,
                    confidence=confidence,
                )
            )
        return records

    @staticmethod
    def _validate_history(
        intelligence_state: IntelligenceState,
        experiments: Sequence[Experiment],
        evidence: Sequence[EvidenceRecord],
    ) -> None:
        hypothesis_ids = {item.id for item in intelligence_state.hypotheses}
        experiment_by_id = {item.experiment_id: item for item in experiments}
        if len(experiment_by_id) != len(experiments):
            raise ValueError("experience history contains duplicate experiment ids")
        for experiment in experiments:
            if experiment.hypothesis_id not in hypothesis_ids:
                raise ValueError("experience history references an unknown hypothesis")
            if experiment.status not in {
                ExperimentStatus.SUCCESS,
                ExperimentStatus.FAILED,
            }:
                raise ValueError("experience extraction requires closed experiments")
        for record in evidence:
            experiment = experiment_by_id.get(record.experiment_id)
            if experiment is None:
                raise ValueError("experience evidence references an unknown experiment")
            if record.hypothesis_id != experiment.hypothesis_id:
                raise ValueError("experience evidence has an inconsistent hypothesis")

    @staticmethod
    def _signal_text(
        run_state: RunState,
        intelligence_state: IntelligenceState,
        experiments: Iterable[Experiment],
        evidence: Iterable[EvidenceRecord],
    ) -> str:
        # Source text is used only for rule matching and is never copied into a
        # record. Credentials are deliberately excluded.
        values = [
            run_state.challenge.title,
            run_state.challenge.description,
            run_state.challenge.category or "",
        ]
        values.extend(item.statement for item in intelligence_state.hypotheses)
        values.extend(item.content for item in intelligence_state.facts)
        values.extend(item.description for item in intelligence_state.findings)
        for item in experiments:
            values.extend(
                [
                    item.goal,
                    item.expected_result,
                    item.actual_result,
                    str(item.action.get("tool_name", "")),
                    " ".join(str(value) for value in item.action.get("arguments", {}).values()),
                ]
            )
        for item in evidence:
            values.extend([item.source, item.observation])
        return " ".join(values).lower()

    @staticmethod
    def _record_domain(run_state: RunState, rule: _ExperienceRule) -> str:
        category = (run_state.challenge.category or "").strip().lower()
        if rule.category == "binary_analysis" and category in {"pwn", "reverse"}:
            return category
        return rule.domain

    @staticmethod
    def _stable_id(source_run: str, category: str, pattern: str) -> str:
        value = f"{source_run}|{category}|{pattern}".encode("utf-8")
        return f"experience-{hashlib.sha256(value).hexdigest()[:12]}"

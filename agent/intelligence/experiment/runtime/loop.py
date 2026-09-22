"""R10.2 autonomous research loop coordinator.

This layer chooses what should be tested next. It has no Tool registry,
Executor, PolicyEngine, network client, or sandbox backend.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from agent.domains.manager import DomainRuntimeManager
from agent.intelligence.experiment.manager import ExperimentManager
from agent.intelligence.experiment.runtime.experiment_runtime import (
    ExperimentEvaluation,
    ExperimentRuntimeRecord,
    ExperimentRuntimeState,
)
from agent.intelligence.experiment.runtime.feedback import (
    ExperimentFeedback,
    ExperimentFeedbackManager,
)
from agent.intelligence.experiment.runtime.research import (
    DomainExperimentAdapter,
    ExperimentDecisionRecord,
    ExperimentPrioritizer,
    HypothesisCandidate,
    HypothesisGenerator,
    ResearchContextBuilder,
)
from agent.intelligence.models import HypothesisStatus
from agent.intelligence.store import IntelligenceStore
from agent.runtime.contracts import AnalysisResult, Observation


class AutonomousExperimentLoop:
    """Build the next bounded experiment recommendation after each step."""

    def __init__(
        self,
        store: IntelligenceStore,
        runtime_state: ExperimentRuntimeState,
        *,
        domain_manager: DomainRuntimeManager | None = None,
        experience_context_provider: Callable[[], Mapping[str, Any]] | None = None,
        domain_adapter: DomainExperimentAdapter | None = None,
        generator: HypothesisGenerator | None = None,
        prioritizer: ExperimentPrioritizer | None = None,
        context_builder: ResearchContextBuilder | None = None,
    ) -> None:
        if store.state.challenge_id != runtime_state.challenge_id:
            raise ValueError("experiment loop belongs to a different challenge")
        self.store = store
        self.state = runtime_state
        self.domain_manager = domain_manager
        self.experience_context_provider = experience_context_provider or (lambda: {})
        self.domain_adapter = domain_adapter or DomainExperimentAdapter()
        self.generator = generator or HypothesisGenerator()
        self.prioritizer = prioritizer or ExperimentPrioritizer()
        self.context_builder = context_builder or ResearchContextBuilder()
        self.experiment_manager = ExperimentManager(store)
        self.feedback_manager = ExperimentFeedbackManager(
            store,
            domain_manager=domain_manager,
            domain_adapter=self.domain_adapter,
        )

    def advance(
        self,
        observation: Observation,
        analysis: AnalysisResult,
    ) -> ExperimentDecisionRecord:
        existing = next(
            (
                item
                for item in self.state.decision_history
                if item.source_step == observation.step_id
            ),
            None,
        )
        if existing is not None:
            return existing
        domain_context = self.domain_adapter.build_context(self.domain_manager)
        experience_context = dict(self.experience_context_provider())
        context = self.context_builder.build(
            iteration=self.state.loop_iteration + 1,
            observation=observation,
            analysis=analysis,
            intelligence=self.store.state,
            runtime_records=self.state.records,
            domain_context=domain_context,
            experience_context=experience_context,
        )
        candidates = self.generator.generate(
            analysis=analysis,
            observation=observation,
            intelligence=self.store.state,
            domain_context=domain_context,
            research_context=context,
        )
        self._materialize(candidates)
        ranked = self.prioritizer.rank(
            candidates,
            phase=context.phase,
            runtime_records=self.state.records,
        )
        self.state.loop_iteration = context.iteration
        self.state.active_candidates = ranked
        self.state.active_hypothesis_ids = [
            item.hypothesis_id
            for item in ranked
            if item.hypothesis_id
            and (
                (hypothesis := self.store.get_hypothesis(item.hypothesis_id))
                is not None
                and hypothesis.status is HypothesisStatus.OPEN
            )
        ]
        self.state.last_research_context = context.to_dict()
        if ranked:
            selected = ranked[0]
            decision = ExperimentDecisionRecord(
                iteration=context.iteration,
                source_step=observation.step_id,
                decision="PROPOSE_EXPERIMENT",
                candidate_id=selected.candidate_id,
                hypothesis_id=selected.hypothesis_id,
                goal=selected.suggested_goal,
                expected_result=selected.expected_result,
                priority_score=selected.score,
                phase=context.phase,
                experience_influence=tuple(selected.experience_influence),
                rationale="; ".join(selected.priority_reasons),
            )
        else:
            decision = ExperimentDecisionRecord(
                iteration=context.iteration,
                source_step=observation.step_id,
                decision="GATHER_MORE_OBSERVATION",
                phase=context.phase,
                rationale="No unresolved evidence-backed hypothesis candidate is available.",
            )
        self.state.decision_history.append(decision)
        self.state.decision_history = self.state.decision_history[-50:]
        self.state.touch()
        return decision

    def apply_feedback(
        self,
        record: ExperimentRuntimeRecord,
        evaluation: ExperimentEvaluation,
    ) -> ExperimentFeedback:
        feedback = self.feedback_manager.apply(record, evaluation)
        if feedback.next_experiment_goal:
            suggestion = {
                "experiment_id": feedback.experiment_id,
                "hypothesis_id": feedback.hypothesis_id,
                "goal": feedback.next_experiment_goal,
                "expected_result": "additional discriminating evidence recorded",
                "status": "PENDING",
            }
            if suggestion not in self.state.follow_up_suggestions:
                self.state.follow_up_suggestions.append(suggestion)
                self.state.follow_up_suggestions = self.state.follow_up_suggestions[-20:]
        self.state.active_candidates = [
            item
            for item in self.state.active_candidates
            if (
                (hypothesis := self.store.get_hypothesis(item.hypothesis_id))
                is not None
                and hypothesis.status is HypothesisStatus.OPEN
            )
        ]
        self.state.active_hypothesis_ids = [
            item.id
            for item in self.store.state.hypotheses
            if item.status is HypothesisStatus.OPEN
        ]
        self.state.touch()
        return feedback

    def _materialize(self, candidates: list[HypothesisCandidate]) -> None:
        by_statement = {
            item.statement.strip().lower(): item
            for item in self.store.state.hypotheses
        }
        for candidate in candidates:
            existing = by_statement.get(candidate.statement.strip().lower())
            if existing is None:
                existing = self.experiment_manager.create_hypothesis(
                    candidate.statement,
                    candidate.domain,
                    candidate.confidence,
                    source=candidate.source,
                    priority=candidate.priority,
                    related_artifacts=candidate.related_artifacts,
                    experience_influence=candidate.experience_influence,
                )
                by_statement[candidate.statement.strip().lower()] = existing
            elif existing.status is HypothesisStatus.OPEN:
                references = list(
                    dict.fromkeys(
                        [*existing.related_artifacts, *candidate.related_artifacts]
                    )
                )
                influence = list(
                    dict.fromkeys(
                        [
                            *existing.experience_influence,
                            *candidate.experience_influence,
                        ]
                    )
                )
                self.store.update_hypothesis(
                    existing.id,
                    related_artifacts=references,
                    experience_influence=influence,
                )
            candidate.hypothesis_id = existing.id

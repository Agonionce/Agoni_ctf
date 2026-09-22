"""Fake-local R14.2-R14.4 workbench contract demonstration.

This demo opens no socket and invokes no Tool. A deterministic fake Runtime
exercises the Runtime-owned supervision, challenge-safe projections, and
explicit Experience review contracts.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from agent.challenge.experience import ChallengeExperienceManager
from agent.challenge.models import ChallengeManifest
from agent.completion.experience import ExperienceCandidateStore
from agent.completion.models import ExperienceCandidate
from agent.intelligence.checkpoint import IntelligenceCheckpoint, RuntimeStepCheckpoint
from agent.intelligence.models import Fact, Finding, Hypothesis
from agent.intelligence.store import IntelligenceStore
from agent.policy.approval import ApprovalRequest
from agent.runtime.contracts import (
    RunState,
    RunStatus,
    TerminationDecision,
    TerminationReason,
)
from agent.runtime.supervision import SupervisedRunCoordinator
from agent.workspace.manager import WorkspaceManager
from webui.projections import ChallengeProjectionService
from webui.service import UISettings


class FakeExecutor:
    def __init__(self, workspace_root: str, challenge_id: str) -> None:
        self.workspace_manager = WorkspaceManager(workspace_root)
        self.workspace_manager.create(challenge_id)

    def artifacts_for_current_workspace(self):
        return []


class FakeSupervisedRuntime:
    """Deterministic stand-in that requests approval but executes nothing."""

    def __init__(
        self,
        *,
        question,
        config,
        approval_resolver,
        resume_checkpoint,
        flag_confirmer=None,
    ) -> None:
        manifest = ChallengeManifest.from_dict(question.metadata["challenge_manifest"])
        self.state = RunState(challenge=manifest.to_challenge_spec())
        self.intelligence_store = IntelligenceStore.create(manifest.challenge_id)
        self.intelligence_store.add_fact(
            Fact(category="fixture", content="The supplied material is fake-local.")
        )
        self.intelligence_store.add_finding(
            Finding(
                title="Contained demonstration",
                description="The supervised decision path completed without a Tool.",
            )
        )
        self.intelligence_store.add_hypothesis(
            Hypothesis(
                statement="A later authorized experiment could test the fixture behavior.",
                domain="misc",
            )
        )
        self.executor = FakeExecutor(
            config["execution"]["workspace_root"],
            manifest.challenge_id,
        )
        self._approval_resolver = approval_resolver
        self._abort_requested = False
        checkpoint = IntelligenceCheckpoint(
            Path(config["checkpoint_dir"]) / f"r4_{self.state.run_id}"
        )
        self.checkpoint_handler = RuntimeStepCheckpoint(
            checkpoint,
            self.intelligence_store,
            artifacts_provider=self.executor.artifacts_for_current_workspace,
        )

    def request_abort(self) -> None:
        self._abort_requested = True

    def run(self) -> RunState:
        self.state.status = RunStatus.RUNNING
        approved = self._approval_resolver(
            ApprovalRequest(
                request_id="demo-decision",
                tool_name="workspace_read_text",
                arguments={"path": "workspace://input/demo.txt"},
                reason="fake-local contract demonstration",
                risk_level="LOW",
            )
        )
        status = RunStatus.SOLVED if approved else RunStatus.ABORTED
        reason = (
            TerminationReason.FLAG_CONFIRMED
            if approved
            else TerminationReason.EXPLICIT_ABORT
        )
        self.state.set_termination(
            TerminationDecision(status, reason, "fake-local demonstration complete")
        )
        self.checkpoint_handler.finalize(self.state)
        return self.state


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="agonionce-r14-") as raw_root:
        root = Path(raw_root)
        settings = UISettings(
            workspace_root=root / "workspace",
            experience_root=root / "experiences" / "challenges",
            global_experience_path=root / "experiences" / "global" / "experience.json",
            checkpoint_root=root / "checkpoints",
            staging_root=root / "staging",
        ).normalized()
        manifest = ChallengeManifest.create(
            name="R14 fake-local demonstration",
            domain="misc",
            description="A deterministic local presentation contract demonstration.",
            entropy="r14-demo",
        )
        manager = ChallengeExperienceManager(settings.experience_root)
        manager.create(manifest)
        coordinator = SupervisedRunCoordinator(
            workspace_root=settings.workspace_root,
            challenge_root=settings.experience_root,
            checkpoint_root=settings.checkpoint_root,
            global_experience_path=settings.global_experience_path,
            config_provider=lambda: {},
            runtime_factory=lambda **kwargs: FakeSupervisedRuntime(**kwargs),
        )

        coordinator.start(manifest.challenge_id)
        waiting = _wait_for(
            coordinator,
            manifest.challenge_id,
            lambda view: view.pending_decision is not None,
        )
        assert waiting.pending_decision is not None
        assert waiting.pending_decision.title == "读取文本材料"
        coordinator.decide(
            manifest.challenge_id,
            waiting.pending_decision.decision_id,
            approved=True,
        )
        completed = _wait_for(
            coordinator,
            manifest.challenge_id,
            lambda view: not view.active,
        )
        assert completed.status == "SOLVED"

        projections = ChallengeProjectionService(settings)
        outcomes = projections.outcomes(manifest.challenge_id)
        documents = projections.documents(manifest.challenge_id)
        assert outcomes.facts and outcomes.findings and outcomes.hypotheses
        assert documents.available

        candidate_store = ExperienceCandidateStore(
            manager.paths_for(manifest).experience_candidates_file,
            challenge_id=manifest.challenge_id,
        )
        candidate_store.replace_all(
            [
                ExperienceCandidate(
                    id="candidate-r14-demo",
                    category="parameter_behavior",
                    pattern="A bounded observation should remain separate from its explanation.",
                    strategy="Compare one controlled input against a stable baseline.",
                    lesson="Promote only evidence-backed conclusions.",
                    source_challenge=manifest.challenge_id,
                    confidence=0.8,
                )
            ]
        )
        reviewed = projections.review_candidate(
            manifest.challenge_id,
            "candidate-r14-demo",
            approved=True,
        )
        assert reviewed.status == "APPROVED"
        assert settings.global_experience_path.is_file()

    print("LOCAL_UI_SUPERVISED_WORKBENCH_OK")


def _wait_for(coordinator, challenge_id: str, predicate):
    for _ in range(200):
        view = coordinator.view(challenge_id)
        if predicate(view):
            return view
        time.sleep(0.01)
    raise RuntimeError("supervised demo did not converge")


if __name__ == "__main__":
    main()

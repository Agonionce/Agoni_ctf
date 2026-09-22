from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.challenge.experience import ChallengeExperienceManager
from agent.challenge.models import ChallengeManifest
from agent.completion.experience import ExperienceCandidateStore
from agent.completion.models import ExperienceCandidate
from agent.domains.web.state import WebRuntimeState
from agent.intelligence.checkpoint import IntelligenceCheckpoint, RuntimeStepCheckpoint
from agent.intelligence.experiment.models import EvidenceRecord, Experiment, ExperimentStatus
from agent.intelligence.models import Fact, Finding, Hypothesis, HypothesisStatus
from agent.intelligence.store import IntelligenceStore
from agent.policy.approval import ApprovalRequest
from agent.runtime.contracts import (
    FlagCandidate,
    RunState,
    RunStatus,
    TerminationDecision,
    TerminationReason,
)
from agent.runtime.supervision import SupervisedRunCoordinator
from agent.workspace.manager import WorkspaceManager
from webui.app import create_app
from webui.service import UISettings


LOCAL_ORIGIN = {"origin": "http://127.0.0.1:5173"}


class _FakeExecutor:
    def __init__(self, workspace_root: str, challenge_id: str) -> None:
        self.workspace_manager = WorkspaceManager(workspace_root)
        self.workspace_manager.create(challenge_id)

    def artifacts_for_current_workspace(self):
        return []


class _FakeRuntime:
    def __init__(
        self,
        *,
        question,
        config,
        approval_resolver,
        resume_checkpoint,
        flag_confirmer=None,
        confirm_candidate=False,
    ) -> None:
        raw_manifest = question.metadata["challenge_manifest"]
        manifest = ChallengeManifest.from_dict(raw_manifest)
        self.state = (
            resume_checkpoint.run_state
            if resume_checkpoint is not None
            else RunState(challenge=manifest.to_challenge_spec())
        )
        self.intelligence_store = (
            resume_checkpoint.intelligence_store
            if resume_checkpoint is not None
            else _sample_intelligence(manifest.challenge_id)
        )
        self.executor = _FakeExecutor(
            config["execution"]["workspace_root"],
            manifest.challenge_id,
        )
        self._approval_resolver = approval_resolver
        self._flag_confirmer = flag_confirmer
        self._confirm_candidate = confirm_candidate
        self._abort_requested = False
        self.domain_runtime_state = WebRuntimeState(
            domain="web",
            phase="application_mapping",
            challenge_id=manifest.challenge_id,
            endpoints=[
                "/",
                "/login?token=hidden",
                "/download/HTB{candidate-value}?token=private",
                "/download/HTB%7Bcandidate-value%7D",
                "/reset/token/private",
                "/Users/maxchen/private.txt",
                "/tmp/private-response.txt",
                "/var/log/app.log",
                "/users/42",
                "/home/feed",
            ],
            parameters={"query": ["/"], "password": ["/login"]},
            cookies={"session": "private-cookie"},
            technologies=["Flask"],
        )
        self.domain_runtime_state.application_model.record_endpoint(
            "/login",
            method="POST",
            parameters=["username", "password"],
            response_format="html",
        )
        checkpoint = IntelligenceCheckpoint(
            Path(config["checkpoint_dir"]) / f"r4_{self.state.run_id}"
        )
        self.checkpoint_handler = RuntimeStepCheckpoint(
            checkpoint,
            self.intelligence_store,
            artifacts_provider=self.executor.artifacts_for_current_workspace,
            domain_state_provider=lambda: self.domain_runtime_state,
        )

    def request_abort(self) -> None:
        self._abort_requested = True

    def run(self) -> RunState:
        self.state.status = RunStatus.RUNNING
        approved = self._approval_resolver(
            ApprovalRequest(
                request_id="approval-visible",
                tool_name="http_request",
                arguments={
                    "method": "POST",
                    "url": "http://127.0.0.1:5000/login?token=private-value",
                    "headers": {"cookie": "private-cookie"},
                },
                reason="private planner reasoning",
                risk_level="MEDIUM",
            )
        )
        candidate = None
        if self._abort_requested:
            status = RunStatus.ABORTED
            reason = TerminationReason.EXPLICIT_ABORT
        elif approved:
            candidate = FlagCandidate(
                value="FLAG{local-answer}",
                source="analysis/response.txt",
                confidence=0.94,
                evidence="The response matched the evidence in analysis/response.txt.",
            )
            confirmed = (
                self._flag_confirmer(candidate)
                if self._confirm_candidate and self._flag_confirmer is not None
                else True
            )
            status = RunStatus.SOLVED if confirmed else RunStatus.BLOCKED
            reason = (
                TerminationReason.FLAG_CONFIRMED
                if confirmed
                else TerminationReason.NO_ACTIONS
            )
        else:
            status = RunStatus.BLOCKED
            reason = TerminationReason.NO_ACTIONS
        self.state.set_termination(
            TerminationDecision(
                status,
                reason,
                "fake local result",
                candidate if approved and status is RunStatus.SOLVED else None,
            )
        )
        self.checkpoint_handler.finalize(self.state)
        return self.state


def _sample_intelligence(challenge_id: str) -> IntelligenceStore:
    store = IntelligenceStore.create(challenge_id)
    store.add_fact(
        Fact(
            category="framework",
            content=(
                "Flask at /Users/example/private/app.py; read /etc/passwd, "
                "/var/log/private.log, /Volumes/Secret/data.txt, "
                r"/data/challenge/private.txt, and \\server\share\private.txt"
            ),
        )
    )
    for content in (
        "Authorization is opaquecredential123456",
        "password is hunter2",
        "X-Session: abcdefghijklmnop",
        "Headers: {X-Custom: abcdefghijklmnop}",
        "Use HTTPRequestTool with arguments payload",
        "Planner reasoning: private chain",
    ):
        store.add_fact(Fact(category="observation", content=content))
    hypothesis = store.add_hypothesis(
        Hypothesis(
            statement="The response may contain flag{private-value} or HTB{candidate-value}",
            domain="web",
            status=HypothesisStatus.OPEN,
        )
    )
    store.add_finding(
        Finding(
            title="Login behavior",
            description=(
                "token=private-value and Authorization: opaquecredential123456 "
                "were observed"
            ),
        )
    )
    experiment = store.add_experiment(
        Experiment(
            hypothesis_id=hypothesis.id,
            goal="Compare the login response",
            action={
                "tool_name": "http_request",
                "arguments": {"token": "private-value"},
            },
            expected_result="GET /login returns a stable response difference",
            actual_result=(
                "cookie=private-cookie and X-API-Key: abcdefghijklmnop changed the response"
            ),
            status=ExperimentStatus.SUCCESS,
        )
    )
    store.add_evidence(
        EvidenceRecord(
            source="http_request",
            observation="flag{private-value} appeared at /tmp/private-response.txt",
            experiment_id=experiment.experiment_id,
            hypothesis_id=hypothesis.id,
        )
    )
    return store


def _settings(tmp_path: Path) -> UISettings:
    return UISettings(
        workspace_root=tmp_path / "workspace",
        experience_root=tmp_path / "experiences" / "challenges",
        global_experience_path=tmp_path / "experiences" / "experience.json",
        checkpoint_root=tmp_path / "checkpoints",
        staging_root=tmp_path / "staging",
    )


def _workbench(tmp_path: Path, *, confirm_candidate: bool = False):
    settings = _settings(tmp_path).normalized()
    manifest = ChallengeManifest.create(
        name="本地监督测试",
        domain="web",
        description="仅用于已授权的本地测试。",
        target_url="http://127.0.0.1:5000",
        entropy="r14-test",
    )
    ChallengeExperienceManager(settings.experience_root).create(manifest)
    resume_seen: list[bool] = []

    def runtime_factory(**kwargs):
        resume_seen.append(kwargs["resume_checkpoint"] is not None)
        return _FakeRuntime(**kwargs, confirm_candidate=confirm_candidate)

    coordinator = SupervisedRunCoordinator(
        workspace_root=settings.workspace_root,
        challenge_root=settings.experience_root,
        checkpoint_root=settings.checkpoint_root,
        global_experience_path=settings.global_experience_path,
        config_provider=lambda: {},
        runtime_factory=runtime_factory,
    )
    client = TestClient(create_app(settings, run_coordinator=coordinator))
    return client, manifest, settings, resume_seen


def _wait_for_run(client: TestClient, challenge_id: str, predicate):
    result = None
    for _ in range(200):
        result = client.get(f"/api/challenges/{challenge_id}/run")
        assert result.status_code == 200
        if predicate(result.json()):
            return result.json()
        time.sleep(0.01)
    raise AssertionError(f"run state did not converge: {result.text if result else 'none'}")


def test_r14_supervised_approval_and_safe_projections(tmp_path):
    client, manifest, settings, resume_seen = _workbench(tmp_path)
    manager = ChallengeExperienceManager(settings.experience_root)
    manager.paths_for(manifest).artifacts_dir.joinpath("imported.json").write_text(
        json.dumps(
            [
                {"path": "attachments/notes.txt", "artifact_type": "challenge_attachment"},
                {
                    "path": "attachments/HTB{candidate-value}.txt",
                    "artifact_type": "challenge_attachment",
                },
            ]
        ),
        encoding="utf-8",
    )
    detail = client.get(f"/api/challenges/{manifest.challenge_id}")
    assert detail.status_code == 200
    assert detail.json()["materials"] == [
        {"name": "attachments/notes.txt", "kind": "attachment"},
        {"name": "attachments/HTB{candidate-value}.txt", "kind": "attachment"},
    ]

    started = client.post(
        f"/api/challenges/{manifest.challenge_id}/runs",
        headers=LOCAL_ORIGIN,
    )
    assert started.status_code == 202
    finished = _wait_for_run(
        client,
        manifest.challenge_id,
        lambda item: not item["active"],
    )
    assert finished["status"] == "SOLVED"
    assert finished["pending_decision"] is None
    assert finished["completion_available"] is True
    assert resume_seen == [False]

    manager.paths_for(manifest).runs_dir.joinpath(
        "run-001", "artifacts", "manifest.json"
    ).write_text(
        json.dumps(
            [
                {"path": "analysis/summary.txt", "artifact_type": "analysis"},
                {
                    "path": "analysis/HTB{candidate-value}.txt",
                    "artifact_type": "analysis",
                },
            ]
        ),
        encoding="utf-8",
    )

    outcomes = client.get(f"/api/challenges/{manifest.challenge_id}/outcomes")
    documents = client.get(f"/api/challenges/{manifest.challenge_id}/documents")
    assert outcomes.status_code == 200
    assert documents.status_code == 200
    public_text = outcomes.text + documents.text
    assert "private-value" in public_text
    assert "private-cookie" in public_text
    assert "/Users/example" in public_text
    assert "/tmp/private-response" in public_text
    assert "/etc/passwd" in public_text
    assert "/var/log/private.log" in public_text
    assert "/Volumes/Secret/data.txt" in public_text
    assert "/data/challenge/private.txt" in public_text
    assert r"\\server\share\private.txt" not in public_text
    assert "opaquecredential123456" in public_text
    assert "abcdefghijklmnop" in public_text
    assert "analysis/summary.txt" in public_text
    assert "hunter2" in public_text
    assert "X-Session" in public_text
    assert "X-Custom" in public_text
    assert "HTTPRequestTool" in public_text
    assert "Planner reasoning" in public_text
    assert "HTB{candidate-value}" in public_text
    assert "/reset/token/private" in public_text
    assert "/Users/maxchen/private.txt" in public_text
    assert "/tmp/private-response.txt" in public_text
    assert "/var/log/app.log" in public_text
    assert "/users/42" in public_text
    assert "/home/feed" in public_text
    assert "GET /login" in public_text
    assert "http_request" in public_text
    run_id = IntelligenceCheckpoint(
        ChallengeExperienceManager(settings.experience_root)
        .paths_for(manifest)
        .runs_dir
        / "run-001"
        / "checkpoint"
    ).load().run_state.run_id
    assert run_id in public_text
    public_endpoints = {
        item["path"]: item for item in outcomes.json()["web"]["endpoints"]
    }
    assert outcomes.json()["flag"]["status"] == "found"
    assert outcomes.json()["flag"]["value"] == "FLAG{local-answer}"
    assert "analysis/response.txt" in outcomes.json()["flag"]["evidence"]
    assert public_endpoints["/login"]["parameters"] == ["password", "username"]
    assert outcomes.json()["artifacts"] == [
        {
            "name": "summary.txt",
            "kind_label": "分析材料",
            "created_at": None,
            "path": "analysis/summary.txt",
        },
        {
            "name": "HTB{candidate-value}.txt",
            "kind_label": "分析材料",
            "created_at": None,
            "path": "analysis/HTB{candidate-value}.txt",
        },
    ]
    assert documents.json()["available"] is True
    assert str(tmp_path) not in public_text
    assert SupervisedRunCoordinator._safe_request_path("/reset/token/private") == "/reset/token/private"

    candidate_store = ExperienceCandidateStore(
        ChallengeExperienceManager(settings.experience_root)
        .paths_for(manifest)
        .experience_candidates_file,
        challenge_id=manifest.challenge_id,
    )
    candidate_store.replace_all(
        [
            ExperienceCandidate(
                id="candidate-approval-test",
                category="parameter_behavior",
                pattern="Response structure changed with a bounded input.",
                strategy="Compare one controlled input against a stable baseline.",
                lesson="Keep observations separate from explanations.",
                source_challenge=manifest.challenge_id,
                confidence=0.78,
            ),
            ExperienceCandidate(
                id="candidate-rejection-test",
                category="business_logic",
                pattern="A state transition was observed.",
                strategy="Compare permitted state before and after one action.",
                lesson="Do not infer an application rule from one response.",
                source_challenge=manifest.challenge_id,
                confidence=0.65,
            ),
        ]
    )
    listed = client.get(
        f"/api/challenges/{manifest.challenge_id}/experience-candidates"
    )
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 2

    approved_candidate = client.post(
        f"/api/challenges/{manifest.challenge_id}/experience-candidates/candidate-approval-test",
        json={"decision": "approve"},
        headers=LOCAL_ORIGIN,
    )
    rejected_candidate = client.post(
        f"/api/challenges/{manifest.challenge_id}/experience-candidates/candidate-rejection-test",
        json={"decision": "reject"},
        headers=LOCAL_ORIGIN,
    )
    assert approved_candidate.json()["status"] == "APPROVED"
    assert rejected_candidate.json()["status"] == "REJECTED"
    global_text = settings.global_experience_path.read_text(encoding="utf-8")
    assert "Response structure changed" in global_text
    assert "A state transition was observed" not in global_text


def test_r14_candidate_confirmation_shows_answer_evidence_and_report(tmp_path):
    client, manifest, _settings, _resume_seen = _workbench(
        tmp_path,
        confirm_candidate=True,
    )
    route = f"/api/challenges/{manifest.challenge_id}"
    assert client.post(f"{route}/runs", headers=LOCAL_ORIGIN).status_code == 202
    finished = _wait_for_run(
        client,
        manifest.challenge_id,
        lambda item: not item["active"],
    )
    assert finished["status"] == "SOLVED"
    assert finished["pending_decision"] is None
    documents = client.get(f"{route}/documents").json()
    assert "FLAG{local-answer}" in documents["report"]
    assert "analysis/response.txt" in documents["report"]


def test_r14_auto_authorized_run_has_no_pending_decision(tmp_path):
    client, manifest, _settings_value, resume_seen = _workbench(tmp_path)
    route = f"/api/challenges/{manifest.challenge_id}"

    assert client.post(f"{route}/runs", headers=LOCAL_ORIGIN).status_code == 202
    completed = _wait_for_run(
        client,
        manifest.challenge_id,
        lambda item: not item["active"],
    )
    assert completed["status"] == "SOLVED"
    assert completed["pending_decision"] is None
    assert completed["milestones"][0]["detail"].startswith("已启用本题授权范围")
    assert resume_seen == [False]

    stale = client.post(
        f"{route}/run/decisions/not-the-current-decision",
        json={"decision": "approve"},
        headers=LOCAL_ORIGIN,
    )
    assert stale.status_code == 409


def test_r14_abort_before_approval_publication_does_not_lose_wakeup(tmp_path):
    settings = _settings(tmp_path).normalized()
    manifest = ChallengeManifest.create(
        name="delayed approval",
        domain="web",
        description="Authorized fake-local concurrency fixture.",
        entropy="delayed-approval",
    )
    ChallengeExperienceManager(settings.experience_root).create(manifest)
    gate = threading.Event()

    class DelayedApprovalRuntime(_FakeRuntime):
        def run(self):
            gate.wait(timeout=2)
            return super().run()

    coordinator = SupervisedRunCoordinator(
        workspace_root=settings.workspace_root,
        challenge_root=settings.experience_root,
        checkpoint_root=settings.checkpoint_root,
        global_experience_path=settings.global_experience_path,
        config_provider=lambda: {},
        runtime_factory=lambda **kwargs: DelayedApprovalRuntime(**kwargs),
    )

    started = coordinator.start(manifest.challenge_id)
    assert started.active is True
    coordinator.abort(manifest.challenge_id)
    gate.set()
    for _ in range(200):
        view = coordinator.view(manifest.challenge_id)
        if not view.active:
            break
        time.sleep(0.01)
    else:
        raise AssertionError("aborted run remained blocked before approval publication")
    assert view.status == "ABORTED"
    assert view.pending_decision is None


def test_r14_concurrent_start_is_reserved_before_runtime_construction(tmp_path):
    settings = _settings(tmp_path).normalized()
    manifest = ChallengeManifest.create(
        name="concurrent start",
        domain="web",
        description="Authorized fake-local concurrency fixture.",
        entropy="concurrent-start",
    )
    ChallengeExperienceManager(settings.experience_root).create(manifest)
    factory_entered = threading.Event()
    factory_gate = threading.Event()

    def delayed_factory(**kwargs):
        factory_entered.set()
        factory_gate.wait(timeout=2)
        return _FakeRuntime(**kwargs)

    coordinator = SupervisedRunCoordinator(
        workspace_root=settings.workspace_root,
        challenge_root=settings.experience_root,
        checkpoint_root=settings.checkpoint_root,
        global_experience_path=settings.global_experience_path,
        config_provider=lambda: {},
        runtime_factory=delayed_factory,
    )
    first_result = []
    first = threading.Thread(
        target=lambda: first_result.append(coordinator.start(manifest.challenge_id)),
        daemon=True,
    )
    first.start()
    assert factory_entered.wait(timeout=2)

    with pytest.raises(ValueError, match="正在分析中"):
        coordinator.start(manifest.challenge_id)

    factory_gate.set()
    first.join(timeout=2)
    assert first_result and first_result[0].active is True
    coordinator.abort(manifest.challenge_id)
    for _ in range(200):
        if not coordinator.view(manifest.challenge_id).active:
            break
        time.sleep(0.01)
    else:
        raise AssertionError("reserved concurrent run did not stop")

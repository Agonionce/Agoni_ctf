import pytest

from agent.domains.context import SkillContextBuilder
from agent.domains.integration import DomainRuntimeAnalyzer
from agent.domains.loader import SkillLoader
from agent.domains.manager import DomainRuntimeManager, build_default_runtime_manager
from agent.domains.router import SkillRouter
from agent.domains.runtime_context import DomainRuntimeContextBuilder
from agent.domains.web.runtime import WebRuntime
from agent.intelligence.checkpoint import IntelligenceCheckpoint
from agent.intelligence.store import IntelligenceStore
from agent.runtime.contracts import (
    AnalysisOutcome,
    AnalysisResult,
    ChallengeSpec,
    RunState,
)
from agent.runtime import integration
from agent.runtime.planner import JsonPlanner
from ctf_platform.base import Question


def _web_challenge() -> ChallengeSpec:
    return ChallengeSpec(
        "r4-web",
        "PHP Login",
        "Local authorized PHP login with a cookie and SQL parameter.",
        category="web",
        authorization_scope="authorized_local_test",
    )


def test_default_runtime_registration_contains_web_and_pwn():
    manager = build_default_runtime_manager()

    assert manager.names() == ["web", "pwn", "reverse", "crypto", "misc"]
    assert manager.select("web").__class__.__name__ == "WebRuntime"
    assert manager.select("pwn").__class__.__name__ == "PwnRuntime"


def test_runtime_manager_rejects_duplicate_registration():
    manager = DomainRuntimeManager([WebRuntime()])

    with pytest.raises(ValueError, match="duplicate domain runtime"):
        manager.register(WebRuntime())


def test_web_phase_transition_is_declarative_and_validated():
    manager = build_default_runtime_manager()
    state = manager.initialize("web", _web_challenge())

    assert state.phase == "RECON"
    assert manager.next_phase().phase == "ANALYSIS"
    assert state.phase_history == ["RECON", "ANALYSIS"]

    with pytest.raises(ValueError, match="invalid web phase transition"):
        manager.next_phase("VERIFY")


def test_observation_routing_records_summary_without_executing_a_tool():
    manager = build_default_runtime_manager()
    state = manager.initialize("web", _web_challenge())

    manager.route_observation(
        {"summary": "Local route metadata has been inventoried."},
        phase_complete=True,
    )

    assert state.observation_count == 1
    assert state.last_observation == "Local route metadata has been inventoried."
    assert state.phase == "ANALYSIS"


def test_analyzer_adapter_routes_summary_without_advancing_phase():
    class FakeAnalyzer:
        def analyze(self, _observation, _state):
            return AnalysisResult(
                summary="Fake local analysis completed.",
                outcome=AnalysisOutcome.PROGRESS,
            )

    challenge = _web_challenge()
    manager = build_default_runtime_manager()
    domain_state = manager.initialize("web", challenge)
    adapter = DomainRuntimeAnalyzer(FakeAnalyzer(), manager)

    result = adapter.analyze(None, RunState(challenge))

    assert result.summary == "Fake local analysis completed."
    assert domain_state.observation_count == 1
    assert domain_state.last_observation == "Fake local analysis completed."
    assert domain_state.phase == "RECON"


def test_domain_runtime_context_combines_state_skill_and_intelligence():
    challenge = _web_challenge()
    loader = SkillLoader()
    selection = SkillRouter(loader=loader).route(challenge)
    skill_context = SkillContextBuilder().build(
        challenge,
        selection,
        loader.all(),
        {"facts": [{"content": "login route exists"}]},
    )
    manager = build_default_runtime_manager()
    state = manager.initialize("web", challenge)

    context = DomainRuntimeContextBuilder().build(
        challenge,
        manager.select("web"),
        state,
        skill_context,
        {
            "facts": [{"content": f"fact-{index}"} for index in range(5)],
            "credentials": [{"value": "not-for-runtime-context"}],
        },
    )

    assert context["domain_runtime"]["state"]["phase"] == "RECON"
    assert context["domain_runtime"]["phase"]["goal"]
    assert context["skill_context"]["routing"]["domains"] == ["web"]
    assert len(context["relevant_intelligence"]["facts"]) == 3
    assert "credentials" not in context["relevant_intelligence"]


def test_planner_receives_optional_domain_runtime_context():
    captured = {}

    def requester(_system_prompt, user_prompt):
        captured["user"] = user_prompt
        return {
            "objective": "organize local recon evidence",
            "reasoning_summary": "the current lifecycle phase is RECON",
            "actions": [{"tool_name": "fake_tool", "arguments": {}}],
        }

    challenge = _web_challenge()
    planner = JsonPlanner(
        requester,
        domain_runtime_context_provider=lambda _challenge, _state: {
            "domain_runtime": {"domain": "web", "phase": {"name": "RECON"}}
        },
    )

    proposal = planner.plan(challenge, RunState(challenge), [])

    assert proposal.actions[0].tool_name == "fake_tool"
    assert '"domain": "web"' in captured["user"]
    assert '"name": "RECON"' in captured["user"]
    assert "{domain_runtime_context}" not in captured["user"]


def test_checkpoint_restores_domain_runtime_state(tmp_path):
    challenge = _web_challenge()
    manager = build_default_runtime_manager()
    domain_state = manager.initialize("web", challenge)
    manager.next_phase()
    checkpoint = IntelligenceCheckpoint(tmp_path / "r4_demo")

    checkpoint.save(
        RunState(challenge),
        IntelligenceStore.create(challenge.challenge_id),
        [],
        domain_state,
    )
    restored = checkpoint.load()

    assert restored.domain_runtime_state is not None
    assert restored.domain_runtime_state.domain == "web"
    assert restored.domain_runtime_state.phase == "ANALYSIS"
    assert restored.domain_runtime_state.phase_history == ["RECON", "ANALYSIS"]
    assert (tmp_path / "r4_demo" / "domain_runtime.json").is_file()


def test_build_runtime_selects_r3_domain_and_exposes_r4_context(monkeypatch, tmp_path):
    class FakeRequester:
        def __call__(self, _system_prompt, _user_prompt):
            raise AssertionError("build-only test must not call an API")

    monkeypatch.setattr(integration, "OpenAIJsonRequester", FakeRequester)
    question = Question(
        title="PHP Login",
        content="Authorized local cookie and SQL challenge",
        metadata={"challenge_id": "r4-build", "category": "web"},
    )

    runtime = integration.build_runtime(
        question,
        {
            "runtime": {"default_domain": "auto", "max_steps": 2},
            "execution": {
                "mode": "manual",
                "workspace_root": str(tmp_path / "workspace"),
                "default_policy": "safe",
            },
            "skills": {"paths": []},
            "domain": {"default": "auto"},
        },
    )
    context = runtime.planner.domain_runtime_context_provider(
        runtime.challenge,
        runtime.state,
    )

    assert runtime.domain_selection.primary_domain == "web"
    assert runtime.domain_runtime_state.phase == "RECON"
    assert context["domain_runtime"]["domain"] == "web"
    assert context["domain_runtime"]["phase"]["name"] == "RECON"
    assert runtime.budget.max_steps == 2

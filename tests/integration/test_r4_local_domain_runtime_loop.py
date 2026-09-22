"""Local-only R4 lifecycle demo with no Tool, Shell, network, or real target."""

from __future__ import annotations

from agent.domains.context import SkillContextBuilder
from agent.domains.loader import SkillLoader
from agent.domains.manager import build_default_runtime_manager
from agent.domains.router import SkillRouter
from agent.domains.runtime_context import DomainRuntimeContextBuilder
from agent.runtime.contracts import ChallengeSpec, RunState
from agent.runtime.planner import JsonPlanner


DEMO_TOKEN = "LOCAL_DOMAIN_RUNTIME_LOOP_OK"


def run_demo() -> str:
    challenge = ChallengeSpec(
        "r4-local-web-demo",
        "Fake PHP Login",
        "An authorized local PHP login uses a cookie and SQL parameter.",
        category="web",
        authorization_scope="authorized_local_demo",
    )
    loader = SkillLoader()
    selection = SkillRouter(loader=loader).route(challenge)
    skill_context = SkillContextBuilder().build(
        challenge,
        selection,
        loader.all(),
        {"facts": [{"content": "A local login surface was declared."}]},
    )
    manager = build_default_runtime_manager()
    state = manager.initialize(selection.primary_domain, challenge)
    assert state.phase == "RECON"
    manager.route_observation(
        {"summary": "Fake recon metadata is complete."},
        phase_complete=True,
    )
    assert state.phase == "ANALYSIS"
    runtime, _ = manager.current()
    runtime_context = DomainRuntimeContextBuilder().build(
        challenge,
        runtime,
        state,
        skill_context,
        {"facts": [{"content": "Fake recon metadata is complete."}]},
    )

    def fake_planner(_system_prompt: str, user_prompt: str):
        assert '"domain": "web"' in user_prompt
        assert '"phase": "ANALYSIS"' in user_prompt
        return {
            "objective": DEMO_TOKEN,
            "reasoning_summary": "The local Web lifecycle moved from RECON to ANALYSIS.",
            "actions": [{"tool_name": "fake_observation", "arguments": {}}],
        }

    proposal = JsonPlanner(
        fake_planner,
        domain_runtime_context_provider=lambda _challenge, _state: runtime_context,
    ).plan(challenge, RunState(challenge), [])
    assert proposal.objective == DEMO_TOKEN
    return proposal.objective


def test_local_domain_runtime_loop():
    assert run_demo() == DEMO_TOKEN


if __name__ == "__main__":
    print(run_demo())

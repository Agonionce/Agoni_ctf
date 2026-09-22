"""Local-only R3 demo: classification and context injection, with no Tool execution."""

from __future__ import annotations

from agent.domains.context import SkillContextBuilder
from agent.domains.loader import SkillLoader
from agent.domains.router import SkillRouter
from agent.runtime.contracts import ChallengeSpec, RunState
from agent.runtime.planner import JsonPlanner


DEMO_TOKEN = "LOCAL_DOMAIN_SKILL_LOOP_OK"


def run_demo() -> str:
    challenge = ChallengeSpec(
        challenge_id="r3-local-domain-demo",
        title="Local PHP login challenge",
        description="A cookie-backed login builds a SQL query from a user value.",
        category="web",
        authorization_scope="authorized_local_demo",
    )
    loader = SkillLoader()
    selection = SkillRouter(loader=loader).route(challenge)
    context = SkillContextBuilder().build(
        challenge,
        selection,
        loader.all(),
        {
            "facts": [{"category": "web", "content": "The login uses a cookie."}],
            "hypotheses": [
                {"statement": "The user value may cross a SQL trust boundary."}
            ],
        },
    )

    def fake_planner(_system_prompt: str, user_prompt: str):
        assert '"web"' in user_prompt
        assert '"sql_injection"' in user_prompt
        return {
            "objective": DEMO_TOKEN,
            "reasoning_summary": "R3 selected and injected bounded local skill context.",
            "actions": [{"tool_name": "fake_observation", "arguments": {}}],
        }

    proposal = JsonPlanner(
        fake_planner,
        domain_context_provider=lambda _challenge, _state: context,
    ).plan(challenge, RunState(challenge), [])
    assert selection.selected_domains == ("web",)
    assert "sql_injection" in selection.selected_skills
    assert proposal.objective == DEMO_TOKEN
    return proposal.objective


def test_local_domain_skill_loop():
    assert run_demo() == DEMO_TOKEN


if __name__ == "__main__":
    print(run_demo())

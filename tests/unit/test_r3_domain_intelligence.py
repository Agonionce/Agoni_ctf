import json

import pytest

from agent.domains.context import SkillContextBuilder
from agent.domains.loader import SkillLoader, SkillValidationError
from agent.domains.registry import build_default_domain_registry
from agent.domains.router import SkillRouter
from agent.runtime.contracts import ChallengeSpec, RunState
from agent.runtime.planner import JsonPlanner


def test_default_domain_catalog_is_bounded_and_ordered():
    registry = build_default_domain_registry()

    assert registry.names() == ["web", "pwn", "reverse", "crypto", "misc"]
    assert registry.get("web").get_skill(SkillLoader(), "sql_injection").domain == "web"


def test_web_detection_routes_php_cookie_sql_to_relevant_skills():
    challenge = ChallengeSpec(
        "r3-web",
        "PHP login",
        "A cookie-backed login sends a user value into a SQL query.",
    )

    selection = SkillRouter().route(challenge)

    assert selection.primary_domain == "web"
    assert selection.selected_skills == (
        "web_general",
        "authentication",
        "sql_injection",
    )
    assert selection.confidence >= 0.5


def test_pwn_detection_uses_challenge_and_artifact_metadata():
    challenge = ChallengeSpec(
        "r3-pwn",
        "Local service",
        "Connect to the authorized challenge endpoint with nc.",
    )

    selection = SkillRouter().route(
        challenge,
        [{"path": "input/chall", "format": "ELF", "architecture": "amd64"}],
    )

    assert selection.primary_domain == "pwn"
    assert "binary_triage" in selection.selected_skills


def test_skill_loader_validates_sql_injection_metadata():
    skill = SkillLoader().get("sql_injection")

    assert skill.domain == "web"
    assert skill.priority.value == "HIGH"
    assert skill.knowledge
    assert skill.strategies
    assert skill.heuristics


def test_skill_loader_rejects_missing_required_sections(tmp_path):
    path = tmp_path / "broken.md"
    path.write_text(
        "---\nname: broken\ndomain: misc\ndescription: broken test\n"
        "tags: [broken]\npriority: LOW\n---\n## Knowledge\n- only one section\n",
        encoding="utf-8",
    )

    with pytest.raises(SkillValidationError, match="missing non-empty sections"):
        SkillLoader(roots=[tmp_path]).load()


def test_context_builder_injects_selected_skills_and_bounded_intelligence():
    challenge = ChallengeSpec(
        "r3-context",
        "PHP login",
        "Cookie and SQL challenge",
        category="web",
    )
    loader = SkillLoader()
    selection = SkillRouter(loader=loader).route(challenge)
    intelligence = {
        "facts": [{"content": f"fact-{index}"} for index in range(5)],
        "hypotheses": [{"statement": "SQL data flow is injectable"}],
        "credentials": [{"value": "must-not-be-injected"}],
        "unrelated": ["not selected"],
    }

    context = SkillContextBuilder(max_items_per_collection=2).build(
        challenge,
        selection,
        loader.all(),
        intelligence,
    )

    names = [skill["name"] for skill in context["skills"]]
    assert names == ["web_general", "authentication", "sql_injection"]
    assert "xss" not in names
    assert len(context["relevant_intelligence"]["facts"]) == 2
    assert "credentials" not in context["relevant_intelligence"]
    assert "unrelated" not in context["relevant_intelligence"]


def test_json_planner_receives_domain_context_without_protocol_change():
    captured = {}

    def requester(system_prompt, user_prompt):
        captured["user"] = user_prompt
        return {
            "objective": "inspect local challenge evidence",
            "reasoning_summary": "selected web guidance is relevant",
            "actions": [{"tool_name": "fake_tool", "arguments": {}}],
        }

    challenge = ChallengeSpec("r3-planner", "Login", "PHP SQL login", "web")
    planner = JsonPlanner(
        requester,
        domain_context_provider=lambda _challenge, _state: {
            "routing": {"domains": ["web"], "skills": ["sql_injection"]}
        },
    )

    proposal = planner.plan(challenge, RunState(challenge), [])

    assert proposal.actions[0].tool_name == "fake_tool"
    assert '"domains": [' in captured["user"]
    assert '"sql_injection"' in captured["user"]
    assert "{domain_context}" not in captured["user"]

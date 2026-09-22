import json

import pytest

from agent.runtime.contracts import ChallengeSpec, RunState
from agent.runtime.analyzer import JsonAnalyzer
from agent.runtime.errors import PlannerOutputError
from agent.runtime.planner import JsonPlanner, parse_json_object


def test_json_planner_returns_action_proposal_without_xml():
    captured = {}

    def requester(system_prompt, user_prompt):
        captured["system"] = system_prompt
        captured["user"] = user_prompt
        return json.dumps(
            {
                "objective": "read local evidence",
                "reasoning_summary": "one deterministic action",
                "actions": [
                    {
                        "call_id": "call-1",
                        "tool_name": "fake_tool",
                        "arguments": {"content": "flag"},
                    }
                ],
            }
        )

    challenge = ChallengeSpec("c1", "Local", "authorized local challenge")
    planner = JsonPlanner(requester)
    proposal = planner.plan(challenge, RunState(challenge), [])

    assert proposal.actions[0].tool_name == "fake_tool"
    assert "<tool_calls>" not in captured["user"]
    assert "{challenge}" not in captured["user"]
    assert "solution_plan" not in captured["user"]


def test_invalid_json_is_a_bounded_domain_error():
    with pytest.raises(PlannerOutputError):
        parse_json_object("not-json-and-not-repairable")


def test_analyzer_uses_observation_contract_and_no_legacy_solution_plan():
    captured = {}

    def requester(system_prompt, user_prompt):
        captured["system"] = system_prompt
        captured["user"] = user_prompt
        return {
            "summary": "tool evidence was interpreted",
            "outcome": "PROGRESS",
            "recommendations": "continue",
            "flag_candidates": [],
            "confidence": 0.8,
        }

    challenge = ChallengeSpec("c1", "Local", "authorized local challenge")
    state = RunState(challenge)
    from agent.runtime.contracts import ActionProposal, Observation, ToolCall, ToolResult

    proposal = ActionProposal("inspect", "read evidence", [ToolCall("c", "fake", {})])
    observation = Observation(
        1,
        proposal.objective,
        proposal,
        [ToolResult("c", "fake", True, stdout="evidence")],
    )
    result = JsonAnalyzer(requester).analyze(observation, state)

    assert result.outcome.value == "PROGRESS"
    assert '"step_id": 1' in captured["user"]
    assert "solution_plan" not in captured["user"]

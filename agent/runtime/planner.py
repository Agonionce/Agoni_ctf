"""Planner contracts and the R0 JSON Planner implementation."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Mapping, Protocol

from json_repair import repair_json

from agent.runtime.contracts import (
    ActionProposal,
    ChallengeSpec,
    DecisionType,
    RunState,
    ToolCall,
)
from agent.runtime.errors import PlannerOutputError
from agent.runtime.prompts import render_planner_prompt


class Planner(Protocol):
    """Interface consumed by AgentRuntime."""

    def plan(
        self,
        challenge: ChallengeSpec,
        state: RunState,
        tool_schemas: List[Dict[str, Any]],
    ) -> ActionProposal:
        """Return one validated action proposal."""


class JsonRequester(Protocol):
    """Minimal injectable JSON request interface."""

    def __call__(self, system_prompt: str, user_prompt: str) -> Any:
        """Return a JSON object or model response content."""


def response_content(payload: Any) -> Any:
    """Extract text content from either a dict/string or OpenAI-like response."""

    if isinstance(payload, (dict, list, str)):
        return payload
    try:
        return payload.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as error:
        raise PlannerOutputError("LLM response has no message content") from error


def parse_json_object(payload: Any) -> Dict[str, Any]:
    """Parse one JSON object with one local repair attempt and no LLM recursion."""

    content = response_content(payload)
    if isinstance(content, dict):
        data = content
    else:
        if not isinstance(content, str):
            raise PlannerOutputError("planner response must be a JSON object")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as error:
            try:
                repaired = repair_json(content)
                data = json.loads(repaired)
            except Exception as repair_error:
                raise PlannerOutputError("planner response is not valid JSON") from repair_error
    if not isinstance(data, dict):
        raise PlannerOutputError("planner response must be a JSON object")
    return data


class JsonPlanner:
    """Generate ActionProposal values from a strict JSON response."""

    def __init__(
        self,
        request_json: JsonRequester,
        tool_schemas: List[Dict[str, Any]] | None = None,
        intelligence_context_provider: Callable[[ChallengeSpec, RunState], Dict[str, Any]] | None = None,
        domain_context_provider: Callable[[ChallengeSpec, RunState], Dict[str, Any]] | None = None,
        domain_runtime_context_provider: Callable[[ChallengeSpec, RunState], Dict[str, Any]] | None = None,
        experiment_context_provider: Callable[[ChallengeSpec, RunState], Dict[str, Any]] | None = None,
        experience_context_provider: Callable[[ChallengeSpec, RunState], Dict[str, Any]] | None = None,
        web_attack_surface_context_provider: Callable[[ChallengeSpec, RunState], Dict[str, Any]] | None = None,
        web_research_context_provider: Callable[[ChallengeSpec, RunState], Dict[str, Any]] | None = None,
    ) -> None:
        self.request_json = request_json
        self.default_tool_schemas = tool_schemas or []
        self.intelligence_context_provider = intelligence_context_provider
        self.domain_context_provider = domain_context_provider
        self.domain_runtime_context_provider = domain_runtime_context_provider
        self.experiment_context_provider = experiment_context_provider
        self.experience_context_provider = experience_context_provider
        self.web_attack_surface_context_provider = web_attack_surface_context_provider
        self.web_research_context_provider = web_research_context_provider

    def plan(
        self,
        challenge: ChallengeSpec,
        state: RunState,
        tool_schemas: List[Dict[str, Any]] | None = None,
    ) -> ActionProposal:
        schemas = self.default_tool_schemas if tool_schemas is None else tool_schemas
        intelligence_context = (
            self.intelligence_context_provider(challenge, state)
            if self.intelligence_context_provider is not None
            else None
        )
        domain_context = (
            self.domain_context_provider(challenge, state)
            if self.domain_context_provider is not None
            else None
        )
        domain_runtime_context = (
            self.domain_runtime_context_provider(challenge, state)
            if self.domain_runtime_context_provider is not None
            else None
        )
        experiment_context = (
            self.experiment_context_provider(challenge, state)
            if self.experiment_context_provider is not None
            else None
        )
        experience_context = (
            self.experience_context_provider(challenge, state)
            if self.experience_context_provider is not None
            else None
        )
        web_attack_surface_context = (
            self.web_attack_surface_context_provider(challenge, state)
            if self.web_attack_surface_context_provider is not None
            else None
        )
        web_research_context = (
            self.web_research_context_provider(challenge, state)
            if self.web_research_context_provider is not None
            else None
        )
        system_prompt, user_prompt = render_planner_prompt(
            challenge,
            state,
            schemas,
            intelligence_context=intelligence_context,
            domain_context=domain_context,
            domain_runtime_context=domain_runtime_context,
            experiment_context=experiment_context,
            experience_context=experience_context,
            web_attack_surface_context=web_attack_surface_context,
            web_research_context=web_research_context,
        )
        payload = parse_json_object(self.request_json(system_prompt, user_prompt))
        return self._proposal_from_payload(payload)

    @staticmethod
    def _proposal_from_payload(payload: Dict[str, Any]) -> ActionProposal:
        objective = payload.get("objective")
        reasoning_summary = payload.get("reasoning_summary")
        raw_actions = payload.get("actions")
        raw_decision_type = str(payload.get("decision_type", "normal_action")).lower()
        aliases = {
            "normal": DecisionType.NORMAL_ACTION,
            "normal_action": DecisionType.NORMAL_ACTION,
            "experiment": DecisionType.EXPERIMENT_ACTION,
            "experiment_action": DecisionType.EXPERIMENT_ACTION,
        }
        decision_type = aliases.get(raw_decision_type)
        if decision_type is None:
            raise PlannerOutputError("planner JSON has invalid decision_type")
        if decision_type is DecisionType.EXPERIMENT_ACTION and raw_actions is None:
            raw_action = payload.get("action")
            raw_actions = [raw_action] if isinstance(raw_action, dict) else None
        if not isinstance(objective, str) or not objective.strip():
            raise PlannerOutputError("planner JSON missing objective")
        if not isinstance(reasoning_summary, str) or not reasoning_summary.strip():
            raise PlannerOutputError("planner JSON missing reasoning_summary")
        if not isinstance(raw_actions, list) or not raw_actions:
            raise PlannerOutputError("planner JSON actions must be a non-empty list")

        actions: List[ToolCall] = []
        for index, raw_action in enumerate(raw_actions, start=1):
            if not isinstance(raw_action, dict):
                raise PlannerOutputError(f"action {index} must be an object")
            tool_name = raw_action.get("tool_name")
            arguments = raw_action.get("arguments", {})
            call_id = raw_action.get("call_id", f"call-{index}")
            if not isinstance(tool_name, str) or not tool_name.strip():
                raise PlannerOutputError(f"action {index} missing tool_name")
            if not isinstance(call_id, str) or not call_id.strip():
                raise PlannerOutputError(f"action {index} has invalid call_id")
            if not isinstance(arguments, dict):
                raise PlannerOutputError(f"action {index} arguments must be an object")
            actions.append(
                ToolCall(
                    call_id=call_id,
                    tool_name=tool_name,
                    arguments=arguments,
                    metadata=raw_action.get("metadata", {}),
                )
            )
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}
        metadata = dict(metadata)
        if decision_type is DecisionType.EXPERIMENT_ACTION:
            if len(actions) != 1:
                raise PlannerOutputError(
                    "experiment_action requires exactly one action"
                )
            hypothesis_id = payload.get("hypothesis_id")
            hypothesis_statement = payload.get("hypothesis_statement")
            if not any(
                isinstance(value, str) and value.strip()
                for value in (hypothesis_id, hypothesis_statement)
            ):
                raise PlannerOutputError(
                    "experiment_action requires hypothesis_id or hypothesis_statement"
                )
            goal = payload.get("experiment_goal")
            if not isinstance(goal, str) or not goal.strip():
                raise PlannerOutputError("experiment_action requires experiment_goal")
            expected_result = payload.get("expected_result", goal)
            if not isinstance(expected_result, str) or not expected_result.strip():
                raise PlannerOutputError("experiment_action requires expected_result")
            confidence = payload.get("hypothesis_confidence", 0.5)
            if (
                isinstance(confidence, bool)
                or not isinstance(confidence, (int, float))
                or not 0 <= float(confidence) <= 1
            ):
                raise PlannerOutputError(
                    "hypothesis_confidence must be a number in [0, 1]"
                )
            metadata["experiment"] = {
                "hypothesis_id": hypothesis_id or "",
                "hypothesis_statement": hypothesis_statement or "",
                "hypothesis_domain": str(payload.get("hypothesis_domain") or "misc"),
                "hypothesis_confidence": float(confidence),
                "goal": goal,
                "expected_result": expected_result,
                "experiment_type": str(payload.get("experiment_type") or ""),
                "evidence_type": str(payload.get("evidence_type") or ""),
                "context": (
                    dict(payload.get("experiment_context", {}))
                    if isinstance(payload.get("experiment_context"), Mapping)
                    else {}
                ),
                "experience_influence": [
                    str(item) for item in payload.get("experience_influence", [])
                ] if isinstance(payload.get("experience_influence"), list) else [],
            }
        return ActionProposal(
            objective=objective,
            reasoning_summary=reasoning_summary,
            actions=actions,
            metadata=metadata,
            decision_type=decision_type,
        )

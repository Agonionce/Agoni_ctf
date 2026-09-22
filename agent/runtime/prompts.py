"""R0 prompt rendering with explicit fields and no undefined variables."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from agent.runtime.contracts import ChallengeSpec, Observation, RunState, to_jsonable


_PROMPT_DIR = Path(__file__).resolve().parents[2] / "prompts"


def _read_prompt(name: str) -> str:
    return (_PROMPT_DIR / name).read_text(encoding="utf-8")


def _state_view(state: RunState) -> Dict[str, Any]:
    return {
        "run_id": state.run_id,
        "status": state.status.value,
        "current_step": state.current_step,
        "counters": to_jsonable(state.counters),
        "last_analysis": to_jsonable(state.last_analysis),
    }


def render_planner_prompt(
    challenge: ChallengeSpec,
    state: RunState,
    tool_schemas: List[Dict[str, Any]],
    intelligence_context: Dict[str, Any] | None = None,
    domain_context: Dict[str, Any] | None = None,
    domain_runtime_context: Dict[str, Any] | None = None,
    experiment_context: Dict[str, Any] | None = None,
    experience_context: Dict[str, Any] | None = None,
    web_attack_surface_context: Dict[str, Any] | None = None,
    web_research_context: Dict[str, Any] | None = None,
) -> Tuple[str, str]:
    system_prompt = _read_prompt("r0_system.md")
    user_prompt = _read_prompt("r0_planner.md")
    user_prompt = user_prompt.replace(
        "{challenge}",
        json.dumps(to_jsonable(challenge), ensure_ascii=False, indent=2),
    )
    user_prompt = user_prompt.replace(
        "{state}",
        json.dumps(_state_view(state), ensure_ascii=False, indent=2),
    )
    user_prompt = user_prompt.replace(
        "{tools}",
        json.dumps(tool_schemas, ensure_ascii=False, indent=2, default=str),
    )
    user_prompt = user_prompt.replace(
        "{intelligence}",
        json.dumps(intelligence_context or {}, ensure_ascii=False, indent=2, default=str),
    )
    user_prompt = user_prompt.replace(
        "{domain_context}",
        json.dumps(domain_context or {}, ensure_ascii=False, indent=2, default=str),
    )
    user_prompt = user_prompt.replace(
        "{domain_runtime_context}",
        json.dumps(
            domain_runtime_context or {},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
    )
    user_prompt = user_prompt.replace(
        "{experiment_context}",
        json.dumps(
            experiment_context or {},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
    )
    user_prompt = user_prompt.replace(
        "{experience_context}",
        json.dumps(
            experience_context or {},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
    )
    user_prompt = user_prompt.replace(
        "{web_attack_surface_context}",
        json.dumps(
            web_attack_surface_context or {},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
    )
    user_prompt = user_prompt.replace(
        "{web_research_context}",
        json.dumps(
            web_research_context or {},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
    )
    return system_prompt, user_prompt


def render_analyzer_prompt(
    observation: Observation,
    state: RunState,
) -> Tuple[str, str]:
    system_prompt = _read_prompt("r0_system.md")
    user_prompt = _read_prompt("r0_analyzer.md")
    user_prompt = user_prompt.replace(
        "{observation}",
        json.dumps(to_jsonable(observation), ensure_ascii=False, indent=2),
    )
    user_prompt = user_prompt.replace(
        "{state}",
        json.dumps(_state_view(state), ensure_ascii=False, indent=2),
    )
    return system_prompt, user_prompt

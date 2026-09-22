"""Bounded R11 Planner context assembled from existing evidence stores."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from agent.domains.web.state import WebRuntimeState
from agent.domains.web.research.models import (
    redact_web_context_text,
    redact_web_context_value,
)


class WebResearchContextBuilder:
    def __init__(self, *, item_limit: int = 5) -> None:
        if item_limit <= 0:
            raise ValueError("Web research context limit must be positive")
        self.item_limit = item_limit

    def build(
        self,
        state: WebRuntimeState,
        *,
        intelligence: Mapping[str, Any] | None = None,
        previous_experiments: Sequence[Any] = (),
        relevant_experience: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        model = state.application_model
        experiments = []
        for item in list(previous_experiments)[-self.item_limit:]:
            evaluation = getattr(item, "evaluation", None)
            experiments.append({
                "experiment_id": str(getattr(item, "experiment_id", "")),
                "status": str(getattr(getattr(item, "status", ""), "value", "")),
                "evaluation": str(getattr(getattr(evaluation, "status", ""), "value", "")),
                "evidence_count": len(getattr(item, "evidence_ids", [])),
            })
        experience_items = (relevant_experience or {}).get("relevant_experience", [])
        if not isinstance(experience_items, list):
            experience_items = []
        context = {
            "domain": "web",
            "phase": state.phase,
            "application_model": {
                "endpoints": [{
                    "path": item.path,
                    "methods": item.methods,
                    "parameters": item.parameters,
                    "status_codes": item.status_codes,
                    "authentication_required": item.authentication_required,
                    "response_formats": item.response_formats,
                    "content_types": item.content_types,
                    "access_states": item.access_states,
                    "behavior_tags": item.behavior_tags,
                } for item in model.endpoints[:self.item_limit]],
                "parameters": [{
                    "name": item.name,
                    "endpoints": item.endpoints[:self.item_limit],
                    "methods": item.methods,
                    "locations": item.locations,
                    "semantic_roles": item.semantic_roles,
                    "value_shapes": item.value_shapes,
                    "user_controlled": item.user_controlled,
                    "reflected": item.reflected,
                    "affects_response": item.affects_response,
                } for item in model.parameters[:self.item_limit]],
                "authentication": model.authentication.to_dict(),
                "technologies": [item.name for item in model.technologies[:self.item_limit]],
                "response_behaviors": [{
                    "kind": item.kind,
                    "endpoint": item.endpoint,
                    "summary": item.summary[:300],
                    "changed": item.changed,
                } for item in model.response_behaviors[-self.item_limit:]],
                "relationships": [{
                    "source": item.source,
                    "relation": item.relation,
                    "target": item.target,
                } for item in model.relationships[:self.item_limit]],
                "state_transitions": [{
                    "from_state": item.from_state,
                    "to_state": item.to_state,
                    "event": item.event,
                    "endpoint": item.endpoint,
                } for item in model.state_transitions[-self.item_limit:]],
                "user_controlled_inputs": [{
                    "name": item.name,
                    "endpoint": item.endpoint,
                    "location": item.location,
                    "semantic_role": item.semantic_role,
                    "value_shape": item.value_shape,
                    "reflected": item.reflected,
                    "affects_response": item.affects_response,
                } for item in model.user_controlled_inputs[:self.item_limit]],
                "application_behaviors": [{
                    "category": item.category,
                    "endpoint": item.endpoint,
                    "observation": item.observation[:300],
                    "evidence_type": item.evidence_type,
                } for item in model.application_behaviors[-self.item_limit:]],
                "response_profiles": [{
                    "request_id": item.request_id,
                    "url": item.url,
                    "status_code": item.status_code,
                    "response_format": item.response_format,
                    "json_keys": list(item.json_keys)[:self.item_limit],
                    "error_patterns": list(item.error_patterns),
                    "state_markers": list(item.state_markers),
                    "content_signals": list(item.content_signals),
                    "client_requests": [
                        contract.to_dict()
                        for contract in item.client_requests[:self.item_limit]
                    ],
                } for item in model.response_profiles[-self.item_limit:]],
                "state_differences": [item.to_dict()
                                      for item in model.state_differences[-self.item_limit:]],
            },
            "sessions": [item.safe_dict() for item in state.sessions[:self.item_limit]],
            "web_experiments": [item.to_dict() for item in state.web_experiments[-self.item_limit:]],
            "web_evidence": [{
                **item.to_dict(),
                "observation": redact_web_context_text(item.observation),
            } for item in state.web_evidence[-self.item_limit:]],
            "flag_candidates": [item.safe_dict() for item in state.flag_candidates[-self.item_limit:]],
            "intelligence_summary": dict(intelligence or {}),
            "previous_experiments": experiments,
            "relevant_experience": [dict(item) for item in experience_items[:self.item_limit]
            if isinstance(item, Mapping)],
            "boundary": (
                "Context is evidence only. Any HTTP action remains loopback-scoped and "
                "subject to ToolRuntime, PolicyEngine, and ApprovalManager."
            ),
        }
        safe = redact_web_context_value(context)
        return safe if isinstance(safe, dict) else {}

"""R11 structured Web evidence construction with mandatory provenance."""

from __future__ import annotations

from typing import Any, Mapping

from agent.domains.web.research.models import WebEvidenceRecord, WebEvidenceType


class WebEvidenceFactory:
    """Convert bounded Tool metadata to Web evidence without drawing conclusions."""

    def create_many(
        self,
        result: Any,
        *,
        experiment_id: str = "",
        observation_id: str = "",
    ) -> list[WebEvidenceRecord]:
        artifact_refs = list(dict.fromkeys(
            str(item) for item in getattr(result, "artifact_refs", []) if str(item).strip()
        ))
        if not artifact_refs:
            return []
        metadata = getattr(result, "metadata", {})
        if not isinstance(metadata, Mapping):
            return []
        raw_items = metadata.get("web_evidence", [])
        if not isinstance(raw_items, list):
            raw_items = []
        if not raw_items:
            web = metadata.get("web_observation")
            raw_items = self._from_web_observation(web) if isinstance(web, Mapping) else []
        records: list[WebEvidenceRecord] = []
        for raw in raw_items[:32]:
            if not isinstance(raw, Mapping):
                continue
            observation = str(raw.get("observation", "")).strip()
            if not observation:
                continue
            try:
                evidence_type = WebEvidenceType(
                    str(raw.get("evidence_type", WebEvidenceType.RESPONSE_BEHAVIOR.value))
                )
            except ValueError:
                continue
            records.append(
                WebEvidenceRecord(
                    evidence_type=evidence_type,
                    observation=observation[:2000],
                    artifact_refs=artifact_refs,
                    request_id=str(raw.get("request_id", "")),
                    experiment_id=experiment_id,
                    observation_id=observation_id,
                    endpoint=str(raw.get("endpoint", "")),
                    parameter=str(raw.get("parameter", "")),
                )
            )
        return records

    @staticmethod
    def _from_web_observation(web: Mapping[str, Any]) -> list[dict[str, str]]:
        request_id = str(web.get("request_id", ""))
        endpoint = str(web.get("endpoint", ""))
        records = [{
            "evidence_type": WebEvidenceType.ENDPOINT_DISCOVERED.value,
            "observation": f"Endpoint {endpoint or '/'} returned status {web.get('status_code')}",
            "request_id": request_id,
            "endpoint": endpoint,
        }]
        parameters = web.get("parameters", [])
        if isinstance(parameters, list):
            records.extend({
                "evidence_type": WebEvidenceType.PARAMETER_IDENTIFIED.value,
                "observation": f"Parameter {parameter} was observed at {endpoint or '/'}",
                "request_id": request_id,
                "endpoint": endpoint,
                "parameter": str(parameter),
            } for parameter in parameters[:16])
        return records

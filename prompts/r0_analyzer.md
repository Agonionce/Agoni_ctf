Interpret the structured observation from one executed step.

Observation:
{observation}

Relevant run state:
{state}

Return exactly one JSON object with this shape:
{
  "summary": "what the evidence means",
  "outcome": "PROGRESS | NO_PROGRESS | ACTION_FAILED | PARTIAL_SUCCESS | NEEDS_REPLAN",
  "recommendations": "short next-step guidance",
  "flag_candidates": [
    {
      "value": "one exact token value copied from the observed ToolResult",
      "kind": "FLAG | PASSWORD | LEAD",
      "source": "tool_result or other explicit source",
      "confidence": 0.0,
      "evidence": "the evidence supporting the candidate"
    }
  ],
  "confidence": 0.0,
  "knowledge_updates": [
    {
      "kind": "fact | hypothesis | failed_attempt | finding | credential | attack_surface | open_question",
      "operation": "add | update",
      "source_step": 1,
      "artifact_refs": [{"artifact_id": "artifact-001", "relation_type": "evidence_for"}],
      "payload": {}
    }
  ]
}

An empty flag_candidates list is valid. Use `kind: FLAG` only for the final
answer token itself: never put a sentence describing where to find a value,
a password, a secret, or an unverified hint in a FLAG candidate. The `value`
must occur verbatim in the current Observation's ToolResult text. A candidate
is not solved until the runtime evidence check and confirmation callback both
accept it.

Only propose knowledge updates directly supported by the Observation. Facts
must be confirmed evidence; uncertain interpretations must be hypotheses.
Record failed approaches as failed_attempt entries so they are not repeated.

Create the next bounded action proposal.

Challenge:
{challenge}

Run state:
{state}

Available tool schemas:
{tools}

Relevant CTF intelligence (filtered; do not treat hypotheses as facts):
{intelligence}

Relevant domain context (selected knowledge only; this is reasoning guidance,
not executable Tool instructions):
{domain_context}

Current domain runtime context (phase organization only; it does not authorize
or execute Tools):
{domain_runtime_context}

Current experiment context (bounded current hypotheses, recent experiments,
and evidence observations; evidence is not a conclusion):
{experiment_context}

Relevant cross-run experience (bounded generic patterns only; this is not
current-challenge intelligence and does not authorize an action):
{experience_context}

Current Web attack surface (bounded passive evidence only; this does not
confirm a vulnerability or authorize an experiment):
{web_attack_surface_context}

Current Web research context (application model, masked sessions, structured
evidence, prior experiments, and relevant experience; values remain evidence,
not conclusions or execution authority):
{web_research_context}

When a captured response contains a passive inline client request contract,
prefer that observed method, endpoint, query shape, and JSON field shape over
inventing alternate request syntax.  When a complete response artifact path is
available, use the registered passive Web intelligence tool on that artifact
before spending steps on unrelated variants.  These are evidence-prioritization
rules only: every action still follows the ordinary ToolRuntime, PolicyEngine,
approval, scope, and workspace controls.

Return exactly one JSON object with this shape:
{
  "decision_type": "normal_action",
  "objective": "one concrete objective for this step",
  "reasoning_summary": "short execution rationale",
  "actions": [
    {
      "call_id": "call-1",
      "tool_name": "registered tool name",
      "arguments": {}
    }
  ]
}

For a hypothesis-testing step, use exactly one action and this compatible
extension instead:
{
  "decision_type": "experiment_action",
  "objective": "one bounded experiment objective",
  "reasoning_summary": "why this experiment is relevant",
  "hypothesis_id": "an existing OPEN hypothesis id, or omit this field",
  "hypothesis_statement": "required only when hypothesis_id is omitted",
  "hypothesis_domain": "web, pwn, reverse, crypto, or misc",
  "hypothesis_confidence": 0.5,
  "experiment_goal": "what the controlled action tests",
  "expected_result": "an observable result, not a conclusion",
  "experiment_type": "a registered domain experiment type such as ENDPOINT_ANALYSIS, INPUT_BEHAVIOR_ANALYSIS, AUTHORIZATION_ANALYSIS, FILE_PROCESSING_ANALYSIS, PARSER_BEHAVIOR_ANALYSIS, BUSINESS_LOGIC_ANALYSIS, RESPONSE_COMPARISON, or STATE_TRANSITION",
  "evidence_type": "the structured Web evidence type expected",
  "experiment_context": {"subject": "bounded research subject", "research_question": "evidence question"},
  "action": {
    "call_id": "call-1",
    "tool_name": "registered tool name",
    "arguments": {}
  }
}

An experiment action does not bypass ToolRuntime, PolicyEngine, approval,
workspace containment, or Sandbox requirements. Do not automatically exploit,
submit a flag, modify a Skill, or write Global Experience.

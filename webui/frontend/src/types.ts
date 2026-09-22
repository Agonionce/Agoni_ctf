export type ChallengeStatus =
  | "not_started"
  | "analyzing"
  | "waiting"
  | "needs_help"
  | "completed"
  | "not_solved"
  | "paused";

export interface ChallengeSummary {
  challenge_id: string;
  name: string;
  domain: string;
  status: ChallengeStatus;
  status_label: string;
  created_at: string;
}

export interface ChallengeMaterial {
  name: string;
  kind: "attachment" | "source";
}

export interface ChallengeDetail extends ChallengeSummary {
  description: string;
  target_url: string | null;
  materials: ChallengeMaterial[];
}

export interface ErrorPayload {
  code: string;
  message: string;
  existing_challenge_id?: string | null;
}

export interface ChallengeDraft {
  name: string;
  description: string;
  domain: string;
  targetUrl: string;
  authorizationConfirmed: boolean;
  attachments: File[];
  sourceFiles: File[];
}

export interface RunMilestone {
  title: string;
  detail: string;
  state: "current" | "attention" | "done";
  occurred_at: string;
}

export interface PendingDecision {
  decision_id: string;
  kind: "action" | "answer";
  title: string;
  summary: string;
  risk_label: string;
  created_at: string;
  candidate_value?: string | null;
  candidate_source?: string | null;
  candidate_evidence?: string | null;
}

export interface RunView {
  status: string;
  status_label: string;
  active: boolean;
  milestones: RunMilestone[];
  pending_decision: PendingDecision | null;
  can_start: boolean;
  can_abort: boolean;
  can_resume: boolean;
  completion_available: boolean;
}

export interface OutcomeRecord {
  title: string;
  detail: string;
  status_label: string;
  certainty_label: string;
  occurred_at: string | null;
  artifact_paths: string[];
}

export interface ArtifactOutcome {
  artifact_id?: string | null;
  name: string;
  kind_label: string;
  created_at: string | null;
  path?: string | null;
}

export interface FlagOutcome {
  status: "found" | "not_found" | "conflict";
  status_label: string;
  value: string | null;
  source: string | null;
  evidence: string | null;
  evidence_paths: string[];
  reason: string | null;
}

export interface WebEndpointOutcome {
  path: string;
  methods: string[];
  parameters: string[];
  response_formats: string[];
  access_label: string;
}

export interface WebOutcome {
  available: boolean;
  phase_label: string;
  authentication_label: string;
  technologies: string[];
  endpoints: WebEndpointOutcome[];
}

export interface ChallengeOutcomes {
  flag: FlagOutcome;
  facts: OutcomeRecord[];
  findings: OutcomeRecord[];
  hypotheses: OutcomeRecord[];
  experiments: OutcomeRecord[];
  evidence: OutcomeRecord[];
  artifacts: ArtifactOutcome[];
  web: WebOutcome;
}

export interface ChallengeDocuments {
  available: boolean;
  report: string;
  writeup: string;
  lessons: string;
}

export interface ExperienceCandidate {
  candidate_id: string;
  category_label: string;
  kind_label: string;
  pattern: string;
  strategy: string;
  lesson: string;
  confidence_label: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
  status_label: string;
}

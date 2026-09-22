import type {
  ChallengeDetail,
  ChallengeDocuments,
  ChallengeDraft,
  ChallengeOutcomes,
  ChallengeSummary,
  ErrorPayload,
  ExperienceCandidate,
  RunView,
} from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly payload: ErrorPayload;

  constructor(status: number, payload: ErrorPayload) {
    super(payload.message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let payload: ErrorPayload = {
      code: "request_failed",
      message: "请求没有完成，请稍后重试",
    };
    try {
      const raw = (await response.json()) as ErrorPayload | { detail?: string };
      if ("code" in raw && typeof raw.code === "string") {
        payload = raw as ErrorPayload;
      } else if ("detail" in raw && typeof raw.detail === "string") {
        payload.message = raw.detail;
      }
    } catch {
      // Keep the concise fallback without exposing an HTTP response body.
    }
    throw new ApiError(response.status, payload);
  }
  return (await response.json()) as T;
}

export async function listChallenges(signal?: AbortSignal): Promise<ChallengeSummary[]> {
  const result = await request<{ items: ChallengeSummary[] }>("/api/challenges", {
    signal,
  });
  return result.items;
}

export function getChallenge(
  challengeId: string,
  signal?: AbortSignal,
): Promise<ChallengeDetail> {
  return request<ChallengeDetail>(
    `/api/challenges/${encodeURIComponent(challengeId)}`,
    { signal },
  );
}

export function createChallenge(draft: ChallengeDraft): Promise<ChallengeDetail> {
  const body = new FormData();
  body.set("name", draft.name);
  body.set("description", draft.description);
  body.set("domain", draft.domain);
  body.set("target_url", draft.targetUrl);
  body.set("authorization_confirmed", String(draft.authorizationConfirmed));
  draft.attachments.forEach((file) => body.append("attachments", file));
  draft.sourceFiles.forEach((file) => body.append("source_files", file));
  return request<ChallengeDetail>("/api/challenges", {
    method: "POST",
    body,
  });
}

export function getRun(challengeId: string, signal?: AbortSignal): Promise<RunView> {
  return request<RunView>(`/api/challenges/${encodeURIComponent(challengeId)}/run`, {
    signal,
  });
}

export function startRun(challengeId: string): Promise<RunView> {
  return request<RunView>(`/api/challenges/${encodeURIComponent(challengeId)}/runs`, {
    method: "POST",
  });
}

export function resumeRun(challengeId: string): Promise<RunView> {
  return request<RunView>(
    `/api/challenges/${encodeURIComponent(challengeId)}/runs/resume`,
    { method: "POST" },
  );
}

export function abortRun(challengeId: string): Promise<RunView> {
  return request<RunView>(
    `/api/challenges/${encodeURIComponent(challengeId)}/run/abort`,
    { method: "POST" },
  );
}

export function decideRun(
  challengeId: string,
  decisionId: string,
  decision: "approve" | "reject",
): Promise<RunView> {
  return request<RunView>(
    `/api/challenges/${encodeURIComponent(challengeId)}/run/decisions/${encodeURIComponent(decisionId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    },
  );
}

export function getOutcomes(
  challengeId: string,
  signal?: AbortSignal,
): Promise<ChallengeOutcomes> {
  return request<ChallengeOutcomes>(
    `/api/challenges/${encodeURIComponent(challengeId)}/outcomes`,
    { signal },
  );
}

export function getDocuments(
  challengeId: string,
  signal?: AbortSignal,
): Promise<ChallengeDocuments> {
  return request<ChallengeDocuments>(
    `/api/challenges/${encodeURIComponent(challengeId)}/documents`,
    { signal },
  );
}

export async function getExperienceCandidates(
  challengeId: string,
  signal?: AbortSignal,
): Promise<ExperienceCandidate[]> {
  const result = await request<{ items: ExperienceCandidate[] }>(
    `/api/challenges/${encodeURIComponent(challengeId)}/experience-candidates`,
    { signal },
  );
  return result.items;
}

export function reviewExperienceCandidate(
  challengeId: string,
  candidateId: string,
  decision: "approve" | "reject",
): Promise<ExperienceCandidate> {
  return request<ExperienceCandidate>(
    `/api/challenges/${encodeURIComponent(challengeId)}/experience-candidates/${encodeURIComponent(candidateId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    },
  );
}

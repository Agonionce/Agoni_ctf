import type { ChallengeStatus } from "../types";

interface StatusTextProps {
  status: ChallengeStatus;
  label: string;
}

export function StatusText({ status, label }: StatusTextProps) {
  return <span className={`status-text status-text--${status}`}>{label}</span>;
}

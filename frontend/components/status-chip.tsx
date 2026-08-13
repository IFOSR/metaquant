import type { ResearchJobState } from "../lib/types";

const labels: Record<ResearchJobState, string> = {
  DRAFT: "Draft",
  READY: "Ready",
  RUNNING: "Running",
  WAITING_INPUT: "Waiting input",
  BLOCKED_POLICY: "Blocked policy",
  SUCCEEDED: "Succeeded",
  FAILED: "Failed",
  CANCELLED: "Cancelled",
  ARCHIVED: "Archived",
};

export function StatusChip({ state }: { state: ResearchJobState }) {
  return <span className={`status-chip status-${state.toLowerCase()}`}>{labels[state]}</span>;
}

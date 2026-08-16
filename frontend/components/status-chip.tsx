"use client";

import type { MessageKey } from "../lib/i18n";
import type { ResearchJobState } from "../lib/types";
import { useI18n } from "./i18n-provider";

const labelKeys: Record<ResearchJobState, MessageKey> = {
  DRAFT: "status.DRAFT",
  READY: "status.READY",
  RUNNING: "status.RUNNING",
  WAITING_INPUT: "status.WAITING_INPUT",
  BLOCKED_POLICY: "status.BLOCKED_POLICY",
  SUCCEEDED: "status.SUCCEEDED",
  FAILED: "status.FAILED",
  CANCELLED: "status.CANCELLED",
  ARCHIVED: "status.ARCHIVED",
};

export function StatusChip({ state }: { state: ResearchJobState }) {
  const { t } = useI18n();
  return <span className={`status-chip status-${state.toLowerCase()}`}>{t(labelKeys[state])}</span>;
}

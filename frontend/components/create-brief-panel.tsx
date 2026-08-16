"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { quantApiClient } from "../lib/client";
import type { BriefDraftInput } from "../lib/types";
import { useI18n } from "./i18n-provider";
import { StateBoundary } from "./state-boundary";

const EMPTY_DRAFT: BriefDraftInput = {
  hypothesis: "TBD",
  economicMechanism: "TBD",
  expectedDirection: "UNKNOWN",
  falsificationConditions: ["TBD"],
  allowedDataDomains: ["formal.market.eod"],
  forbiddenDataDomains: [],
  constraints: ["TBD"],
  evidenceRefIds: [],
  uncertainties: [],
};

export function CreateBriefPanel({
  jobId,
  jobVersion,
}: {
  jobId: string;
  jobVersion: number;
}) {
  const { t } = useI18n();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    setBusy(true);
    setError(null);
    try {
      await quantApiClient.createBrief(jobId, EMPTY_DRAFT, jobVersion);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setBusy(false);
    }
  }

  return (
    <StateBoundary
      state="empty"
      title={t("briefCreate.title")}
      detail={error ?? t("briefCreate.detail")}
      actionLabel={busy ? t("briefCreate.creating") : t("briefCreate.action")}
      onAction={busy ? undefined : create}
    />
  );
}

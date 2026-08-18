import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ResearchJobSnapshot } from "../components/research-job-snapshot";
import type { ResearchJob } from "../lib/types";
import { renderWithI18n } from "./render";

const job: ResearchJob = {
  id: "rj_1",
  version: "2",
  title: "Server job",
  market: "CN_A",
  environment: "RESEARCH",
  state: "READY",
  owner: "researcher-1",
  currentStage: null,
  budget: {
    candidateLimit: 10,
    llmTokenLimit: 1000,
    cpuHours: 2,
    wallClockMinutes: 30,
  },
  budgetUsed: null,
  latestAttempt: null,
  snapshotRefs: [],
  policyVersion: null,
  runFingerprint: null,
  experimentId: null,
  freshness: null,
  blockers: [],
  allowedActions: [],
  updatedAt: "2026-08-13T01:00:00Z",
};

describe("ResearchJobSnapshot", () => {
  it("does not invent run progress, attempts, policy, or references", () => {
    renderWithI18n(<ResearchJobSnapshot job={job} />);

    expect(screen.getByText("未返回执行快照。")).toBeInTheDocument();
    expect(screen.queryByText(/validation gates are running/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/attempt 0/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/validation-policy:\/\/pending/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/G0|G1|G2|G3|G4|G5/)).not.toBeInTheDocument();
  });
});

import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ExperimentMonitor } from "../components/experiment-monitor";
import type {
  Experiment,
  ExperimentArtifacts,
  ExperimentRun,
  ExperimentRunState,
} from "../lib/types";
import { renderWithI18n } from "./render";

const experiment: Experiment = {
  id: "exp_1",
  projectId: "local",
  researchJobId: "rj_1",
  briefVersionId: "brief_1",
  market: "CN_A",
  state: "PREREGISTERED",
  resourceVersion: 1,
  specHash: "sha256:spec",
  factorIrHash: "sha256:factor-ir",
  snapshotId: "snapshot-cn-a-20260812",
  snapshotManifestHash: "sha256:snapshot",
  factorIr: null,
  decisionTime: null,
  randomSeed: null,
  latestRunId: "run_1",
  createdAt: "2026-08-13T01:00:00Z",
  createdBy: "researcher-1",
};

function run(state: ExperimentRunState): ExperimentRun {
  return {
    id: "run_1",
    experimentId: "exp_1",
    market: "CN_A",
    state,
    runFingerprint: "sha256:run-fingerprint",
    attemptCount: 2,
    validationSummary: {
      observationCount: 100,
      finiteCount: 96,
      missingCount: 4,
      coverageRatio: 0.96,
      minimum: -1,
      maximum: 1,
      mean: 0,
    },
    invariance: {
      futureTruncationPassed: true,
      sentinelIsolationPassed: true,
      baselineOutputHash: "sha256:baseline",
      futureTruncationOutputHash: "sha256:baseline",
      sentinelIsolationOutputHash: "sha256:baseline",
    },
    createdAt: "2026-08-13T01:00:00Z",
    updatedAt: "2026-08-13T01:01:00Z",
  };
}

const artifacts: ExperimentArtifacts = {
  items: [
    {
      contentHash: "sha256:computation",
      artifactType: "FactorComputationArtifact",
      schemaVersion: "factor-computation/v1",
      sizeBytes: 2048,
      mediaType: "application/json",
      domainHash: "sha256:observations",
    },
    {
      contentHash: "sha256:validation",
      artifactType: "ValidationArtifact",
      schemaVersion: "factor-validation/v1",
      sizeBytes: 512,
      mediaType: "application/json",
      domainHash: "sha256:validation-domain",
    },
  ],
  lineage: [
    {
      edgeHash: "sha256:edge",
      sourceArtifactHash: "sha256:computation",
      targetArtifactHash: "sha256:validation",
      relation: "VALIDATED_BY",
    },
  ],
};

afterEach(cleanup);

describe("ExperimentMonitor", () => {
  it("shows server-authoritative states, hashes, validation and lineage", () => {
    renderWithI18n(
      <ExperimentMonitor
        experiment={experiment}
        run={run("SUCCEEDED")}
        artifacts={artifacts}
      />,
    );

    expect(screen.getByText("已预注册")).toBeInTheDocument();
    expect(screen.getByText("已成功")).toBeInTheDocument();
    expect(screen.getByText("2 次尝试")).toBeInTheDocument();
    expect(screen.getByText("96.00%")).toBeInTheDocument();
    expect(screen.getByText("未来截断")).toBeInTheDocument();
    expect(screen.getByText("哨兵隔离")).toBeInTheDocument();
    expect(screen.getByText("FactorComputationArtifact")).toBeInTheDocument();
    expect(screen.getByText("VALIDATED_BY")).toBeInTheDocument();
    expect(screen.getByText("sha256:factor-ir")).toBeInTheDocument();
    expect(screen.queryByText(/profit|sharpe/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /paper|live/i })).not.toBeInTheDocument();
  });

  it.each([
    ["BLOCKED_POLICY", "被策略阻止"],
    ["QUARANTINED", "已隔离"],
    ["NON_REPRODUCIBLE", "不可复现"],
  ] as const)("renders only the server-provided %s state", (state, label) => {
    renderWithI18n(
      <ExperimentMonitor
        experiment={experiment}
        run={run(state)}
        artifacts={artifacts}
      />,
    );

    expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.queryByText("Advancement blocked")).not.toBeInTheDocument();
    expect(
      screen.queryByText(/cannot advance|valid research result|pending investigation/i),
    ).not.toBeInTheDocument();
  });

  it("renders an explicit empty state when the server has no experiment reference", () => {
    renderWithI18n(
      <ExperimentMonitor experiment={null} run={null} artifacts={null} />,
    );

    expect(screen.getByText("尚无预注册实验")).toBeInTheDocument();
    expect(screen.getByText(/该研究任务未返回任何实验资源。/)).toBeInTheDocument();
  });
});

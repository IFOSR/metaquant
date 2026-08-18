import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { FactorProfilePanel } from "../components/factor-profile-panel";
import type { Experiment, ResearchBrief } from "../lib/types";
import { renderWithI18n } from "./render";

const brief: ResearchBrief = {
  id: "brief-1",
  jobId: "job-1",
  version: 2,
  resourceVersion: 2,
  status: "FROZEN",
  hypothesis: "螺纹钢和黄金的短期价格动量在未来 5 个交易日延续",
  economicMechanism: "商品价格信息扩散缓慢，动量效应在日频尺度持续",
  expectedDirection: "POSITIVE",
  falsificationConditions: [],
  allowedDataDomains: [],
  forbiddenDataDomains: [],
  constraints: [],
  evidenceRefIds: [],
  uncertainties: [],
  contentHash: null,
  createdAt: "2026-08-01T00:00:00Z",
  createdBy: "agent",
  frozenAt: "2026-08-01T01:00:00Z",
};

const experiment: Experiment = {
  id: "exp-1",
  projectId: "proj-1",
  researchJobId: "job-1",
  briefVersionId: "brief-1",
  market: "CN_COMMODITY_FUTURES",
  state: "PREREGISTERED",
  resourceVersion: 1,
  specHash: "a".repeat(64),
  factorIrHash: "b".repeat(64),
  snapshotId: "snapshot-cn-futures-eod-001",
  snapshotManifestHash: "c".repeat(64),
  factorIr: {
    factorId: "classic.cn_futures.momentum_1d",
    version: "1.0.0",
    marketScope: {
      market: "CN_COMMODITY_FUTURES",
      frequency: "1d",
      universeRef: "futures:liquid-initial",
    },
    decisionClock: {
      signalTime: "T_CLOSE+30m",
      earliestTradeTime: "T+1_OPEN",
    },
    inputs: [
      {
        alias: "close",
        fieldRef: "market.eod.close",
        dataType: "ScalarSeries",
        unit: "CNY",
        availableTimeRule: "T_CLOSE+20m",
      },
    ],
    expression: {
      op: "returns",
      args: [{ ref: "close" }],
      params: { periods: 1 },
    },
  },
  decisionTime: "2026-08-05T16:00:00Z",
  randomSeed: 41,
  latestRunId: "run-1",
  createdAt: "2026-08-01T02:00:00Z",
  createdBy: "agent",
};

afterEach(cleanup);

describe("FactorProfilePanel", () => {
  it("renders identity, meaning and hypothesis", () => {
    renderWithI18n(
      <FactorProfilePanel brief={brief} experiment={experiment} />,
    );

    expect(screen.getByText("Factor profile")).toBeInTheDocument();
    expect(screen.getByText("classic.cn_futures.momentum_1d")).toBeInTheDocument();
    expect(screen.getByText("returns(close, periods=1)")).toBeInTheDocument();
    expect(screen.getByText("market.eod.close")).toBeInTheDocument();
    expect(screen.getByText(/T_CLOSE\+30m/)).toBeInTheDocument();
    expect(
      screen.getByText("螺纹钢和黄金的短期价格动量在未来 5 个交易日延续"),
    ).toBeInTheDocument();
    expect(screen.getByText(/POSITIVE/)).toBeInTheDocument();
    expect(screen.queryByText("How it was produced")).not.toBeInTheDocument();
  });

  it("falls back gracefully without brief", () => {
    renderWithI18n(<FactorProfilePanel brief={null} experiment={experiment} />);

    expect(screen.getByText("No frozen research brief yet.")).toBeInTheDocument();
  });

  it("renders an empty state when no experiment exists", () => {
    renderWithI18n(<FactorProfilePanel brief={null} experiment={null} />);

    expect(screen.getByText("No factor registered")).toBeInTheDocument();
  });
});

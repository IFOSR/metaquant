import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { IndependencePanel } from "../components/independence-panel";
import type { IndependenceSummary } from "../lib/types";
import { renderWithI18n } from "./render";

const report: IndependenceSummary = {
  runId: "run-001",
  outputHash: "0".repeat(64),
  baselineIc: 0.042,
  orthogonalizedIc: 0.031,
  maxAbsCorrelation: 0.38,
  replicatedRiskFactor: false,
  pairwise: [
    { factorIrHash: "a".repeat(64), pearson: 0.31, spearman: 0.28 },
    { factorIrHash: "b".repeat(64), pearson: 0.12, spearman: 0.09 },
  ],
};

afterEach(cleanup);

describe("IndependencePanel", () => {
  it("renders incremental IC metrics and pairwise correlations", () => {
    renderWithI18n(<IndependencePanel report={report} />);

    expect(screen.getByText("因子独立性")).toBeInTheDocument();
    expect(screen.getByText("基准 IC")).toBeInTheDocument();
    expect(screen.getByText("0.0420")).toBeInTheDocument();
    expect(screen.getByText("正交化 IC")).toBeInTheDocument();
    expect(screen.getByText("0.0310")).toBeInTheDocument();
    expect(screen.getByText("最大绝对相关")).toBeInTheDocument();
    expect(screen.getByText("否")).toBeInTheDocument();
    expect(screen.getByText("两两相关性")).toBeInTheDocument();
    expect(screen.getByText("2 个池内因子")).toBeInTheDocument();
  });

  it("marks a replicated risk factor", () => {
    renderWithI18n(
      <IndependencePanel
        report={{ ...report, replicatedRiskFactor: true }}
      />,
    );

    expect(screen.getByText("是")).toBeInTheDocument();
  });

  it("renders an explicit empty state when no report exists", () => {
    renderWithI18n(<IndependencePanel report={null} />);

    expect(screen.getByText("暂无独立性评估")).toBeInTheDocument();
    expect(screen.getByText(/本次运行未提交独立性报告。/)).toBeInTheDocument();
  });

  it("shows an empty pairwise note when there are no pool factors", () => {
    renderWithI18n(<IndependencePanel report={{ ...report, pairwise: [] }} />);

    expect(
      screen.getByText(/没有可对比的池内因子。/),
    ).toBeInTheDocument();
  });
});

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

    expect(screen.getByText("Factor independence")).toBeInTheDocument();
    expect(screen.getByText("Baseline IC")).toBeInTheDocument();
    expect(screen.getByText("0.0420")).toBeInTheDocument();
    expect(screen.getByText("Orthogonalized IC")).toBeInTheDocument();
    expect(screen.getByText("0.0310")).toBeInTheDocument();
    expect(screen.getByText("Max abs correlation")).toBeInTheDocument();
    expect(screen.getByText("NO")).toBeInTheDocument();
    expect(screen.getByText("Pairwise correlation")).toBeInTheDocument();
    expect(screen.getByText("2 pool factors")).toBeInTheDocument();
  });

  it("marks a replicated risk factor", () => {
    renderWithI18n(
      <IndependencePanel
        report={{ ...report, replicatedRiskFactor: true }}
      />,
    );

    expect(screen.getByText("YES")).toBeInTheDocument();
  });

  it("renders an explicit empty state when no report exists", () => {
    renderWithI18n(<IndependencePanel report={null} />);

    expect(screen.getByText("No independence assessment")).toBeInTheDocument();
    expect(screen.getByText(/No independence report/)).toBeInTheDocument();
  });

  it("shows an empty pairwise note when there are no pool factors", () => {
    renderWithI18n(<IndependencePanel report={{ ...report, pairwise: [] }} />);

    expect(
      screen.getByText(/No pool factors to compare against/),
    ).toBeInTheDocument();
  });
});

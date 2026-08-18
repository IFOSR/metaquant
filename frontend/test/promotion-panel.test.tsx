import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { PromotionPanel } from "../components/promotion-panel";
import type { PromotionSummary } from "../lib/types";
import { renderWithI18n } from "./render";

const report: PromotionSummary = {
  runId: "run-001",
  outputHash: "0".repeat(64),
  factorIrHash: "a".repeat(64),
  policyId: "policy://cn-a-promotion/v1",
  disposition: "PROMOTE",
  totalScore: 0.72,
  gates: [
    { name: "data_quality.coverage", passed: true, observed: 0.95, threshold: 0.8, note: null },
    { name: "oos.direction", passed: true, observed: 0.05, threshold: 0.02, note: null },
  ],
  componentScores: [
    ["effect", 0.8],
    ["stability", 0.7],
  ],
  rationale: "all hard gates passed",
};

afterEach(cleanup);

describe("PromotionPanel", () => {
  it("renders disposition, scorecard, gates and rationale", () => {
    renderWithI18n(<PromotionPanel report={report} />);

    expect(screen.getByText("晋升决策")).toBeInTheDocument();
    expect(screen.getByText("晋升")).toBeInTheDocument();
    expect(screen.getByText("0.7200")).toBeInTheDocument();
    expect(screen.getByText("effect")).toBeInTheDocument();
    expect(screen.getByText("data_quality.coverage")).toBeInTheDocument();
    expect(screen.getByText("all hard gates passed")).toBeInTheDocument();
  });

  it("renders an explicit empty state when no report exists", () => {
    renderWithI18n(<PromotionPanel report={null} />);

    expect(screen.getByText("暂无晋升决策")).toBeInTheDocument();
    expect(screen.getByText(/本次运行未提交晋升决策。/)).toBeInTheDocument();
  });
});

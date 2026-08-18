import { cleanup, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { FactorValidationReportPanel } from "../components/factor-validation-report";
import type { FactorValidationReport } from "../lib/types";
import { renderWithI18n } from "./render";

const report: FactorValidationReport = {
  policyId: "policy://cn-a-daily-factor/v1",
  policyHash: "0".repeat(64),
  labelId: "label.cn_a.forward_5d",
  labelHash: "0".repeat(64),
  factorArtifactHash: "sha256:factor-computation",
  dataQuality: {
    observationCount: 100,
    finiteCount: 96,
    coverageRatio: 0.96,
    constantRatio: 0.12,
  },
  predictivePower: {
    meanPearsonIc: 0.042,
    meanRankIc: 0.038,
    icir: 0.55,
    nwT: 3.1,
    icDecay: [{ horizon: 5, meanIc: 0.042 }],
    quantileReturns: [
      { quantile: 1, meanReturn: -0.01 },
      { quantile: 2, meanReturn: 0.0 },
      { quantile: 3, meanReturn: 0.012 },
    ],
    topBottomSpread: 0.022,
    monotonic: true,
  },
};

afterEach(cleanup);

describe("FactorValidationReportPanel", () => {
  it("renders policy, predictive power, quantiles and data quality", () => {
    renderWithI18n(<FactorValidationReportPanel report={report} />);

    expect(screen.getByText("因子校验")).toBeInTheDocument();
    expect(
      screen.getByText("policy://cn-a-daily-factor/v1"),
    ).toBeInTheDocument();
    expect(screen.getByText("平均 Pearson IC")).toBeInTheDocument();
    expect(screen.getByText("0.0420")).toBeInTheDocument();
    expect(screen.getByText("96.00%")).toBeInTheDocument();
    expect(screen.getByText("Q1")).toBeInTheDocument();
    expect(screen.getByText("多空价差")).toBeInTheDocument();
    expect(screen.queryByText(/profit|sharpe/i)).not.toBeInTheDocument();
  });

  it("renders an explicit empty state when no report exists", () => {
    renderWithI18n(<FactorValidationReportPanel report={null} />);

    expect(screen.getByText("暂无因子校验")).toBeInTheDocument();
    expect(screen.getByText(/本次运行未提交校验报告。/)).toBeInTheDocument();
  });
});

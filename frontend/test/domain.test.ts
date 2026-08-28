import { describe, expect, it } from "vitest";

import {
  getVisibleNavigation,
  validateResearchJob,
} from "../lib/domain";

describe("session capability boundaries", () => {
  it("hides backtest and paper navigation when the session lacks capabilities", () => {
    const navigation = getVisibleNavigation([
      "research.jobs.read",
      "research.jobs.write",
    ]);

    expect(navigation.map((item) => item.labelKey)).toEqual([
      "nav.overview",
      "nav.newResearch",
    ]);
    const labels = navigation.map((item) => item.labelKey) as string[];
    expect(labels.includes("nav.backtest")).toBe(false);
    expect(labels.includes("nav.paper")).toBe(false);
  });
});

describe("research job market rules", () => {
  it("requires the futures exchange, actual contracts, settlement clock, and roll policy", () => {
    const result = validateResearchJob({
      market: "CN_COMMODITY_FUTURES",
      environment: "RESEARCH",
      universeRef: "futures:liquid",
      frequency: "1d",
      decisionClock: "T close",
      tradeClock: "T+1 open",
      settlementClock: "",
      exchangeScope: [],
      contractSelection: "",
      rollPolicy: "",
      horizon: "5d",
      briefVersionId: "brief_v1",
    });

    expect(result.valid).toBe(false);
    expect(result.errors).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ field: "settlementClock" }),
        expect.objectContaining({ field: "exchangeScope" }),
        expect.objectContaining({ field: "contractSelection" }),
        expect.objectContaining({ field: "rollPolicy" }),
      ]),
    );
  });

  it("accepts minute-level frequencies for formal research", () => {
    const result = validateResearchJob({
      market: "CN_A",
      environment: "RESEARCH",
      universeRef: "cn-a:main-board",
      frequency: "5m",
      decisionClock: "T close",
      tradeClock: "T+1 open",
      settlementClock: "",
      exchangeScope: [],
      contractSelection: "",
      rollPolicy: "",
      horizon: "5d",
      briefVersionId: "brief_v1",
    });

    expect(result.valid).toBe(true);
    expect(result.errors).toEqual([]);
  });
});

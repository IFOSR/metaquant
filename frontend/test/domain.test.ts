import { describe, expect, it } from "vitest";

import {
  getVisibleNavigation,
  validateResearchJob,
} from "../lib/domain";

describe("session capability boundaries", () => {
  it("hides strategy and execution navigation when the session lacks capabilities", () => {
    const navigation = getVisibleNavigation([
      "research.jobs.read",
      "research.jobs.write",
    ]);

    expect(navigation.map((item) => item.label)).toEqual([
      "Overview",
      "Research jobs",
      "New research",
    ]);
    expect((navigation.map((item) => item.label) as string[]).includes("Operations")).toBe(
      false,
    );
  });
});

describe("research job market rules", () => {
  it("requires the futures exchange, actual contracts, settlement clock, and roll policy", () => {
    const result = validateResearchJob({
      market: "CN_COMMODITY_FUTURES",
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

  it("rejects disabled five-minute formal research", () => {
    const result = validateResearchJob({
      market: "CN_A",
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

    expect(result.valid).toBe(false);
    expect(result.errors).toEqual([
      expect.objectContaining({
        field: "frequency",
        message: "Formal research is enabled only at 1d in G1.",
      }),
    ]);
  });
});

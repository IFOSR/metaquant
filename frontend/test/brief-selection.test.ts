import { describe, expect, it } from "vitest";

import { selectLatestBriefVersion } from "../lib/briefs";
import type { ResearchBrief } from "../lib/types";

function brief(version: number, resourceVersion = 1): ResearchBrief {
  return {
    id: `brief_${version}`,
    jobId: "job_1",
    version,
    resourceVersion,
    status: "DRAFT",
    hypothesis: "test",
    economicMechanism: "test",
    expectedDirection: "UNKNOWN",
    falsificationConditions: [],
    allowedDataDomains: [],
    forbiddenDataDomains: [],
    constraints: [],
    evidenceRefIds: [],
    uncertainties: [],
    contentHash: null,
    createdAt: "2026-08-12T00:00:00Z",
    createdBy: "tester",
    frozenAt: null,
  };
}

describe("selectLatestBriefVersion", () => {
  it("selects the highest version regardless of API ordering", () => {
    expect(
      selectLatestBriefVersion([brief(1), brief(3), brief(2)])?.id,
    ).toBe("brief_3");
  });

  it("returns undefined for a job without brief versions", () => {
    expect(selectLatestBriefVersion([])).toBeUndefined();
  });
});

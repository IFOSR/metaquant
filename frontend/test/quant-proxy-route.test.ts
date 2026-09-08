import { describe, expect, it } from "vitest";

import { upstreamTimeoutMs } from "../app/api/quant/[...path]/route";

describe("quant API proxy timeout", () => {
  it("allows strategy draft agent turns to finish both backend attempts", () => {
    expect(upstreamTimeoutMs(["v1", "strategy-drafts", "draft-1", "messages"])).toBe(
      700_000,
    );
  });

  it("keeps ordinary API calls on the short timeout", () => {
    expect(upstreamTimeoutMs(["v1", "session"])).toBe(15_000);
  });
});

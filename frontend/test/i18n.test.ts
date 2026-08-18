import { describe, expect, it } from "vitest";

import { translate, type MessageKey } from "../lib/i18n";

describe("i18n zh dictionary", () => {
  it("translates known keys", () => {
    const key: MessageKey = "nav.overview";
    expect(translate(key)).toBe("概览");
  });

  it("interpolates params and leaves unknown placeholders intact", () => {
    expect(translate("jobs.count", { count: 3 })).toBe("3 条已授权记录");
    expect(translate("jobs.count")).toBe("{count} 条已授权记录");
  });
});

import { describe, expect, it } from "vitest";

import {
  dictionaries,
  resolveLocale,
  translate,
  type MessageKey,
} from "../lib/i18n";

describe("i18n dictionaries", () => {
  it("keeps zh and en key sets identical", () => {
    const enKeys = Object.keys(dictionaries.en).sort();
    const zhKeys = Object.keys(dictionaries.zh).sort();
    expect(zhKeys).toEqual(enKeys);
  });

  it("resolves locale with zh as the default", () => {
    expect(resolveLocale("en")).toBe("en");
    expect(resolveLocale("zh")).toBe("zh");
    expect(resolveLocale(undefined)).toBe("zh");
    expect(resolveLocale("fr")).toBe("zh");
  });

  it("translates in both locales", () => {
    const key: MessageKey = "nav.overview";
    expect(translate("en", key)).toBe("Overview");
    expect(translate("zh", key)).toBe("概览");
  });

  it("interpolates params and leaves unknown placeholders intact", () => {
    expect(translate("en", "jobs.count", { count: 3 })).toBe(
      "3 authorized records",
    );
    expect(translate("zh", "jobs.count", { count: 3 })).toBe(
      "3 条已授权记录",
    );
    expect(translate("en", "jobs.count")).toBe("{count} authorized records");
  });
});

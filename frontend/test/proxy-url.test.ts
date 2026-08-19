import { describe, expect, it } from "vitest";

import { buildProxyTarget, isAllowedQuantApiPath } from "../lib/proxy-url";

describe("buildProxyTarget", () => {
  it("preserves FastAPI action suffixes without URL normalization", () => {
    expect(
      buildProxyTarget(
        "http://localhost:8000/",
        ["v1", "research-brief-versions", "rbv_1:freeze"],
        "",
      ),
    ).toBe(
      "http://localhost:8000/v1/research-brief-versions/rbv_1%3Afreeze",
    );
  });

  it("preserves query strings", () => {
    expect(
      buildProxyTarget(
        "http://localhost:8000",
        ["v1", "research-jobs"],
        "?market=CN_A",
      ),
    ).toBe("http://localhost:8000/v1/research-jobs?market=CN_A");
  });

  it("allows only the P0 research control-plane paths", () => {
    expect(isAllowedQuantApiPath(["v1", "research-jobs"])).toBe(true);
    expect(isAllowedQuantApiPath(["v1", "research-jobs", "rj_1"])).toBe(true);
    expect(
      isAllowedQuantApiPath([
        "v1",
        "research-jobs",
        "rj_1",
        "brief-versions",
      ]),
    ).toBe(true);
    expect(
      isAllowedQuantApiPath([
        "v1",
        "research-brief-versions",
        "rbv_1:freeze",
      ]),
    ).toBe(true);
    expect(isAllowedQuantApiPath(["v1", "experiments:preregister"])).toBe(true);
    expect(isAllowedQuantApiPath(["v1", "experiments", "exp_1"])).toBe(true);
    expect(isAllowedQuantApiPath(["v1", "experiments", "exp_1:run"])).toBe(true);
    expect(isAllowedQuantApiPath(["v1", "experiment-runs", "run_1"])).toBe(true);
    expect(
      isAllowedQuantApiPath([
        "v1",
        "experiment-runs",
        "run_1",
        "artifacts",
      ]),
    ).toBe(true);
    expect(isAllowedQuantApiPath(["v1", "session"])).toBe(true);
    expect(isAllowedQuantApiPath(["v1", "session", "extra"])).toBe(false);
    expect(isAllowedQuantApiPath(["v1", "formal-snapshots"])).toBe(true);
    expect(isAllowedQuantApiPath(["v1", "formal-snapshots", "x"])).toBe(false);
    expect(isAllowedQuantApiPath(["v1", "data-provisioning"])).toBe(true);
    expect(isAllowedQuantApiPath(["v1", "data-provisioning", "t_1"])).toBe(true);
    expect(isAllowedQuantApiPath(["v1", "data-provisioning", "t_1", "x"])).toBe(
      false,
    );
    expect(isAllowedQuantApiPath(["v1", "research-briefs:from-paper"])).toBe(
      true,
    );
    expect(
      isAllowedQuantApiPath(["v1", "research-briefs:extract-factor"]),
    ).toBe(true);
    expect(
      isAllowedQuantApiPath(["v1", "research-pipelines:from-paper"]),
    ).toBe(true);
    expect(
      isAllowedQuantApiPath(["v1", "research-pipelines:from-paper-file"]),
    ).toBe(true);
    expect(isAllowedQuantApiPath(["v1", "execution", "orders"])).toBe(false);
    expect(isAllowedQuantApiPath(["v1", "execution", "state"])).toBe(true);
    expect(isAllowedQuantApiPath(["v1", "execution", "kill-switch:trip"])).toBe(
      true,
    );
    expect(isAllowedQuantApiPath(["v1", "execution", "kill-switch:reset"])).toBe(
      true,
    );
    expect(isAllowedQuantApiPath(["v1", "experiments", "exp_1:delete"])).toBe(
      false,
    );
    expect(isAllowedQuantApiPath(["health", "ready"])).toBe(false);
  });
});

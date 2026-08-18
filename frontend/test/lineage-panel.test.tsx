import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LineagePanel } from "../components/lineage-panel";
import type { ExperimentArtifacts } from "../lib/types";
import { renderWithI18n } from "./render";

const artifacts: ExperimentArtifacts = {
  items: [
    {
      contentHash: "a".repeat(64),
      artifactType: "FactorComputationArtifact",
      schemaVersion: "factor-computation/v1",
      sizeBytes: 100,
      mediaType: "application/json",
      domainHash: "a".repeat(64),
    },
    {
      contentHash: "b".repeat(64),
      artifactType: "FactorValidationReport",
      schemaVersion: "factor-validation/v1",
      sizeBytes: 200,
      mediaType: "application/json",
      domainHash: "b".repeat(64),
    },
  ],
  lineage: [
    {
      edgeHash: "c".repeat(64),
      sourceArtifactHash: "a".repeat(64),
      targetArtifactHash: "b".repeat(64),
      relation: "VALIDATED_BY",
    },
  ],
};

describe("LineagePanel", () => {
  it("renders artifacts, edges and relation labels", () => {
    renderWithI18n(<LineagePanel artifacts={artifacts} />);

    expect(screen.getByText("证据血缘")).toBeDefined();
    expect(screen.getByText("由…校验")).toBeDefined();
    expect(screen.getByText("FactorValidationReport")).toBeDefined();
  });

  it("renders an explicit empty state when no artifacts exist", () => {
    renderWithI18n(<LineagePanel artifacts={null} />);

    expect(screen.getByText("暂无运行产物。")).toBeDefined();
  });

  it("renders a note when there are no lineage edges", () => {
    renderWithI18n(<LineagePanel artifacts={{ items: artifacts.items, lineage: [] }} />);

    expect(screen.getByText("本次运行未记录血缘边。")).toBeDefined();
  });
});

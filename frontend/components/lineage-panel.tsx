"use client";

import type { MessageKey } from "../lib/i18n";
import type { ExperimentArtifacts, LineageEdge } from "../lib/types";
import { useI18n } from "./i18n-provider";

interface LineagePanelProps {
  artifacts: ExperimentArtifacts | null;
}

const RELATION_KEYS: Record<string, MessageKey> = {
  VALIDATED_BY: "lin.validatedBy",
  DERIVED_FROM: "lin.derivedFrom",
};

function shortHash(hash: string): string {
  return hash.length > 12 ? `${hash.slice(0, 8)}…${hash.slice(-4)}` : hash;
}

export function LineagePanel({ artifacts }: LineagePanelProps) {
  const { t } = useI18n();
  if (!artifacts) {
    return (
      <section className="panel" aria-label={t("lin.aria")}>
        <div className="panel-heading">
          <div>
            <span className="eyebrow">{t("lin.emptyEyebrow")}</span>
            <h2>{t("lin.title")}</h2>
          </div>
        </div>
        <p className="muted">{t("lin.noArtifacts")}</p>
      </section>
    );
  }

  const byHash = new Map(artifacts.items.map((item) => [item.contentHash, item]));
  const edges = artifacts.lineage;

  return (
    <section className="panel" aria-label={t("lin.aria")}>
      <div className="panel-heading">
        <div>
          <span className="eyebrow">{t("lin.eyebrow")}</span>
          <h2>{t("lin.title")}</h2>
        </div>
        <span className="mono muted">
          {t("lin.count", { artifacts: artifacts.items.length, edges: edges.length })}
        </span>
      </div>

      {edges.length ? (
        <ol className="lineage-list">
          {edges.map((edge: LineageEdge) => (
            <li className="lineage-edge" key={edge.edgeHash}>
              <span className="mono">{shortHash(edge.sourceArtifactHash)}</span>
              <span className="lineage-relation">
                {RELATION_KEYS[edge.relation] ? t(RELATION_KEYS[edge.relation]) : edge.relation}
              </span>
              <span className="mono">{shortHash(edge.targetArtifactHash)}</span>
              <span className="lineage-type">
                {byHash.get(edge.targetArtifactHash)?.artifactType ?? t("lin.artifactFallback")}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">{t("lin.noEdges")}</p>
      )}
    </section>
  );
}

import type { ExperimentArtifacts, LineageEdge } from "../lib/types";

interface LineagePanelProps {
  artifacts: ExperimentArtifacts | null;
}

const RELATION_LABELS: Record<string, string> = {
  VALIDATED_BY: "validated by",
  DERIVED_FROM: "derived from",
};

function shortHash(hash: string): string {
  return hash.length > 12 ? `${hash.slice(0, 8)}…${hash.slice(-4)}` : hash;
}

export function LineagePanel({ artifacts }: LineagePanelProps) {
  if (!artifacts) {
    return (
      <section className="panel" aria-label="Evidence lineage">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">Lineage</span>
            <h2>Evidence lineage</h2>
          </div>
        </div>
        <p className="muted">No run artifacts yet.</p>
      </section>
    );
  }

  const byHash = new Map(artifacts.items.map((item) => [item.contentHash, item]));
  const edges = artifacts.lineage;

  return (
    <section className="panel" aria-label="Evidence lineage">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">FR-704 / Lineage</span>
          <h2>Evidence lineage</h2>
        </div>
        <span className="mono muted">
          {artifacts.items.length} artifacts · {edges.length} edges
        </span>
      </div>

      {edges.length ? (
        <ol className="lineage-list">
          {edges.map((edge: LineageEdge) => (
            <li className="lineage-edge" key={edge.edgeHash}>
              <span className="mono">{shortHash(edge.sourceArtifactHash)}</span>
              <span className="lineage-relation">
                {RELATION_LABELS[edge.relation] ?? edge.relation}
              </span>
              <span className="mono">{shortHash(edge.targetArtifactHash)}</span>
              <span className="lineage-type">
                {byHash.get(edge.targetArtifactHash)?.artifactType ?? "artifact"}
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">No lineage edges recorded for this run.</p>
      )}
    </section>
  );
}

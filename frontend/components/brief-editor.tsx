"use client";

import { useState } from "react";

import { quantApiClient } from "../lib/client";
import type { ResearchBrief } from "../lib/types";

export function BriefEditor({ initialBrief }: { initialBrief: ResearchBrief }) {
  const [brief, setBrief] = useState(initialBrief);
  const [saved, setSaved] = useState(false);
  const [freezing, setFreezing] = useState(false);
  const disabled = brief.status !== "DRAFT";

  async function save() {
    const result = await quantApiClient.updateBrief(brief.id, brief);
    setBrief(result);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2000);
  }

  async function freeze() {
    setFreezing(true);
    const result = await quantApiClient.freezeBrief(brief.id, brief.resourceVersion);
    setBrief(result);
    setFreezing(false);
  }

  return (
    <div className="brief-editor">
      <div className="brief-statusbar">
        <span className={`brief-state state-${brief.status.toLowerCase()}`}>
          {brief.status}
        </span>
        <span className="mono">version {brief.version} · rv {brief.resourceVersion}</span>
        {brief.contentHash ? <span className="mono">{brief.contentHash}</span> : null}
      </div>
      <div className="brief-grid">
        <label className="field field-wide">
          <span>Hypothesis</span>
          <textarea
            disabled={disabled}
            value={brief.hypothesis}
            onChange={(event) => setBrief({ ...brief, hypothesis: event.target.value })}
            rows={4}
          />
        </label>
        <label className="field field-wide">
          <span>Economic mechanism</span>
          <textarea
            disabled={disabled}
            value={brief.economicMechanism}
            onChange={(event) =>
              setBrief({ ...brief, economicMechanism: event.target.value })
            }
            rows={4}
          />
        </label>
        <label className="field">
          <span>Expected direction</span>
          <select
            disabled={disabled}
            value={brief.expectedDirection}
            onChange={(event) =>
              setBrief({
                ...brief,
                expectedDirection: event.target.value as ResearchBrief["expectedDirection"],
              })
            }
          >
            <option value="POSITIVE">Positive</option>
            <option value="NEGATIVE">Negative</option>
            <option value="NON_MONOTONIC">Non-monotonic</option>
            <option value="UNKNOWN">Unknown</option>
          </select>
        </label>
        <label className="field">
          <span>Allowed data domains</span>
          <textarea
            disabled={disabled}
            value={brief.allowedDataDomains.join("\n")}
            onChange={(event) =>
              setBrief({
                ...brief,
                allowedDataDomains: event.target.value.split("\n").filter(Boolean),
              })
            }
            rows={4}
          />
        </label>
        <label className="field">
          <span>Falsification conditions</span>
          <textarea
            disabled={disabled}
            value={brief.falsificationConditions.join("\n")}
            onChange={(event) =>
              setBrief({
                ...brief,
                falsificationConditions: event.target.value.split("\n").filter(Boolean),
              })
            }
            rows={4}
          />
        </label>
        <label className="field">
          <span>Constraints</span>
          <textarea
            disabled={disabled}
            value={brief.constraints.join("\n")}
            onChange={(event) =>
              setBrief({
                ...brief,
                constraints: event.target.value.split("\n").filter(Boolean),
              })
            }
            rows={4}
          />
        </label>
      </div>
      <div className="brief-actions">
        <button className="button button-secondary" type="button" disabled={disabled} onClick={save}>
          {saved ? "Draft saved" : "Save draft"}
        </button>
        <button
          className="button button-primary"
          type="button"
          disabled={disabled || freezing}
          onClick={freeze}
        >
          {freezing ? "Freezing…" : "Freeze brief version"}
        </button>
        <span className="form-footnote">
          Freeze creates an immutable content hash. Further edits require a new version.
        </span>
      </div>
    </div>
  );
}

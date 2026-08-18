"use client";

import { useState } from "react";

import { quantApiClient } from "../lib/client";
import type { ResearchBrief } from "../lib/types";
import { RESEARCH_TEMPLATES, type ResearchTemplate } from "../lib/research-templates";
import { useI18n } from "./i18n-provider";

export function BriefEditor({ initialBrief }: { initialBrief: ResearchBrief }) {
  const { t } = useI18n();
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

  function applyTemplate(template: ResearchTemplate) {
    setBrief({
      ...brief,
      hypothesis: template.brief.hypothesis,
      economicMechanism: template.brief.economicMechanism,
      expectedDirection: template.brief.expectedDirection,
      falsificationConditions: template.brief.falsificationConditions,
      constraints: template.brief.constraints,
      uncertainties: template.brief.uncertainties,
    });
    setSaved(false);
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
          {t(`briefStatus.${brief.status}`)}
        </span>
        <span className="mono">
          {t("brief.version", {
            version: brief.version,
            resourceVersion: brief.resourceVersion,
          })}
        </span>
        {brief.contentHash ? <span className="mono">{brief.contentHash}</span> : null}
      </div>
      <div className="brief-template-row">
        <span className="eyebrow">用预置模板填充</span>
        <div className="brief-template-buttons">
          {RESEARCH_TEMPLATES.map((template) => (
            <button
              key={template.id}
              type="button"
              className="button button-secondary button-small"
              disabled={disabled}
              onClick={() => applyTemplate(template)}
            >
              {template.name}
            </button>
          ))}
        </div>
      </div>
      <div className="brief-grid">
        <label className="field field-wide">
          <span>{t("brief.hypothesis")}</span>
          <textarea
            disabled={disabled}
            value={brief.hypothesis}
            onChange={(event) => setBrief({ ...brief, hypothesis: event.target.value })}
            rows={4}
          />
        </label>
        <label className="field field-wide">
          <span>{t("brief.mechanism")}</span>
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
          <span>{t("brief.direction")}</span>
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
            <option value="POSITIVE">{t("brief.direction.positive")}</option>
            <option value="NEGATIVE">{t("brief.direction.negative")}</option>
            <option value="NON_MONOTONIC">{t("brief.direction.nonMonotonic")}</option>
            <option value="UNKNOWN">{t("brief.direction.unknown")}</option>
          </select>
        </label>
        <label className="field">
          <span>{t("brief.domains")}</span>
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
          <span>{t("brief.falsification")}</span>
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
          <span>{t("brief.constraints")}</span>
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
          {saved ? t("brief.saved") : t("brief.save")}
        </button>
        <button
          className="button button-primary"
          type="button"
          disabled={disabled || freezing}
          onClick={freeze}
        >
          {freezing ? t("brief.freezing") : t("brief.freeze")}
        </button>
        <span className="form-footnote">
          {t("brief.footnote")}
        </span>
      </div>
    </div>
  );
}

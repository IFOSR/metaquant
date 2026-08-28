"use client";

import { useState, type ReactNode } from "react";

import { useI18n } from "./i18n-provider";

export function AuditDeepZone({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  return (
    <section className="deep-zone">
      <button
        type="button"
        className="deep-zone-toggle"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span>{t("detail.deepZone")}</span>
        <span className="mono" aria-hidden="true">
          {open ? "−" : "+"}
        </span>
      </button>
      {open ? (
        <div className="deep-zone-body">
          <p className="muted deep-zone-hint">{t("detail.deepZoneHint")}</p>
          {children}
        </div>
      ) : null}
    </section>
  );
}

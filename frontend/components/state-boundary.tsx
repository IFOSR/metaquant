"use client";

import type { ReactNode } from "react";

import type { MessageKey } from "../lib/i18n";
import { useI18n } from "./i18n-provider";

type BoundaryState =
  | "loading"
  | "empty"
  | "error"
  | "permission"
  | "stale"
  | "long-running";

const STATE_LABEL_KEYS: Record<BoundaryState, MessageKey> = {
  loading: "state.loading",
  empty: "state.empty",
  error: "state.error",
  permission: "state.permission",
  stale: "state.stale",
  "long-running": "state.long-running",
};

interface StateBoundaryProps {
  state: BoundaryState;
  title: string;
  detail: string;
  children?: ReactNode;
  actionLabel?: string;
  onAction?: () => void;
}

export function StateBoundary({
  state,
  title,
  detail,
  children,
  actionLabel,
  onAction,
}: StateBoundaryProps) {
  const { t } = useI18n();
  const isReadOnly = state === "stale" || state === "permission";
  return (
    <section
      className={`state-boundary state-${state}`}
      aria-live={state === "loading" ? "polite" : "assertive"}
      role={state === "loading" ? undefined : "status"}
    >
      <div className="state-mark" aria-hidden="true">
        {state === "loading" ? "…" : state === "error" ? "!" : "·"}
      </div>
      <div>
        <div className="eyebrow">{t(STATE_LABEL_KEYS[state])}</div>
        <h2>{title}</h2>
        <p>{detail}</p>
        {isReadOnly ? (
          <span className="read-only-label">{t("state.readOnly")}</span>
        ) : null}
        {children}
        {!isReadOnly && actionLabel && onAction ? (
          <button className="button button-secondary" type="button" onClick={onAction}>
            {actionLabel}
          </button>
        ) : null}
      </div>
    </section>
  );
}

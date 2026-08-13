"use client";

import type { ReactNode } from "react";

type BoundaryState =
  | "loading"
  | "empty"
  | "error"
  | "permission"
  | "stale"
  | "long-running";

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
        <div className="eyebrow">{state.replace("-", " ")}</div>
        <h2>{title}</h2>
        <p>{detail}</p>
        {isReadOnly ? <span className="read-only-label">Read-only mode</span> : null}
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

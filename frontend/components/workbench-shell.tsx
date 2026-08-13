"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { getVisibleNavigation, MARKET_LABELS } from "../lib/domain";
import { quantApiClient } from "../lib/client";
import type { MarketId, Session } from "../lib/types";
import { StateBoundary } from "./state-boundary";

export function WorkbenchShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [session, setSession] = useState<Session | null>(null);
  const [market, setMarket] = useState<MarketId>("CN_COMMODITY_FUTURES");

  useEffect(() => {
    void quantApiClient.getSession().then(setSession);
  }, []);

  if (!session) {
    return (
      <main className="shell-loading">
        <StateBoundary
          state="loading"
          title="Loading session"
          detail="Resolving actor, environment, market scope, and capabilities."
        />
      </main>
    );
  }

  const visibleNavigation = getVisibleNavigation(session.capabilities);
  return (
    <div className="app-shell">
      <header className="topbar">
        <Link className="wordmark" href="/">
          <span className="wordmark-kicker">QUANT / CONTROL PLANE</span>
          <span className="wordmark-title">Research desk</span>
        </Link>
        <div className="topbar-context">
          <label className="context-select">
            <span>Environment</span>
            <select aria-label="Environment" defaultValue="RESEARCH">
              <option>RESEARCH</option>
              <option disabled>PAPER / gated</option>
              <option disabled>LIVE / gated</option>
            </select>
          </label>
          <label className="context-select">
            <span>Market</span>
            <select
              aria-label="Market"
              value={market}
              onChange={(event) => setMarket(event.target.value as MarketId)}
            >
              {session.markets.map((marketId) => (
                <option key={marketId} value={marketId}>
                  {MARKET_LABELS[marketId]}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="actor-context">
          <span className="online-dot" aria-hidden="true" />
          <span>{session.actor.displayName}</span>
          <span className="mono">OIDC / scoped</span>
        </div>
      </header>
      <div className="shell-body">
        <aside className="sidebar" aria-label="Primary navigation">
          <div className="sidebar-intro">
            <span className="eyebrow">Evidence first</span>
            <p>Every conclusion carries its snapshot, policy and lineage.</p>
          </div>
          <nav className="nav-list">
            {visibleNavigation.map((item) => (
              <Link
                className={`nav-link ${pathname === item.href ? "is-active" : ""}`}
                href={item.href}
                key={item.href}
              >
                <span className="nav-marker">{item.marker}</span>
                <span>{item.label}</span>
              </Link>
            ))}
          </nav>
          <div className="sidebar-foot">
            <span className="eyebrow">Current scope</span>
            <strong>{MARKET_LABELS[market]}</strong>
            <span className="mono">formal / 1d only</span>
          </div>
        </aside>
        <main className="main-content">
          <div className="evidence-rail" aria-hidden="true">
            <span>ENV / RESEARCH</span>
            <span>MARKET / {market}</span>
            <span>POLICY / G1</span>
          </div>
          <div className="content-wrap">{children}</div>
        </main>
      </div>
    </div>
  );
}

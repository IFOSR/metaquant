import { HttpQuantApiClient, type QuantApiClient } from "./api";
import { mockClient } from "./mock-client";
import type { Session } from "./types";

const localSession: Session = {
  actor: { id: "local-researcher", displayName: "Local Researcher" },
  roles: ["Researcher"],
  capabilities: [
    "research.jobs.read",
    "research.jobs.write",
    "research.briefs.write",
    "research.briefs.freeze",
    "research.experiments.read",
    "strategy.read",
    "execution.read",
    "approval.read",
  ],
  environments: ["RESEARCH", "PAPER", "LIVE"],
  markets: ["CN_A", "CN_COMMODITY_FUTURES"],
};

function buildClient(): QuantApiClient {
  if (process.env.NEXT_PUBLIC_QUANT_API_MODE !== "http") return mockClient;

  if (typeof window === "undefined") {
    const upstream = process.env.QUANT_API_UPSTREAM_URL;
    const accessToken = process.env.QUANT_API_ACCESS_TOKEN;
    if (!upstream || !accessToken) {
      throw new Error(
        "HTTP API mode requires QUANT_API_UPSTREAM_URL and " +
          "QUANT_API_ACCESS_TOKEN on the Next.js server.",
      );
    }
    return new HttpQuantApiClient({
      baseUrl: `${upstream.replace(/\/$/, "")}/v1`,
      accessToken,
      session: localSession,
    });
  }

  return new HttpQuantApiClient({
    baseUrl: "/api/quant/v1",
    accessToken: readClientToken() ?? undefined,
    session: localSession,
  });
}

function readClientToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("quant-access-token");
}

export const quantApiClient = buildClient();

import { HttpQuantApiClient, type QuantApiClient } from "./api";
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
  if (typeof window === "undefined") {
    const upstream = process.env.QUANT_API_UPSTREAM_URL;
    const accessToken = process.env.QUANT_API_ACCESS_TOKEN;
    if (!upstream || !accessToken) {
      throw new Error(
        "The Next.js server requires QUANT_API_UPSTREAM_URL and " +
          "QUANT_API_ACCESS_TOKEN to reach the Quant API.",
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
    session: localSession,
  });
}

export const quantApiClient = buildClient();

import type {
  Capability,
  CreateResearchJobInput,
  MarketId,
  Session,
} from "./types";

export const MARKET_LABELS: Record<MarketId, string> = {
  CN_A: "CN A-share",
  CN_COMMODITY_FUTURES: "CN commodity futures",
};

export const MARKET_NOTES: Record<MarketId, string> = {
  CN_A: "Shanghai + Shenzhen main board · T+1 execution",
  CN_COMMODITY_FUTURES:
    "Actual contracts · settlement-aware · immutable roll policy",
};

export const navigation = [
  {
    label: "Overview",
    href: "/",
    required: "research.jobs.read" as Capability,
    marker: "00",
  },
  {
    label: "Research jobs",
    href: "/research/jobs",
    required: "research.jobs.read" as Capability,
    marker: "01",
  },
  {
    label: "New research",
    href: "/research/jobs/new",
    required: "research.jobs.write" as Capability,
    marker: "02",
  },
  {
    label: "Strategy",
    href: "/strategy",
    required: "strategy.read" as Capability,
    marker: "03",
  },
  {
    label: "Execution",
    href: "/execution",
    required: "execution.read" as Capability,
    marker: "04",
  },
] as const;

export function getVisibleNavigation(capabilities: Capability[]) {
  return navigation.filter((item) => capabilities.includes(item.required));
}

export interface ValidationError {
  field: keyof CreateResearchJobInput;
  message: string;
}

export function validateResearchJob(input: CreateResearchJobInput): {
  valid: boolean;
  errors: ValidationError[];
} {
  const errors: ValidationError[] = [];
  const required: Array<[keyof CreateResearchJobInput, string]> = [
    ["universeRef", "Universe reference is required."],
    ["decisionClock", "Decision clock is required."],
    ["tradeClock", "Trade clock is required."],
    ["horizon", "Horizon is required."],
    ["briefVersionId", "A research brief draft is required."],
  ];

  required.forEach(([field, message]) => {
    if (!String(input[field]).trim()) errors.push({ field, message });
  });

  if (input.frequency !== "1d") {
    errors.push({
      field: "frequency",
      message: "Formal research is enabled only at 1d in G1.",
    });
  }

  if (input.market === "CN_COMMODITY_FUTURES") {
    if (!input.settlementClock.trim()) {
      errors.push({
        field: "settlementClock",
        message: "Settlement clock is required for commodity futures.",
      });
    }
    if (!input.exchangeScope.length) {
      errors.push({
        field: "exchangeScope",
        message: "Select at least one exchange scope.",
      });
    }
    if (input.contractSelection !== "ACTUAL_CONTRACTS_ONLY") {
      errors.push({
        field: "contractSelection",
        message: "Formal research must use actual contracts.",
      });
    }
    if (!input.rollPolicy.trim()) {
      errors.push({
        field: "rollPolicy",
        message: "An immutable roll policy is required.",
      });
    }
  }

  return { valid: errors.length === 0, errors };
}

export function hasCapability(session: Session, capability: Capability) {
  return session.capabilities.includes(capability);
}

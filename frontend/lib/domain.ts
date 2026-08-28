import type { MessageKey } from "./i18n";
import type {
  Capability,
  CreateResearchJobInput,
  Environment,
  ExperimentRunState,
  ExperimentSpecState,
  MarketId,
  Session,
} from "./types";

export const MARKET_LABEL_KEYS: Record<MarketId, MessageKey> = {
  CN_A: "market.cnA.label",
  CN_COMMODITY_FUTURES: "market.cnFutures.label",
};

export const RESEARCH_KIND_LABEL_KEYS: Record<"factor" | "strategy", MessageKey> = {
  factor: "research.kind.factor",
  strategy: "research.kind.strategy",
};

export const RESEARCH_STAGE_LABEL_KEYS: Record<
  "CREATING" | "READY" | "CODE_TESTED" | "BACKTESTED" | "PAPER_LINKED",
  MessageKey
> = {
  CREATING: "research.stage.creating",
  READY: "research.stage.ready",
  CODE_TESTED: "research.stage.codeTested",
  BACKTESTED: "research.stage.backtested",
  PAPER_LINKED: "research.stage.paperLinked",
};

// 正式研究任务（因子流水线）状态 → 统一「研究」生命周期的粗粒度阶段映射。
export function factorStageFromState(state: string) {
  if (state === "SUCCEEDED") return "BACKTESTED";
  if (state === "RUNNING" || state === "READY") return "READY";
  return "CREATING";
}

export const MARKET_NOTE_KEYS: Record<MarketId, MessageKey> = {
  CN_A: "market.cnA.note",
  CN_COMMODITY_FUTURES: "market.cnFutures.note",
};

export const ENV_LABEL_KEYS: Record<Environment, MessageKey> = {
  RESEARCH: "env.RESEARCH",
  PAPER: "env.PAPER",
  LIVE: "env.LIVE",
};

export const EXPERIMENT_SPEC_STATE_KEYS: Record<ExperimentSpecState, MessageKey> = {
  DRAFT: "expState.DRAFT",
  PREREGISTERED: "expState.PREREGISTERED",
};

export const EXPERIMENT_RUN_STATE_KEYS: Record<ExperimentRunState, MessageKey> = {
  QUEUED: "runState.QUEUED",
  RUNNING: "runState.RUNNING",
  SUCCEEDED: "runState.SUCCEEDED",
  FAILED_RETRYABLE: "runState.FAILED_RETRYABLE",
  FAILED_TERMINAL: "runState.FAILED_TERMINAL",
  BLOCKED_POLICY: "runState.BLOCKED_POLICY",
  QUARANTINED: "runState.QUARANTINED",
  NON_REPRODUCIBLE: "runState.NON_REPRODUCIBLE",
  CANCELLED: "runState.CANCELLED",
};

export const DISPOSITION_KEYS: Record<string, MessageKey> = {
  PROMOTE: "disposition.PROMOTE",
  REJECT: "disposition.REJECT",
  QUARANTINE: "disposition.QUARANTINE",
};

// Pipeline stages are backend data; map the known ones and fall back to the raw value.
export const STAGE_LABEL_KEYS: Record<string, MessageKey> = {
  RESEARCH_INTAKE: "stage.researchIntake",
  BRIEF_FROZEN: "stage.briefFrozen",
};

export function stageLabelKey(stage: string): MessageKey | null {
  return STAGE_LABEL_KEYS[stage] ?? null;
}

export const navigation = [
  {
    labelKey: "nav.overview" as MessageKey,
    href: "/",
    required: "research.jobs.read" as Capability,
    marker: "00",
  },
  {
    labelKey: "nav.newResearch" as MessageKey,
    href: "/research/new",
    required: "research.jobs.write" as Capability,
    marker: "01",
  },
  {
    labelKey: "nav.backtest" as MessageKey,
    href: "/backtest",
    required: "strategy.read" as Capability,
    marker: "02",
  },
  {
    labelKey: "nav.paper" as MessageKey,
    href: "/paper",
    required: "paper.read" as Capability,
    marker: "03",
  },
] as const;

export function getVisibleNavigation(capabilities: Capability[]) {
  return navigation.filter((item) => capabilities.includes(item.required));
}

export interface ValidationError {
  field: keyof CreateResearchJobInput;
  message: MessageKey;
}

export function validateResearchJob(input: CreateResearchJobInput): {
  valid: boolean;
  errors: ValidationError[];
} {
  const errors: ValidationError[] = [];
  const required: Array<[keyof CreateResearchJobInput, MessageKey]> = [
    ["universeRef", "validation.universeRequired"],
    ["decisionClock", "validation.decisionClockRequired"],
    ["tradeClock", "validation.tradeClockRequired"],
    ["horizon", "validation.horizonRequired"],
    ["briefVersionId", "validation.briefRequired"],
  ];

  required.forEach(([field, message]) => {
    if (!String(input[field]).trim()) errors.push({ field, message });
  });

  if (input.market === "CN_COMMODITY_FUTURES") {
    if (!input.settlementClock.trim()) {
      errors.push({
        field: "settlementClock",
        message: "validation.settlementRequired",
      });
    }
    if (!input.exchangeScope.length) {
      errors.push({
        field: "exchangeScope",
        message: "validation.exchangeRequired",
      });
    }
    if (input.contractSelection !== "ACTUAL_CONTRACTS_ONLY") {
      errors.push({
        field: "contractSelection",
        message: "validation.actualContractsRequired",
      });
    }
    if (!input.rollPolicy.trim()) {
      errors.push({
        field: "rollPolicy",
        message: "validation.rollPolicyRequired",
      });
    }
  }

  return { valid: errors.length === 0, errors };
}

export function hasCapability(session: Session, capability: Capability) {
  return session.capabilities.includes(capability);
}

export type MarketId = "CN_A" | "CN_COMMODITY_FUTURES";
export type Environment = "RESEARCH" | "PAPER" | "LIVE";
export type ResearchJobState =
  | "DRAFT"
  | "READY"
  | "RUNNING"
  | "WAITING_INPUT"
  | "BLOCKED_POLICY"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELLED"
  | "ARCHIVED";
export type FrequencyId = "1d" | "5m";
export type ExperimentSpecState = "DRAFT" | "PREREGISTERED";
export type ExperimentRunState =
  | "QUEUED"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED_RETRYABLE"
  | "FAILED_TERMINAL"
  | "BLOCKED_POLICY"
  | "QUARANTINED"
  | "NON_REPRODUCIBLE"
  | "CANCELLED";
export type Capability =
  | "research.jobs.read"
  | "research.jobs.write"
  | "research.briefs.write"
  | "research.briefs.freeze"
  | "research.experiments.read"
  | "research.experiments.preregister"
  | "research.experiments.run"
  | "research.jobs.propose"
  | "strategy.read"
  | "execution.read"
  | "approval.read";

export interface Session {
  actor: { id: string; displayName: string };
  roles: string[];
  capabilities: Capability[];
  environments: Environment[];
  markets: MarketId[];
}

export interface Budget {
  candidateLimit: number;
  llmTokenLimit: number;
  cpuHours: number;
  wallClockMinutes: number;
}

export interface ResearchJob {
  id: string;
  version: string;
  title: string;
  market: MarketId;
  environment: Environment;
  state: ResearchJobState;
  owner: string;
  currentStage: string | null;
  budget: Budget;
  budgetUsed: {
    candidates: number;
    llmTokens: number;
    cpuHours: number;
    wallClockMinutes: number;
  } | null;
  latestAttempt: {
    attempt: number;
    state: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED" | "TIMED_OUT";
    startedAt: string;
    heartbeatAt: string;
  } | null;
  snapshotRefs: string[];
  policyVersion: string | null;
  runFingerprint: string | null;
  experimentId: string | null;
  freshness: {
    asOf: string;
    isStale: boolean;
    staleReason: string | null;
  } | null;
  blockers: Array<{
    code: string;
    title: string;
    detail: string;
    responsibility: string;
  }>;
  allowedActions: string[];
  updatedAt: string;
}

export interface ResearchBrief {
  id: string;
  jobId: string;
  version: number;
  resourceVersion: number;
  status: "DRAFT" | "FROZEN" | "SUPERSEDED";
  hypothesis: string;
  economicMechanism: string;
  expectedDirection: "POSITIVE" | "NEGATIVE" | "NON_MONOTONIC" | "UNKNOWN";
  falsificationConditions: string[];
  allowedDataDomains: string[];
  forbiddenDataDomains: string[];
  constraints: string[];
  evidenceRefIds: string[];
  uncertainties: string[];
  contentHash: string | null;
  createdAt: string;
  createdBy: string;
  frozenAt: string | null;
}

export interface CreateResearchJobInput {
  market: MarketId;
  universeRef: string;
  frequency: FrequencyId;
  decisionClock: string;
  tradeClock: string;
  settlementClock: string;
  exchangeScope: string[];
  contractSelection: string;
  rollPolicy: string;
  horizon: string;
  briefVersionId: string;
}

export interface ExperimentResourceBudget {
  cpuSeconds: number;
  wallClockSeconds: number;
  memoryMb: number;
  maxObservations: number;
}

export interface PreregisterExperimentInput {
  researchJobId: string;
  briefVersionId: string;
  decisionTime: string;
  randomSeed: number;
  resourceBudget: ExperimentResourceBudget;
  factorIr: Record<string, unknown>;
  snapshotId: string;
  snapshotManifestHash: string;
}

export interface Experiment {
  id: string;
  projectId: string;
  researchJobId: string;
  briefVersionId: string;
  market: MarketId;
  state: ExperimentSpecState;
  resourceVersion: number;
  specHash: string;
  factorIrHash: string;
  snapshotId: string;
  snapshotManifestHash: string;
  latestRunId: string | null;
  createdAt: string;
  createdBy: string;
}

export interface ValidationSummary {
  observationCount: number;
  finiteCount: number;
  missingCount: number;
  coverageRatio: number;
  minimum: number | null;
  maximum: number | null;
  mean: number | null;
}

export interface InvarianceEvidence {
  futureTruncationPassed: boolean;
  sentinelIsolationPassed: boolean;
  baselineOutputHash: string;
  futureTruncationOutputHash: string;
  sentinelIsolationOutputHash: string;
}

export interface ExperimentRun {
  id: string;
  experimentId: string;
  market: MarketId;
  state: ExperimentRunState;
  runFingerprint: string;
  attemptCount: number;
  validationSummary: ValidationSummary | null;
  invariance: InvarianceEvidence | null;
  createdAt: string;
  updatedAt: string;
}

export interface ExperimentArtifact {
  contentHash: string;
  artifactType: string;
  schemaVersion: string;
  sizeBytes: number;
  mediaType: string;
  domainHash: string;
}

export interface LineageEdge {
  edgeHash: string;
  sourceArtifactHash: string;
  targetArtifactHash: string;
  relation: string;
}

export interface ExperimentArtifacts {
  items: ExperimentArtifact[];
  lineage: LineageEdge[];
}

export interface FactorValidationReport {
  policyId: string;
  policyHash: string;
  labelId: string;
  labelHash: string;
  factorArtifactHash: string;
  dataQuality: {
    observationCount: number;
    finiteCount: number;
    coverageRatio: number;
    constantRatio: number;
  };
  predictivePower: {
    meanPearsonIc: number | null;
    meanRankIc: number | null;
    icir: number | null;
    nwT: number | null;
    icDecay: Array<{ horizon: number; meanIc: number | null }>;
    quantileReturns: Array<{ quantile: number; meanReturn: number | null }>;
    topBottomSpread: number | null;
    monotonic: boolean | null;
  };
}

export interface IndependenceSummary {
  runId: string;
  outputHash: string;
  baselineIc: number | null;
  orthogonalizedIc: number | null;
  maxAbsCorrelation: number | null;
  replicatedRiskFactor: boolean;
  pairwise: Array<{
    factorIrHash: string;
    pearson: number | null;
    spearman: number | null;
  }>;
}

export interface PromotionSummary {
  runId: string;
  outputHash: string;
  factorIrHash: string;
  policyId: string;
  disposition: "PROMOTE" | "REJECT" | "QUARANTINE";
  totalScore: number | null;
  gates: Array<{
    name: string;
    passed: boolean;
    observed: number | null;
    threshold: number | null;
    note: string | null;
  }>;
  componentScores: Array<[string, number]>;
  rationale: string;
}

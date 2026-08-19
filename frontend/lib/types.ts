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
export type FrequencyId = "1d" | "1m" | "5m" | "15m" | "30m" | "60m";
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
  environment: Environment;
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

export interface BriefDraftInput {
  hypothesis: string;
  economicMechanism: string;
  expectedDirection: "POSITIVE" | "NEGATIVE" | "NON_MONOTONIC" | "UNKNOWN";
  falsificationConditions: string[];
  allowedDataDomains: string[];
  forbiddenDataDomains: string[];
  constraints: string[];
  evidenceRefIds: string[];
  uncertainties: string[];
}

export interface FactorExtractionResult {
  brief: BriefDraftInput;
  factorIr: Record<string, unknown>;
  explanation: string;
}

export interface FromPaperPipelineResult {
  jobId: string;
  briefId: string;
  experimentId: string;
  brief: BriefDraftInput;
  factorIr: Record<string, unknown>;
  explanation: string;
}

export interface FormalSnapshotInfo {
  snapshotId: string;
  manifestHash: string;
  market: string | null;
  universeRef: string | null;
  frequency: string | null;
  decisionClock: string | null;
  tradeClock: string | null;
  frozenAt: string | null;
  instruments: string[] | null;
}

export interface ProvisionInput {
  universeRef: string;
  explicitInstruments: string[];
  exchangeScope: string[];
  start: string;
  end: string;
}

export interface ProvisionResult {
  snapshotId: string;
  snapshotManifestHash: string;
  decisionTime: string;
  instrumentCount: number;
  rowCount: number;
  labelSnapshotId: string;
  labelSnapshotManifestHash: string;
}

export interface ProvisioningTaskStatus {
  taskId: string;
  status: "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED";
  error: string | null;
  snapshotId: string | null;
  snapshotManifestHash: string | null;
  decisionTime: string | null;
  instrumentCount: number | null;
  rowCount: number | null;
  labelSnapshotId: string | null;
  labelSnapshotManifestHash: string | null;
  instruments: string[] | null;
}

export interface LabelSnapshotInfo {
  snapshotId: string;
  manifestHash: string;
  market: string;
  horizon: number;
  labelId: string;
  decisionTime: string | null;
}

export interface FactorIrInput {
  alias: string;
  fieldRef: string;
  dataType: string;
  unit: string;
  availableTimeRule: string;
}

export interface FactorIrExpression {
  ref?: string;
  literal?: number | boolean;
  unit?: string;
  op?: string;
  args?: FactorIrExpression[];
  params?: Record<string, unknown>;
}

export interface FactorIR {
  factorId: string;
  version: string;
  marketScope: {
    market: string;
    frequency: string;
    universeRef: string;
  };
  decisionClock: {
    signalTime: string;
    earliestTradeTime: string;
  };
  inputs: FactorIrInput[];
  expression: FactorIrExpression;
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
  factorIr: FactorIR | null;
  decisionTime: string | null;
  randomSeed: number | null;
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

export interface AlphaPoolFactor {
  factorIrHash: string;
  factorId: string | null;
  instruments: string[];
  dataStart: string | null;
  dataEnd: string | null;
  direction: string;
  market: MarketId;
  universe: string;
  horizon: number;
  policyId: string;
  riskPremium: boolean;
  lifecycleState: string;
  oosIc: number | null;
}

export interface BacktestMetrics {
  totalReturn: number;
  sharpe: number | null;
  maxDrawdown: number;
  tradeCount: number;
}

export interface BacktestTrade {
  time: string;
  instrumentId: string;
  side: string;
  quantity: number;
  price: number;
}

export interface BacktestPosition {
  instrumentId: string;
  entry: string;
  peakQty: number;
  avgPxOpen: number;
  avgPxClose: number | null;
  realizedPnl: number;
  openedAt: string;
  closedAt: string | null;
}

export interface BacktestResult {
  factorIrHash: string;
  instrumentIds: string[];
  start: string;
  end: string;
  frequency: string;
  dataSource: "snapshot" | "realtime";
  artifactClass: string | null;
  initialCash: number;
  lotSize: number;
  grossOfFees: boolean;
  metrics: BacktestMetrics;
  equityCurve: Array<{ date: string; equity: number }>;
  trades: BacktestTrade[];
  positions: BacktestPosition[];
  backtestHash: string;
}

export interface RunBacktestInput {
  factorIrHash: string;
  instrumentIds?: string[];
  startDate?: string;
  endDate?: string;
  frequency?: "1d" | "5m";
  dataSource?: "snapshot" | "realtime";
  lotSize?: number;
  initialCash?: number;
}

export interface MarketDataCoverageEntry {
  instrumentId: string;
  fieldPrefix: string;
  sourceId: string;
  licenseTag: string;
  artifactClass: string;
  rowCount: number;
  firstEvent: string;
  lastEvent: string;
}

export interface ExecutionState {
  stateId: string;
  killSwitchState: "ARMED" | "TRIPPED";
  trippedBy: string | null;
  trippedAt: string | null;
  reason: string | null;
  shadowPositions: Record<string, number>;
  paperPositions: Record<string, number>;
}

// ── 因子构建（研报 → 可执行模型） ─────────────────────────────────────

export type FactorArchitecture = "MLP" | "LSTM" | "TRANSFORMER" | "LINEAR";
export type SampleWeighting = "EQUAL" | "INVERSE_SIZE" | "CAP_WEIGHTED";

export interface FactorBuildSpec {
  factor_id: string;
  factor_name: string;
  market: MarketId;
  universe_ref: string;
  frequency?: string;
  inputs: string[];
  label: {
    name: string;
    price_field: string;
    horizon: number;
    return_type?: string;
    style_neutralize?: string[];
  };
  architecture: FactorArchitecture;
  style_neutralize: string[];
  sample_weighting: SampleWeighting;
  expected_direction: string;
  hyperparameters?: Record<string, unknown>;
}

export interface FactorBuildSpecExtraction {
  spec: FactorBuildSpec;
  spec_hash: string;
}

export interface FactorCodeBundleDraft {
  files: Record<string, string>;
  manifest: Record<string, unknown>;
  bundle_hash: string;
  smoke?: { exit_code: number; timed_out: boolean; stderr: string };
}

export interface FactorBuildSpecRecord {
  id: string;
  spec_hash: string;
  state: "DRAFT" | "FROZEN";
  resource_version: number;
  spec: FactorBuildSpec;
}

export interface FactorBuildRunRecord {
  id: string;
  spec_hash: string;
  bundle_hash: string;
  kind: "SMOKE" | "TRAIN" | "INFER";
  state: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";
  weights_hash: string | null;
  factor_values_hash: string | null;
  error: string | null;
}

export interface ModelFactorValidationReport {
  observation_count: number;
  finite_count: number;
  coverage_ratio: number;
  cross_sections: number;
  pearson_ic: number | null;
  rank_ic: number | null;
  icir: number | null;
  output_hash: string;
}

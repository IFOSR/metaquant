import type {
  AgentConfigState,
  AgentDescriptor,
  AgentId,
  AgentModelInfo,
  AgentProviderInfo,
  AlphaPoolFactor,
  BacktestResult,
  BriefDraftInput,
  Capability,
  CreateResearchJobInput,
  Environment,
  ExecutionState,
  Experiment,
  ExperimentArtifacts,
  ExperimentRun,
  FactorIR,
  FactorValidationReport,
  FormalSnapshotInfo,
  IndependenceSummary,
  LabelSnapshotInfo,
  MarketDataCoverageEntry,
  MarketId,
  PaperAccount,
  PaperDriftReport,
  PaperEquityRow,
  PaperFill,
  PaperOrder,
  PaperPosition,
  PaperRunStatus,
  PreregisterExperimentInput,
  PromotionSummary,
  ProvisionInput,
  ProvisionResult,
  ProvisioningTaskStatus,
  ResearchBrief,
  ResearchJob,
  RunBacktestInput,
  Session,
  StrategyBacktestResult,
  StrategyAttachment,
  StrategyCodeTestResult,
  StrategyDataStatus,
  StrategyDraft,
  StrategyFrequency,
  StrategyProvisionResult,
  FactorExtractionResult,
  FromPaperPipelineResult,
  FactorBuildSpec,
  FactorBuildSpecExtraction,
  FactorBuildSpecRecord,
  FactorBuildRunRecord,
  FactorCodeBundleDraft,
  ModelFactorValidationReport,
} from "./types";

type Fetcher = typeof fetch;

interface ApiList<T> {
  items: T[];
  next_cursor: string | null;
}

interface ApiCommandReceipt {
  command_id: string;
  status: "ACCEPTED";
  resource_id: string;
  submitted_at: string;
}

interface ApiFormalSnapshot {
  snapshot_id: string;
  manifest_hash: string;
  market?: string | null;
  universe_ref?: string | null;
  frequency?: string | null;
  decision_clock?: string | null;
  trade_clock?: string | null;
  frozen_at?: string | null;
  instruments?: string[] | null;
}

interface ApiLabelSnapshot {
  snapshot_id: string;
  manifest_hash: string;
  market: string;
  horizon: number;
  label_id: string;
  decision_time: string | null;
}

interface ApiProvisionResult {
  snapshot_id: string;
  snapshot_manifest_hash: string;
  decision_time: string;
  instrument_count: number;
  row_count: number;
  label_snapshot_id: string;
  label_snapshot_manifest_hash: string;
}

interface ApiProvisioningTaskStatus {
  task_id: string;
  status: string;
  error: string | null;
  snapshot_id: string | null;
  snapshot_manifest_hash: string | null;
  decision_time: string | null;
  instrument_count: number | null;
  row_count: number | null;
  label_snapshot_id: string | null;
  label_snapshot_manifest_hash: string | null;
  instruments: string[] | null;
}

interface ApiBudget {
  candidate_limit?: number;
  llm_token_limit?: number;
  cpu_hours?: number;
  wall_clock_minutes?: number;
}

interface ApiResearchJob {
  id: string;
  resource_version?: number;
  version?: string;
  title: string;
  market: ResearchJob["market"];
  environment: "RESEARCH";
  state: ResearchJob["state"];
  owner: string;
  current_stage?: string;
  budget: ApiBudget;
  budget_used?: Partial<{
    candidates: number;
    llm_tokens: number;
    cpu_hours: number;
    wall_clock_minutes: number;
  }>;
  latest_attempt?: {
    attempt: number;
    state: NonNullable<ResearchJob["latestAttempt"]>["state"];
    started_at: string;
    heartbeat_at: string;
  } | null;
  snapshot_refs?: string[];
  policy_version?: string;
  run_fingerprint?: string | null;
  freshness?: {
    as_of: string;
    is_stale: boolean;
    stale_reason: string | null;
  };
  blockers?: ResearchJob["blockers"];
  allowed_actions?: string[];
  updated_at: string;
  universe_ref: string;
  frequency: "1d";
  decision_clock: string;
  trade_clock: string;
  settlement_clock: string | null;
  exchange_scope: string[];
  contract_selection: string | null;
  roll_policy: string | null;
  horizon: string;
  research_brief_version_id: string;
  experiment_id?: string | null;
  latest_experiment_id?: string | null;
  created_at: string;
}

interface ApiResearchBrief {
  id: string;
  job_id: string;
  version: number;
  resource_version: number;
  status: ResearchBrief["status"];
  hypothesis: string;
  economic_mechanism: string;
  expected_direction: ResearchBrief["expectedDirection"];
  falsification_conditions: string[];
  allowed_data_domains: string[];
  forbidden_data_domains: string[];
  constraints: string[];
  evidence_ref_ids: string[];
  uncertainties: string[];
  content_hash: string | null;
  created_at: string;
  created_by: string;
  frozen_at: string | null;
  frozen_by: string | null;
}

interface ApiBriefDraft {
  hypothesis: string;
  economic_mechanism: string;
  expected_direction: ResearchBrief["expectedDirection"];
  falsification_conditions: string[];
  allowed_data_domains: string[];
  forbidden_data_domains: string[];
  constraints: string[];
  evidence_ref_ids: string[];
  uncertainties: string[];
}

interface ApiFactorExtraction {
  brief: ApiBriefDraft;
  factor_ir: Record<string, unknown>;
  explanation: string;
}

interface ApiProblem {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  code?: string;
  request_id?: string;
  retryable?: boolean;
  current_version?: string | null;
  field_errors?: Array<{ path: string; code: string; message: string }>;
}

export interface ApiFactorIrExpression {
  ref?: string;
  literal?: number | boolean;
  unit?: string;
  op?: string;
  args?: ApiFactorIrExpression[];
  params?: Record<string, unknown>;
}

export interface ApiFactorIR {
  factor_id: string;
  version: string;
  market_scope: {
    market: string;
    frequency: string;
    universe_ref: string;
  };
  decision_clock: {
    signal_time: string;
    earliest_trade_time: string;
  };
  inputs: Array<{
    alias: string;
    field_ref: string;
    data_type: string;
    unit: string;
    available_time_rule: string;
  }>;
  expression: ApiFactorIrExpression;
}

export interface ApiExperiment {
  id: string;
  project_id: string;
  research_job_id: string;
  brief_version_id: string;
  market: Experiment["market"];
  state: Experiment["state"];
  resource_version: number;
  spec_hash: string;
  factor_ir_hash: string;
  snapshot_id: string;
  snapshot_manifest_hash: string;
  factor_ir?: ApiFactorIR | null;
  decision_time?: string | null;
  random_seed?: number | null;
  latest_run_id?: string | null;
  created_at: string;
  created_by: string;
}

export interface ApiExperimentRun {
  id: string;
  experiment_id: string;
  market: ExperimentRun["market"];
  state: ExperimentRun["state"];
  run_fingerprint: string;
  attempt_count: number;
  validation_summary: {
    observation_count: number;
    finite_count: number;
    missing_count: number;
    coverage_ratio: number;
    minimum: number | null;
    maximum: number | null;
    mean: number | null;
  } | null;
  invariance: {
    future_truncation_passed: boolean;
    sentinel_isolation_passed: boolean;
    baseline_output_hash: string;
    future_truncation_output_hash: string;
    sentinel_isolation_output_hash: string;
  } | null;
  created_at: string;
  updated_at: string;
}

export interface ApiExperimentArtifacts {
  items: Array<{
    content_hash: string;
    artifact_type: string;
    schema_version: string;
    size_bytes: number;
    media_type: string;
    domain_hash: string;
  }>;
  lineage: Array<{
    edge_hash: string;
    source_artifact_hash: string;
    target_artifact_hash: string;
    relation: string;
  }>;
}

export interface ApiFactorValidationReport {
  schema_version: string;
  policy_id: string;
  policy_hash: string;
  label_id: string;
  label_hash: string;
  factor_artifact_hash: string;
  data_quality: {
    observation_count: number;
    finite_count: number;
    coverage_ratio: number;
    constant_ratio: number;
  };
  predictive_power: {
    mean_pearson_ic: number | null;
    mean_rank_ic: number | null;
    icir: number | null;
    nw_t: number | null;
    ic_decay: Array<{ horizon: number; mean_ic: number | null }>;
    quantile_returns: Array<{ quantile: number; mean_return: number | null }>;
    top_bottom_spread: number | null;
    monotonic: boolean | null;
  };
}

export interface ApiIndependence {
  run_id: string;
  output_hash: string;
  baseline_ic: number | null;
  orthogonalized_ic: number | null;
  max_abs_correlation: number | null;
  replicated_risk_factor: boolean;
  report: {
    pairwise: Array<{
      factor_ir_hash: string;
      pearson: number | null;
      spearman: number | null;
    }>;
  } | null;
}

export interface ApiPromotion {
  run_id: string;
  output_hash: string;
  factor_ir_hash: string;
  policy_id: string;
  disposition: string;
  total_score: number | null;
  report: {
    gates: Array<{
      name: string;
      passed: boolean;
      observed: number | null;
      threshold: number | null;
      note: string | null;
    }>;
    component_scores: Array<[string, number]>;
    rationale: string;
  } | null;
}

export interface ApiAlphaPoolFactor {
  factor_ir_hash: string;
  factor_id: string | null;
  instruments: string[];
  data_start: string | null;
  data_end: string | null;
  direction: string;
  market: string;
  universe: string;
  horizon: number;
  policy_id: string;
  risk_premium: boolean;
  lifecycle_state: string;
  oos_ic: number | null;
}

export interface ApiBacktestResult {
  schema_version: string;
  factor_ir_hash: string;
  instrument_ids: string[];
  start: string;
  end: string;
  frequency: string;
  data_source: "snapshot" | "realtime";
  artifact_class: string | null;
  initial_cash: number;
  lot_size: number;
  gross_of_fees: boolean;
  metrics: {
    total_return: number;
    sharpe: number | null;
    max_drawdown: number;
    trade_count: number;
  };
  equity_curve: Array<{ date: string; equity: number }>;
  trades: Array<{
    time: string;
    instrument_id: string;
    side: string;
    quantity: number;
    price: number;
    commission?: number;
  }>;
  positions: Array<{
    instrument_id: string;
    entry: string;
    peak_qty: number;
    avg_px_open: number;
    avg_px_close: number | null;
    realized_pnl: number;
    opened_at: string;
    closed_at: string | null;
  }>;
  backtest_hash: string;
}

export interface ApiStrategyDraft {
  id: string;
  market: MarketId;
  kind: "factor" | "strategy";
  stage: "CREATING" | "READY" | "CODE_TESTED" | "BACKTESTED" | "PAPER_LINKED";
  state: "DRAFT" | "READY" | "FROZEN";
  title: string;
  explanation: string;
  question: string;
  code: string | null;
  ready: boolean;
  instrument_ids: string[];
  frequency: string;
  backtest_plan: {
    timeframes: string[];
    trend_timeframe: string | null;
    exec_timeframe: string;
    start: string;
    end: string;
    rationale: string;
  } | null;
  code_test_result: {
    passed: boolean;
    exit_code: number;
    stderr: string;
    duration_ms: number;
  } | null;
  backtest_results: Array<{
    backtest_hash: string;
    start: string;
    end: string;
    frequency: string;
    metrics: {
      total_return: number;
      sharpe: number | null;
      max_drawdown: number;
      trade_count: number;
    } | null;
    ran_at: string;
  }>;
  paper_binding: { account_id: string; published_at: string } | null;
  content_hash: string | null;
  resource_version: number;
  saved_versions?: Array<{
    version: number;
    hash: string;
    state: string;
    title: string;
    saved_at: string;
  }>;
  created_at: string;
  updated_at: string;
  messages?: Array<{
    role: "user" | "assistant";
    content: string;
    attachments?: Array<{ name: string; kind: "text" | "image"; extracted_text: string }>;
  }>;
}

export interface ApiStrategyBacktestResult {
  instrument_ids: string[];
  start: string;
  end: string;
  frequency: string;
  initial_cash: number;
  gross_of_fees: boolean;
  venue_spec: {
    market: string;
    cost_basis: string;
    fee_model: string | null;
    fill_model: string | null;
    latency_model: string | null;
    random_seed: number | null;
    price_protection_points: number | null;
  } | null;
  metrics: {
    total_return: number;
    sharpe: number | null;
    max_drawdown: number;
    trade_count: number;
  };
  equity_curve: Array<{ date: string; equity: number }>;
  trades: Array<{
    time: string;
    instrument_id: string;
    side: string;
    quantity: number;
    price: number;
    commission?: number;
  }>;
  positions: Array<{
    instrument_id: string;
    entry: string;
    peak_qty: number;
    avg_px_open: number;
    avg_px_close: number | null;
    realized_pnl: number;
    opened_at: string;
    closed_at: string | null;
  }>;
  backtest_hash: string;
  error: string | null;
}

export interface ApiStrategyDataStatus {
  instrument_ids: string[];
  frequencies: string[];
  ready: boolean;
  items: Array<{
    instrument_id: string;
    available: boolean;
    daily: {
      rows: number;
      first_event: string;
      last_event: string;
    } | null;
    minute: {
      rows: number;
      first_event: string;
      last_event: string;
    } | null;
    checks: Array<{
      frequency: string;
      available: boolean;
      required: {
        rows: number;
        first_event: string;
        last_event: string;
      } | null;
    }>;
  }>;
}

export interface ApiMarketDataCoverageEntry {
  instrument_id: string;
  field_prefix: string;
  source_id: string;
  license_tag: string;
  artifact_class: string;
  row_count: number;
  first_event: string;
  last_event: string;
}

export interface ApiExecutionState {
  state_id: string;
  kill_switch_state: "ARMED" | "TRIPPED";
  tripped_by: string | null;
  tripped_at: string | null;
  reason: string | null;
  shadow_positions: Record<string, number>;
  paper_positions: Record<string, number>;
}

export interface ApiPaperAccount {
  id: string;
  owner: string;
  draft_id: string;
  artifact_address: string;
  content_hash: string;
  market: string;
  instrument_ids: string[];
  frequency: string;
  initial_cash: number;
  state: "ACTIVE" | "PAUSED" | "CLOSED";
  created_at: string;
  updated_at: string;
}

export interface ApiPaperOrder {
  id: string;
  instrument_id: string;
  side: "BUY" | "SELL";
  quantity: number;
  order_clock: string;
  status: string;
  reject_reason: string | null;
  filled_qty: number;
  avg_px: number | null;
  created_at: string;
}

export interface ApiPaperFill {
  id: string;
  order_id: string;
  trade_ts: string;
  price: number;
  quantity: number;
  fee: number;
  notional: number;
}

export interface ApiPaperPosition {
  instrument_id: string;
  quantity: number;
  avg_px: number | null;
  updated_at: string;
}

export interface ApiPaperEquityRow {
  trade_date: string;
  equity: number;
  cash: number;
  margin_used: number;
  drawdown: number;
}

export interface ApiPaperDriftReport {
  schema_version: string;
  points: Array<{
    date: string;
    backtest_equity: number;
    paper_equity: number;
    diff: number;
  }>;
  common_days: number;
  paper_days: number;
  backtest_days: number;
  max_abs_diff: number;
  cost_basis: string | null;
  backtest_hash: string | null;
}

export interface ApiSession {
  actor: { id: string; displayName: string };
  roles: string[];
  capabilities: string[];
  environments: string[];
  markets: string[];
}

export interface QuantApiClient {
  getSession(): Promise<Session>;
  listResearchJobs(): Promise<ResearchJob[]>;
  getResearchJob(id: string): Promise<ResearchJob>;
  listBriefVersions(jobId: string): Promise<ResearchBrief[]>;
  getBrief(id: string): Promise<ResearchBrief>;
  createBrief(
    jobId: string,
    draft: BriefDraftInput,
    jobResourceVersion?: number,
  ): Promise<ResearchBrief>;
  updateBrief(id: string, brief: ResearchBrief): Promise<ResearchBrief>;
  freezeBrief(id: string, resourceVersion?: number): Promise<ResearchBrief>;
  parsePaperToBrief(
    paperText: string,
    market: MarketId,
  ): Promise<BriefDraftInput>;
  extractFactor(
    paperText: string,
    market: MarketId,
  ): Promise<FactorExtractionResult>;
  createResearchFromPaper(
    paperText: string,
    market: MarketId,
  ): Promise<FromPaperPipelineResult>;
  createResearchFromPaperFile(
    file: File,
    prompt: string,
    market: MarketId,
  ): Promise<FromPaperPipelineResult>;
  createResearchJob(input: CreateResearchJobInput): Promise<ResearchJob>;
  preregisterExperiment(input: PreregisterExperimentInput): Promise<Experiment>;
  getExperiment(id: string): Promise<Experiment>;
  runExperiment(id: string): Promise<ExperimentRun>;
  getExperimentRun(id: string): Promise<ExperimentRun>;
  getExperimentArtifacts(id: string): Promise<ExperimentArtifacts>;
  getExperimentValidation(id: string): Promise<FactorValidationReport>;
  getExperimentIndependence(id: string): Promise<IndependenceSummary>;
  getExperimentPromotion(id: string): Promise<PromotionSummary>;
  listAlphaPool(): Promise<AlphaPoolFactor[]>;
  runBacktest(input: RunBacktestInput): Promise<BacktestResult>;
  getMarketDataCoverage(
    instruments: string[],
  ): Promise<MarketDataCoverageEntry[]>;
  createStrategyDraft(
    market: MarketId,
    firstMessage: string,
    attachments?: StrategyAttachment[],
  ): Promise<StrategyDraft>;
  listStrategyDrafts(
    state?: "DRAFT" | "READY" | "FROZEN",
  ): Promise<StrategyDraft[]>;
  postStrategyMessage(
    draftId: string,
    message: string,
    attachments?: StrategyAttachment[],
  ): Promise<StrategyDraft>;
  uploadStrategyAttachment(
    market: MarketId,
    file: File,
  ): Promise<StrategyAttachment>;
  getStrategyDraft(draftId: string): Promise<StrategyDraft>;
  freezeStrategyDraft(draftId: string): Promise<StrategyDraft>;
  unfreezeStrategyDraft(draftId: string): Promise<StrategyDraft>;
  saveStrategyDraft(draftId: string): Promise<StrategyDraft>;
  codeTestStrategyDraft(draftId: string): Promise<StrategyCodeTestResult>;
  backtestStrategyDraft(
    draftId: string,
    options?: {
      frequency?: StrategyFrequency;
      startDate?: string;
      endDate?: string;
    },
  ): Promise<StrategyBacktestResult>;
  getStrategyBacktestResult(
    draftId: string,
    backtestHash: string,
  ): Promise<StrategyBacktestResult>;
  getStrategyDataStatus(
    draftId: string,
    frequency?: StrategyFrequency,
    startDate?: string,
    endDate?: string,
  ): Promise<StrategyDataStatus>;
  provisionStrategyData(
    draftId: string,
    frequency?: StrategyFrequency,
    startDate?: string,
    endDate?: string,
  ): Promise<StrategyProvisionResult>;
  listFormalSnapshots(): Promise<FormalSnapshotInfo[]>;
  provisionData(input: ProvisionInput): Promise<{ taskId: string }>;
  getProvisioningTask(taskId: string): Promise<ProvisioningTaskStatus>;
  listLabelSnapshots(): Promise<LabelSnapshotInfo[]>;
  validateExperiment(
    runId: string,
    policyId: string,
    labelSnapshotId: string,
    labelSnapshotManifestHash: string,
  ): Promise<ExperimentRun>;
  getExecutionState(): Promise<ExecutionState>;
  tripKillSwitch(reason: string): Promise<ExecutionState>;
  resetKillSwitch(): Promise<ExecutionState>;

  // Paper 仿真
  listPaperAccounts(): Promise<PaperAccount[]>;
  createPaperAccount(
    draftId: string,
    initialCash?: number,
  ): Promise<PaperAccount>;
  getPaperAccount(id: string): Promise<PaperAccount>;
  pausePaperAccount(id: string): Promise<PaperAccount>;
  resumePaperAccount(id: string): Promise<PaperAccount>;
  closePaperAccount(id: string): Promise<PaperAccount>;
  listPaperOrders(id: string): Promise<PaperOrder[]>;
  listPaperFills(id: string): Promise<PaperFill[]>;
  listPaperPositions(id: string): Promise<PaperPosition[]>;
  listPaperEquity(id: string): Promise<PaperEquityRow[]>;
  paperDrift(id: string): Promise<PaperDriftReport>;
  paperRunStatus(id: string): Promise<PaperRunStatus>;
  startPaperNode(id: string): Promise<{ account_id: string; starting: boolean }>;

  // Agent 基座模型配置
  getAgentConfig(): Promise<AgentConfigState>;
  listAgentConfigAgents(): Promise<AgentDescriptor[]>;
  listAgentConfigProviders(agent?: AgentId): Promise<AgentProviderInfo[]>;
  listAgentConfigModels(
    agent: AgentId,
    provider: string,
  ): Promise<{ items: AgentModelInfo[]; note?: string }>;
  upsertAgentProvider(input: {
    provider: string;
    apiKey: string;
    kind?: "builtin" | "custom";
    baseUrl?: string;
  }): Promise<AgentProviderInfo>;
  deleteAgentProvider(provider: string): Promise<void>;
  saveAgentConfig(input: {
    agent: AgentId;
    provider: string;
    model: string;
  }): Promise<{ agent: string; provider: string; model: string }>;

  // 因子构建
  extractBuildSpec(
    paperText: string,
    market: MarketId,
  ): Promise<FactorBuildSpecExtraction>;
  generateCodeDraft(spec: FactorBuildSpec): Promise<FactorCodeBundleDraft>;
  smokeFiles(files: Record<string, string>): Promise<{
    exit_code: number;
    timed_out: boolean;
    stderr: string;
  }>;
  createFactorBuildSpec(spec: FactorBuildSpec): Promise<FactorBuildSpecRecord>;
  freezeFactorBuildSpec(
    specId: string,
    resourceVersion: number,
  ): Promise<FactorBuildSpecRecord>;
  registerCodeBundle(
    specId: string,
    specHash: string,
    draft: FactorCodeBundleDraft,
  ): Promise<Record<string, unknown>>;
  trainFactor(input: {
    spec_hash: string;
    bundle_hash: string;
    instrument_ids: string[];
    decision_time: string;
  }): Promise<{ run: FactorBuildRunRecord; weights_hash: string }>;
  inferFactor(input: {
    spec_hash: string;
    bundle_hash: string;
    weights_hash: string;
    instrument_ids: string[];
    decision_time: string;
  }): Promise<{
    run: FactorBuildRunRecord;
    factor_values_hash: string;
    output_hash: string;
    observation_count: number;
  }>;
  validateFactor(input: {
    spec_hash: string;
    factor_values_hash: string;
    instrument_ids: string[];
    price_field: string;
    horizon: number;
    decision_time: string;
  }): Promise<ModelFactorValidationReport>;
  getFactorBuildRun(runId: string): Promise<FactorBuildRunRecord>;
}

export class QuantApiProblem extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: string;
  readonly requestId: string | null;
  readonly retryable: boolean;
  readonly currentVersion: string | null;
  readonly fieldErrors: ApiProblem["field_errors"];

  constructor(problem: ApiProblem, fallbackStatus: number) {
    const detail = problem.detail ?? problem.title ?? "The API request failed.";
    super(detail);
    this.name = "QuantApiProblem";
    this.status = problem.status ?? fallbackStatus;
    this.code = problem.code ?? "API_REQUEST_FAILED";
    this.detail = detail;
    this.requestId = problem.request_id ?? null;
    this.retryable = problem.retryable ?? false;
    this.currentVersion = problem.current_version ?? null;
    this.fieldErrors = problem.field_errors ?? [];
  }
}

interface HttpQuantApiClientOptions {
  baseUrl: string;
  accessToken?: string | (() => string | Promise<string>);
  session: Session;
  fetcher?: Fetcher;
  idempotencyKey?: () => string;
}

export class HttpQuantApiClient implements QuantApiClient {
  private readonly baseUrl: string;
  private readonly accessToken: HttpQuantApiClientOptions["accessToken"];
  private readonly session: Session;
  private readonly fetcher: Fetcher;
  private readonly idempotencyKey: () => string;
  private readonly etags = new Map<string, string>();

  constructor(options: HttpQuantApiClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.accessToken = options.accessToken;
    this.session = structuredClone(options.session);
    this.fetcher =
      options.fetcher ?? ((input, init) => fetch(input, init));
    this.idempotencyKey = options.idempotencyKey ?? (() => crypto.randomUUID());
  }

  async getSession() {
    try {
      const result = await this.request<ApiSession>("/session");
      return mapSession(result.body);
    } catch {
      return structuredClone(this.session);
    }
  }

  async listResearchJobs() {
    const result = await this.request<ApiList<ApiResearchJob>>("/research-jobs");
    return result.body.items.map(mapResearchJob);
  }

  async getResearchJob(id: string) {
    const result = await this.request<ApiResearchJob>(`/research-jobs/${id}`);
    this.rememberEtag(id, result.response);
    return mapResearchJob(result.body);
  }

  async listBriefVersions(jobId: string) {
    const result = await this.request<ApiList<ApiResearchBrief>>(
      `/research-jobs/${jobId}/brief-versions`,
    );
    return result.body.items.map(mapResearchBrief);
  }

  async getBrief(id: string) {
    const result = await this.request<ApiResearchBrief>(
      `/research-brief-versions/${id}`,
    );
    this.rememberEtag(id, result.response);
    return mapResearchBrief(result.body);
  }

  async createBrief(
    jobId: string,
    draft: BriefDraftInput,
    jobResourceVersion?: number,
  ) {
    const receipt = await this.request<ApiCommandReceipt>(
      `/research-jobs/${jobId}/brief-versions`,
      {
        method: "POST",
        headers: this.commandHeaders(jobId, jobResourceVersion),
        body: JSON.stringify({
          metadata: commandMetadata("Create a research brief draft"),
          brief: briefCommand(draft),
        }),
      },
    );
    return this.getBrief(receipt.body.resource_id);
  }

  async updateBrief(id: string, brief: ResearchBrief) {
    await this.request<ApiCommandReceipt>(`/research-brief-versions/${id}`, {
      method: "PATCH",
      headers: this.commandHeaders(id, brief.resourceVersion),
      body: JSON.stringify({
        metadata: commandMetadata("Update a research brief draft"),
        brief: briefCommand(brief),
      }),
    });
    return this.getBrief(id);
  }

  async freezeBrief(id: string, resourceVersion?: number) {
    await this.request<ApiCommandReceipt>(`/research-brief-versions/${id}:freeze`, {
      method: "POST",
      headers: this.commandHeaders(id, resourceVersion),
      body: JSON.stringify(commandMetadata("Freeze a research brief version")),
    });
    return this.getBrief(id);
  }

  async parsePaperToBrief(paperText: string, market: MarketId) {
    const result = await this.request<{ brief: ApiBriefDraft }>(
      "/research-briefs:from-paper",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paper_text: paperText, market }),
      },
    );
    return mapBriefDraft(result.body.brief);
  }

  async extractFactor(paperText: string, market: MarketId) {
    const result = await this.request<ApiFactorExtraction>(
      "/research-briefs:extract-factor",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paper_text: paperText, market }),
      },
    );
    return mapFactorExtraction(result.body);
  }

  async createResearchFromPaper(paperText: string, market: MarketId) {
    const result = await this.request<{
      job_id: string;
      brief_id: string;
      experiment_id: string;
      brief: ApiBriefDraft;
      factor_ir: Record<string, unknown>;
      explanation: string;
    }>("/research-pipelines:from-paper", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": this.idempotencyKey(),
      },
      body: JSON.stringify({ paper_text: paperText, market }),
    });
    return {
      jobId: result.body.job_id,
      briefId: result.body.brief_id,
      experimentId: result.body.experiment_id,
      brief: mapBriefDraft(result.body.brief),
      factorIr: result.body.factor_ir,
      explanation: result.body.explanation,
    } satisfies FromPaperPipelineResult;
  }

  async createResearchFromPaperFile(
    file: File,
    prompt: string,
    market: MarketId,
  ) {
    const form = new FormData();
    form.append("file", file);
    form.append("prompt", prompt);
    form.append("market", market);
    const result = await this.request<{
      job_id: string;
      brief_id: string;
      experiment_id: string;
      brief: ApiBriefDraft;
      factor_ir: Record<string, unknown>;
      explanation: string;
    }>("/research-pipelines:from-paper-file", {
      method: "POST",
      headers: { "Idempotency-Key": this.idempotencyKey() },
      body: form,
    });
    return {
      jobId: result.body.job_id,
      briefId: result.body.brief_id,
      experimentId: result.body.experiment_id,
      brief: mapBriefDraft(result.body.brief),
      factorIr: result.body.factor_ir,
      explanation: result.body.explanation,
    } satisfies FromPaperPipelineResult;
  }

  async createResearchJob(input: CreateResearchJobInput) {
    const receipt = await this.request<ApiCommandReceipt>("/research-jobs", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": this.idempotencyKey(),
      },
      body: JSON.stringify({
        metadata: commandMetadata("Create a preregistered research workspace"),
        market: input.market,
        environment: input.environment,
        universe_ref: input.universeRef,
        frequency: input.frequency,
        decision_clock: input.decisionClock,
        trade_clock: input.tradeClock,
        settlement_clock: input.settlementClock || null,
        exchange_scope: input.exchangeScope,
        contract_selection: input.contractSelection || null,
        roll_policy: input.rollPolicy || null,
        horizon: input.horizon,
        research_brief_version_id: input.briefVersionId,
      }),
    });
    return this.getResearchJob(receipt.body.resource_id);
  }

  async preregisterExperiment(input: PreregisterExperimentInput) {
    const receipt = await this.request<ApiCommandReceipt>(
      "/experiments:preregister",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": this.idempotencyKey(),
        },
        body: JSON.stringify({
          metadata: commandMetadata("Preregister a bounded research experiment"),
          research_job_id: input.researchJobId,
          brief_version_id: input.briefVersionId,
          decision_time: input.decisionTime,
          random_seed: input.randomSeed,
          resource_budget: {
            cpu_seconds: input.resourceBudget.cpuSeconds,
            wall_clock_seconds: input.resourceBudget.wallClockSeconds,
            memory_mb: input.resourceBudget.memoryMb,
            max_observations: input.resourceBudget.maxObservations,
          },
          factor_ir: input.factorIr,
          snapshot_id: input.snapshotId,
          snapshot_manifest_hash: input.snapshotManifestHash,
        }),
      },
    );
    return this.getExperiment(receipt.body.resource_id);
  }

  async getExperiment(id: string) {
    const result = await this.request<ApiExperiment>(`/experiments/${id}`);
    this.rememberEtag(id, result.response, result.body.resource_version);
    return mapExperiment(result.body);
  }

  async runExperiment(id: string) {
    const receipt = await this.request<ApiCommandReceipt>(
      `/experiments/${id}:run`,
      {
        method: "POST",
        headers: this.commandHeaders(id),
        body: JSON.stringify({
          metadata: commandMetadata("Run a preregistered research experiment"),
        }),
      },
    );
    return this.getExperimentRun(receipt.body.resource_id);
  }

  async getExperimentRun(id: string) {
    const result = await this.request<ApiExperimentRun>(
      `/experiment-runs/${id}`,
    );
    return mapExperimentRun(result.body);
  }

  async getExperimentArtifacts(id: string) {
    const result = await this.request<ApiExperimentArtifacts>(
      `/experiment-runs/${id}/artifacts`,
    );
    return mapExperimentArtifacts(result.body);
  }

  async getExperimentValidation(id: string) {
    const result = await this.request<ApiFactorValidationReport>(
      `/experiment-runs/${id}/validation`,
    );
    return mapFactorValidationReport(result.body);
  }

  async getExperimentIndependence(id: string) {
    const result = await this.request<ApiIndependence>(
      `/experiment-runs/${id}/independence`,
    );
    return mapIndependence(result.body);
  }

  async getExperimentPromotion(id: string) {
    const result = await this.request<ApiPromotion>(
      `/experiment-runs/${id}/promotion`,
    );
    return mapPromotion(result.body);
  }

  async listAlphaPool() {
    const result = await this.request<{ items: ApiAlphaPoolFactor[] }>(
      "/alpha-pool",
    );
    return result.body.items.map(mapAlphaPoolFactor);
  }

  async runBacktest(input: RunBacktestInput) {
    const result = await this.request<ApiBacktestResult>("/backtests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        factor_ir_hash: input.factorIrHash,
        instrument_ids: input.instrumentIds ?? null,
        start_date: input.startDate ?? null,
        end_date: input.endDate ?? null,
        frequency: input.frequency ?? "1d",
        data_source: input.dataSource ?? "snapshot",
        lot_size: input.lotSize ?? 1,
        initial_cash: input.initialCash ?? 100_000_000,
        reason: "Run factor backtest from strategy workbench",
      }),
    });
    return mapBacktestResult(result.body);
  }

  async getMarketDataCoverage(instruments: string[]) {
    const query = encodeURIComponent(instruments.join(","));
    const result = await this.request<{ items: ApiMarketDataCoverageEntry[] }>(
      `/market-data/coverage?instruments=${query}`,
    );
    return result.body.items.map(mapMarketDataCoverageEntry);
  }

  async createStrategyDraft(
    market: MarketId,
    firstMessage: string,
    attachments?: StrategyAttachment[],
  ) {
    const result = await this.request<ApiStrategyDraft>("/strategy-drafts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        market,
        first_message: firstMessage,
        attachments: (attachments ?? []).map(mapStrategyAttachmentToApi),
      }),
    });
    return mapStrategyDraft(result.body);
  }

  async listStrategyDrafts(state?: "DRAFT" | "READY" | "FROZEN") {
    const query = state ? `?state=${state}` : "";
    const result = await this.request<{ items: ApiStrategyDraft[] }>(
      `/strategy-drafts${query}`,
    );
    return result.body.items.map(mapStrategyDraft);
  }

  async postStrategyMessage(
    draftId: string,
    message: string,
    attachments?: StrategyAttachment[],
  ) {
    const result = await this.request<ApiStrategyDraft>(
      `/strategy-drafts/${draftId}/messages`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message,
          attachments: (attachments ?? []).map(mapStrategyAttachmentToApi),
        }),
      },
    );
    return mapStrategyDraft(result.body);
  }

  async uploadStrategyAttachment(market: MarketId, file: File) {
    const form = new FormData();
    form.append("file", file);
    const result = await this.request<{
      name: string;
      kind: "text" | "image";
      object_key: string;
      extracted_text: string;
    }>(`/strategy-drafts/attachments?market=${market}`, {
      method: "POST",
      body: form,
    });
    return {
      name: result.body.name,
      kind: result.body.kind,
      objectKey: result.body.object_key,
      extractedText: result.body.extracted_text,
    };
  }

  async getStrategyDraft(draftId: string) {
    const result = await this.request<ApiStrategyDraft>(
      `/strategy-drafts/${draftId}`,
    );
    return mapStrategyDraft(result.body);
  }

  async freezeStrategyDraft(draftId: string) {
    const result = await this.request<ApiStrategyDraft>(
      `/strategy-drafts/${draftId}:freeze`,
      { method: "POST" },
    );
    return mapStrategyDraft(result.body);
  }

  async unfreezeStrategyDraft(draftId: string) {
    const result = await this.request<ApiStrategyDraft>(
      `/strategy-drafts/${draftId}:unfreeze`,
      { method: "POST" },
    );
    return mapStrategyDraft(result.body);
  }

  async saveStrategyDraft(draftId: string) {
    const result = await this.request<ApiStrategyDraft>(
      `/strategy-drafts/${draftId}:save`,
      { method: "POST" },
    );
    return mapStrategyDraft(result.body);
  }

  async codeTestStrategyDraft(draftId: string) {
    const result = await this.request<{
      passed: boolean;
      exit_code: number;
      stderr: string;
      duration_ms: number;
    }>(`/strategy-drafts/${draftId}:code-test`, { method: "POST" });
    const body = result.body;
    return {
      passed: body.passed,
      exitCode: body.exit_code,
      stderr: body.stderr,
      durationMs: body.duration_ms,
    };
  }

  async backtestStrategyDraft(
    draftId: string,
    options?: {
      frequency?: StrategyFrequency;
      startDate?: string;
      endDate?: string;
    },
  ) {
    const params = new URLSearchParams();
    if (options?.frequency) params.set("frequency", options.frequency);
    if (options?.startDate) params.set("start", options.startDate);
    if (options?.endDate) params.set("end", options.endDate);
    const query = params.toString();
    const result = await this.request<ApiStrategyBacktestResult>(
      `/strategy-drafts/${draftId}:backtest${query ? `?${query}` : ""}`,
      { method: "POST" },
    );
    return mapStrategyBacktestResult(result.body);
  }

  async getStrategyBacktestResult(draftId: string, backtestHash: string) {
    const result = await this.request<ApiStrategyBacktestResult>(
      `/strategy-drafts/${draftId}/backtests/${encodeURIComponent(backtestHash)}`,
    );
    return mapStrategyBacktestResult(result.body);
  }

  async getStrategyDataStatus(
    draftId: string,
    frequency?: StrategyFrequency,
    startDate?: string,
    endDate?: string,
  ) {
    const params = new URLSearchParams();
    if (frequency) params.set("frequency", frequency);
    if (startDate) params.set("start", startDate);
    if (endDate) params.set("end", endDate);
    const query = params.toString();
    const result = await this.request<ApiStrategyDataStatus>(
      `/strategy-drafts/${draftId}/data-status${query ? `?${query}` : ""}`,
    );
    return mapStrategyDataStatus(result.body);
  }

  async provisionStrategyData(
    draftId: string,
    frequency?: StrategyFrequency,
    startDate?: string,
    endDate?: string,
  ) {
    const params = new URLSearchParams();
    if (frequency) params.set("frequency", frequency);
    if (startDate) params.set("start", startDate);
    if (endDate) params.set("end", endDate);
    const query = params.toString();
    const result = await this.request<{
      instrument_ids: string[];
      frequency: string;
      rows: number;
      sources: string[];
    }>(`/strategy-drafts/${draftId}:provision${query ? `?${query}` : ""}`, {
      method: "POST",
    });
    return {
      instrumentIds: result.body.instrument_ids,
      frequency: result.body.frequency,
      rows: result.body.rows,
      sources: result.body.sources,
    };
  }

  async listFormalSnapshots() {
    const result = await this.request<ApiList<ApiFormalSnapshot>>(
      "/formal-snapshots",
    );
    return result.body.items.map(
      (item): FormalSnapshotInfo => ({
        snapshotId: item.snapshot_id,
        manifestHash: item.manifest_hash,
        market: item.market ?? null,
        universeRef: item.universe_ref ?? null,
        frequency: item.frequency ?? null,
        decisionClock: item.decision_clock ?? null,
        tradeClock: item.trade_clock ?? null,
        frozenAt: item.frozen_at ?? null,
        instruments: item.instruments ?? null,
      }),
    );
  }

  async provisionData(input: ProvisionInput) {
    const result = await this.request<{ task_id: string; status: string }>(
      "/data-provisioning",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          universe_ref: input.universeRef,
          explicit_instruments: input.explicitInstruments,
          exchange_scope: input.exchangeScope,
          start: input.start,
          end: input.end,
        }),
      },
    );
    return { taskId: result.body.task_id };
  }

  async getProvisioningTask(taskId: string) {
    const result = await this.request<ApiProvisioningTaskStatus>(
      `/data-provisioning/${taskId}`,
    );
    return mapProvisioningTaskStatus(result.body);
  }

  async listLabelSnapshots() {
    const result = await this.request<ApiList<ApiLabelSnapshot>>(
      "/label-snapshots",
    );
    return result.body.items.map(mapLabelSnapshot);
  }

  async validateExperiment(
    runId: string,
    policyId: string,
    labelSnapshotId: string,
    labelSnapshotManifestHash: string,
  ) {
    await this.request<ApiCommandReceipt>(`/experiment-runs/${runId}:validate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": this.idempotencyKey(),
      },
      body: JSON.stringify({
        metadata: commandMetadata("Validate factor predictive power"),
        policy_id: policyId,
        label_snapshot_id: labelSnapshotId,
        label_snapshot_manifest_hash: labelSnapshotManifestHash,
      }),
    });
    return this.getExperimentRun(runId);
  }

  async getExecutionState() {
    const result = await this.request<ApiExecutionState>("/execution/state");
    return mapExecutionState(result.body);
  }

  async tripKillSwitch(reason: string) {
    const result = await this.request<ApiExecutionState>(
      "/execution/kill-switch:trip",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision: "APPROVE", reason }),
      },
    );
    return mapExecutionState(result.body);
  }

  async resetKillSwitch() {
    const result = await this.request<ApiExecutionState>(
      "/execution/kill-switch:reset",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      },
    );
    return mapExecutionState(result.body);
  }

  async listPaperAccounts() {
    const result = await this.request<{ accounts: ApiPaperAccount[] }>(
      "/paper/accounts",
    );
    return result.body.accounts.map(mapPaperAccount);
  }

  async createPaperAccount(draftId: string, initialCash?: number) {
    const result = await this.request<ApiPaperAccount>("/paper/accounts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        draft_id: draftId,
        ...(initialCash !== undefined ? { initial_cash: initialCash } : {}),
      }),
    });
    return mapPaperAccount(result.body);
  }

  async getPaperAccount(id: string) {
    const result = await this.request<ApiPaperAccount>(`/paper/accounts/${id}`);
    return mapPaperAccount(result.body);
  }

  async pausePaperAccount(id: string) {
    const result = await this.request<ApiPaperAccount>(
      `/paper/accounts/${id}:pause`,
      { method: "POST" },
    );
    return mapPaperAccount(result.body);
  }

  async resumePaperAccount(id: string) {
    const result = await this.request<ApiPaperAccount>(
      `/paper/accounts/${id}:resume`,
      { method: "POST" },
    );
    return mapPaperAccount(result.body);
  }

  async closePaperAccount(id: string) {
    const result = await this.request<ApiPaperAccount>(
      `/paper/accounts/${id}:close`,
      { method: "POST" },
    );
    return mapPaperAccount(result.body);
  }

  async listPaperOrders(id: string) {
    const result = await this.request<{ orders: ApiPaperOrder[] }>(
      `/paper/accounts/${id}/orders`,
    );
    return result.body.orders.map(mapPaperOrder);
  }

  async listPaperFills(id: string) {
    const result = await this.request<{ fills: ApiPaperFill[] }>(
      `/paper/accounts/${id}/fills`,
    );
    return result.body.fills.map(mapPaperFill);
  }

  async listPaperPositions(id: string) {
    const result = await this.request<{ positions: ApiPaperPosition[] }>(
      `/paper/accounts/${id}/positions`,
    );
    return result.body.positions.map(mapPaperPosition);
  }

  async listPaperEquity(id: string) {
    const result = await this.request<{ equity: ApiPaperEquityRow[] }>(
      `/paper/accounts/${id}/equity`,
    );
    return result.body.equity.map(mapPaperEquityRow);
  }

  async paperDrift(id: string) {
    const result = await this.request<ApiPaperDriftReport>(
      `/paper/accounts/${id}/drift`,
    );
    return mapPaperDriftReport(result.body);
  }

  async paperRunStatus(id: string) {
    const result = await this.request<PaperRunStatus>(
      `/paper/accounts/${id}/run-status`,
    );
    return result.body;
  }

  async startPaperNode(id: string) {
    const result = await this.request<{ account_id: string; starting: boolean }>(
      `/paper/accounts/${id}:start-node`,
      { method: "POST" },
    );
    return result.body;
  }

  // ── Agent 基座模型配置 ──────────────────────────────────────────────

  async getAgentConfig() {
    const result = await this.request<{
      agent: string;
      provider: string;
      model: string;
      providers: Array<{
        provider: string;
        kind: "builtin" | "custom";
        has_api_key: boolean;
        masked_key: string;
        base_url?: string | null;
      }>;
    }>("/agent-config");
    return {
      agent: result.body.agent,
      provider: result.body.provider,
      model: result.body.model,
      providers: result.body.providers.map((item) => ({
        provider: item.provider,
        kind: item.kind,
        hasApiKey: item.has_api_key,
        maskedKey: item.masked_key,
        baseUrl: item.base_url,
      })),
    };
  }

  async listAgentConfigAgents() {
    const result = await this.request<{ items: AgentDescriptor[] }>(
      "/agent-config/agents",
    );
    return result.body.items;
  }

  async listAgentConfigProviders(agent?: AgentId) {
    const result = await this.request<{
      items: Array<{
        provider: string;
        kind: "builtin" | "custom";
        has_api_key: boolean;
        masked_key: string;
        base_url?: string | null;
      }>;
    }>(`/agent-config/providers${agent ? `?agent=${agent}` : ""}`);
    return result.body.items.map((item) => ({
      provider: item.provider,
      kind: item.kind,
      hasApiKey: item.has_api_key,
      maskedKey: item.masked_key,
      baseUrl: item.base_url,
    }));
  }

  async listAgentConfigModels(agent: AgentId, provider: string) {
    const result = await this.request<{
      items: Array<{
        provider: string;
        model: string;
        context: string;
        max_out: string;
        thinking: boolean;
        images: boolean;
      }>;
      note?: string;
    }>(`/agent-config/models?agent=${agent}&provider=${provider}`);
    return {
      items: result.body.items.map((item) => ({
        provider: item.provider,
        model: item.model,
        context: item.context,
        maxOut: item.max_out,
        thinking: item.thinking,
        images: item.images,
      })),
      note: result.body.note,
    };
  }

  async upsertAgentProvider(input: {
    provider: string;
    apiKey: string;
    kind?: "builtin" | "custom";
    baseUrl?: string;
  }) {
    const result = await this.request<{
      provider: string;
      kind: "builtin" | "custom";
      has_api_key: boolean;
      masked_key: string;
      base_url?: string | null;
    }>("/agent-config/credentials", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: input.provider,
        api_key: input.apiKey,
        kind: input.kind ?? "builtin",
        base_url: input.baseUrl ?? null,
      }),
    });
    return {
      provider: result.body.provider,
      kind: result.body.kind,
      hasApiKey: result.body.has_api_key,
      maskedKey: result.body.masked_key,
      baseUrl: result.body.base_url,
    };
  }

  async deleteAgentProvider(provider: string) {
    await this.request<{ provider: string }>(
      `/agent-config/credentials?provider=${encodeURIComponent(provider)}`,
      { method: "DELETE" },
    );
  }

  async saveAgentConfig(input: {
    agent: AgentId;
    provider: string;
    model: string;
  }) {
    const result = await this.request<{
      agent: string;
      provider: string;
      model: string;
    }>("/agent-config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    });
    return result.body;
  }

  // ── 因子构建 ──────────────────────────────────────────────────────

  async extractBuildSpec(paperText: string, market: MarketId) {
    const result = await this.request<{
      spec: FactorBuildSpec;
      spec_hash: string;
    }>("/factor-build-specs:extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paper_text: paperText, market }),
    });
    return { spec: result.body.spec, spec_hash: result.body.spec_hash };
  }

  async generateCodeDraft(spec: FactorBuildSpec) {
    const result = await this.request<{
      files: Record<string, string>;
      manifest: Record<string, unknown>;
      bundle_hash: string;
    }>("/factor-build-specs:generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spec }),
    });
    return {
      files: result.body.files,
      manifest: result.body.manifest,
      bundle_hash: result.body.bundle_hash,
    };
  }

  async smokeFiles(files: Record<string, string>) {
    const result = await this.request<{
      smoke: { exit_code: number; timed_out: boolean; stderr: string };
    }>("/factor-build-specs:smoke", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files }),
    });
    return result.body.smoke;
  }

  async createFactorBuildSpec(spec: FactorBuildSpec) {
    const result = await this.request<FactorBuildSpecRecord>(
      "/factor-build-specs",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": this.idempotencyKey(),
        },
        body: JSON.stringify({
          metadata: commandMetadata("Create a factor build spec"),
          spec,
        }),
      },
    );
    return result.body;
  }

  async freezeFactorBuildSpec(specId: string, resourceVersion: number) {
    const result = await this.request<FactorBuildSpecRecord>(
      `/factor-build-specs/${specId}:freeze`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": this.idempotencyKey(),
          "If-Match": `"${resourceVersion}"`,
        },
        body: JSON.stringify({
          metadata: commandMetadata("Freeze a factor build spec"),
        }),
      },
    );
    return result.body;
  }

  async registerCodeBundle(
    specId: string,
    specHash: string,
    draft: FactorCodeBundleDraft,
  ) {
    const result = await this.request<Record<string, unknown>>(
      `/factor-build-specs/${specId}:generate`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": this.idempotencyKey(),
        },
        body: JSON.stringify({
          metadata: commandMetadata("Register a generated code bundle"),
          spec_hash: specHash,
          bundle_hash: draft.bundle_hash,
          manifest: draft.manifest,
          files: draft.files,
        }),
      },
    );
    return result.body;
  }

  async trainFactor(input: {
    spec_hash: string;
    bundle_hash: string;
    instrument_ids: string[];
    decision_time: string;
  }) {
    const result = await this.request<{
      run: FactorBuildRunRecord;
      weights_hash: string;
    }>("/factor-build-specs:train", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": this.idempotencyKey(),
      },
      body: JSON.stringify({
        metadata: commandMetadata("Train a factor build"),
        ...input,
      }),
    });
    return result.body;
  }

  async inferFactor(input: {
    spec_hash: string;
    bundle_hash: string;
    weights_hash: string;
    instrument_ids: string[];
    decision_time: string;
  }) {
    const result = await this.request<{
      run: FactorBuildRunRecord;
      factor_values_hash: string;
      output_hash: string;
      observation_count: number;
    }>("/factor-build-specs:infer", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": this.idempotencyKey(),
      },
      body: JSON.stringify({
        metadata: commandMetadata("Infer factor values"),
        ...input,
      }),
    });
    return result.body;
  }

  async validateFactor(input: {
    spec_hash: string;
    factor_values_hash: string;
    instrument_ids: string[];
    price_field: string;
    horizon: number;
    decision_time: string;
  }) {
    const result = await this.request<ModelFactorValidationReport>(
      "/factor-build-specs:validate",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(input),
      },
    );
    return result.body;
  }

  async getFactorBuildRun(runId: string) {
    const result = await this.request<FactorBuildRunRecord>(
      `/factor-build-runs/${runId}`,
    );
    return result.body;
  }

  private commandHeaders(id: string, resourceVersion?: number) {
    const etag =
      this.etags.get(id) ??
      (resourceVersion === undefined ? undefined : `"${resourceVersion}"`);
    if (!etag) {
      throw new QuantApiProblem(
        {
          status: 428,
          code: "ETAG_REQUIRED",
          detail: "Reload the resource before issuing a write command.",
        },
        428,
      );
    }
    return {
      "Content-Type": "application/json",
      "Idempotency-Key": this.idempotencyKey(),
      "If-Match": etag,
    };
  }

  private rememberEtag(
    id: string,
    response: Response,
    resourceVersion?: number,
  ) {
    const etag = response.headers.get("ETag");
    if (etag) {
      this.etags.set(id, etag);
    } else if (resourceVersion !== undefined) {
      this.etags.set(id, `"${resourceVersion}"`);
    }
  }

  private async request<T>(
    path: string,
    init: RequestInit = {},
  ): Promise<{ body: T; response: Response }> {
    const token =
      typeof this.accessToken === "function"
        ? await this.accessToken()
        : this.accessToken;
    const response = await this.fetcher(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        Accept: "application/json, application/problem+json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...init.headers,
      },
    });
    const body = (await response.json()) as T | ApiProblem;
    if (!response.ok) {
      throw new QuantApiProblem(body as ApiProblem, response.status);
    }
    return { body: body as T, response };
  }
}

function mapProvisionResult(input: ApiProvisionResult): ProvisionResult {
  return {
    snapshotId: input.snapshot_id,
    snapshotManifestHash: input.snapshot_manifest_hash,
    decisionTime: input.decision_time,
    instrumentCount: input.instrument_count,
    rowCount: input.row_count,
    labelSnapshotId: input.label_snapshot_id,
    labelSnapshotManifestHash: input.label_snapshot_manifest_hash,
  };
}

function mapProvisioningTaskStatus(
  input: ApiProvisioningTaskStatus,
): ProvisioningTaskStatus {
  return {
    taskId: input.task_id,
    status: input.status as ProvisioningTaskStatus["status"],
    error: input.error,
    snapshotId: input.snapshot_id,
    snapshotManifestHash: input.snapshot_manifest_hash,
    decisionTime: input.decision_time,
    instrumentCount: input.instrument_count,
    rowCount: input.row_count,
    labelSnapshotId: input.label_snapshot_id,
    labelSnapshotManifestHash: input.label_snapshot_manifest_hash,
    instruments: input.instruments,
  };
}

function mapLabelSnapshot(input: ApiLabelSnapshot): LabelSnapshotInfo {
  return {
    snapshotId: input.snapshot_id,
    manifestHash: input.manifest_hash,
    market: input.market,
    horizon: input.horizon,
    labelId: input.label_id,
    decisionTime: input.decision_time,
  };
}

export function mapResearchJob(input: ApiResearchJob): ResearchJob {
  const candidateLimit = input.budget.candidate_limit ?? 0;
  const llmTokenLimit = input.budget.llm_token_limit ?? 0;
  const cpuHours = input.budget.cpu_hours ?? 0;
  const wallClockMinutes = input.budget.wall_clock_minutes ?? 0;
  return {
    id: input.id,
    version: input.version ?? String(input.resource_version ?? 0),
    title: input.title,
    market: input.market,
    environment: input.environment,
    state: input.state,
    owner: input.owner,
    currentStage: input.current_stage ?? null,
    budget: {
      candidateLimit,
      llmTokenLimit,
      cpuHours,
      wallClockMinutes,
    },
    budgetUsed: input.budget_used
      ? {
          candidates: input.budget_used.candidates ?? 0,
          llmTokens: input.budget_used.llm_tokens ?? 0,
          cpuHours: input.budget_used.cpu_hours ?? 0,
          wallClockMinutes: input.budget_used.wall_clock_minutes ?? 0,
        }
      : null,
    latestAttempt: input.latest_attempt
      ? {
          attempt: input.latest_attempt.attempt,
          state: input.latest_attempt.state,
          startedAt: input.latest_attempt.started_at,
          heartbeatAt: input.latest_attempt.heartbeat_at,
        }
      : null,
    snapshotRefs: input.snapshot_refs ?? [],
    policyVersion: input.policy_version ?? null,
    runFingerprint: input.run_fingerprint ?? null,
    experimentId: input.experiment_id ?? input.latest_experiment_id ?? null,
    freshness: input.freshness
      ? {
          asOf: input.freshness.as_of,
          isStale: input.freshness.is_stale,
          staleReason: input.freshness.stale_reason,
        }
      : null,
    blockers: input.blockers ?? [],
    allowedActions: input.allowed_actions ?? ["VIEW"],
    updatedAt: input.updated_at,
  };
}

export function mapExperiment(input: ApiExperiment): Experiment {
  return {
    id: input.id,
    projectId: input.project_id,
    researchJobId: input.research_job_id,
    briefVersionId: input.brief_version_id,
    market: input.market,
    state: input.state,
    resourceVersion: input.resource_version,
    specHash: input.spec_hash,
    factorIrHash: input.factor_ir_hash,
    snapshotId: input.snapshot_id,
    snapshotManifestHash: input.snapshot_manifest_hash,
    factorIr: input.factor_ir ? mapFactorIr(input.factor_ir) : null,
    decisionTime: input.decision_time ?? null,
    randomSeed: input.random_seed ?? null,
    latestRunId: input.latest_run_id ?? null,
    createdAt: input.created_at,
    createdBy: input.created_by,
  };
}

function mapFactorIr(input: ApiFactorIR): FactorIR {
  return {
    factorId: input.factor_id,
    version: input.version,
    marketScope: {
      market: input.market_scope.market,
      frequency: input.market_scope.frequency,
      universeRef: input.market_scope.universe_ref,
    },
    decisionClock: {
      signalTime: input.decision_clock.signal_time,
      earliestTradeTime: input.decision_clock.earliest_trade_time,
    },
    inputs: input.inputs.map((item) => ({
      alias: item.alias,
      fieldRef: item.field_ref,
      dataType: item.data_type,
      unit: item.unit,
      availableTimeRule: item.available_time_rule,
    })),
    expression: input.expression,
  };
}

export function mapExperimentRun(input: ApiExperimentRun): ExperimentRun {
  return {
    id: input.id,
    experimentId: input.experiment_id,
    market: input.market,
    state: input.state,
    runFingerprint: input.run_fingerprint,
    attemptCount: input.attempt_count,
    validationSummary: input.validation_summary
      ? {
          observationCount: input.validation_summary.observation_count,
          finiteCount: input.validation_summary.finite_count,
          missingCount: input.validation_summary.missing_count,
          coverageRatio: input.validation_summary.coverage_ratio,
          minimum: input.validation_summary.minimum,
          maximum: input.validation_summary.maximum,
          mean: input.validation_summary.mean,
        }
      : null,
    invariance: input.invariance
      ? {
          futureTruncationPassed: input.invariance.future_truncation_passed,
          sentinelIsolationPassed: input.invariance.sentinel_isolation_passed,
          baselineOutputHash: input.invariance.baseline_output_hash,
          futureTruncationOutputHash:
            input.invariance.future_truncation_output_hash,
          sentinelIsolationOutputHash:
            input.invariance.sentinel_isolation_output_hash,
        }
      : null,
    createdAt: input.created_at,
    updatedAt: input.updated_at,
  };
}

export function mapExperimentArtifacts(
  input: ApiExperimentArtifacts,
): ExperimentArtifacts {
  return {
    items: input.items.map((item) => ({
      contentHash: item.content_hash,
      artifactType: item.artifact_type,
      schemaVersion: item.schema_version,
      sizeBytes: item.size_bytes,
      mediaType: item.media_type,
      domainHash: item.domain_hash,
    })),
    lineage: input.lineage.map((item) => ({
      edgeHash: item.edge_hash,
      sourceArtifactHash: item.source_artifact_hash,
      targetArtifactHash: item.target_artifact_hash,
      relation: item.relation,
    })),
  };
}

export function mapFactorValidationReport(
  input: ApiFactorValidationReport,
): FactorValidationReport {
  return {
    policyId: input.policy_id,
    policyHash: input.policy_hash,
    labelId: input.label_id,
    labelHash: input.label_hash,
    factorArtifactHash: input.factor_artifact_hash,
    dataQuality: {
      observationCount: input.data_quality.observation_count,
      finiteCount: input.data_quality.finite_count,
      coverageRatio: input.data_quality.coverage_ratio,
      constantRatio: input.data_quality.constant_ratio,
    },
    predictivePower: {
      meanPearsonIc: input.predictive_power.mean_pearson_ic,
      meanRankIc: input.predictive_power.mean_rank_ic,
      icir: input.predictive_power.icir,
      nwT: input.predictive_power.nw_t,
      icDecay: input.predictive_power.ic_decay.map((item) => ({
        horizon: item.horizon,
        meanIc: item.mean_ic,
      })),
      quantileReturns: input.predictive_power.quantile_returns.map((item) => ({
        quantile: item.quantile,
        meanReturn: item.mean_return,
      })),
      topBottomSpread: input.predictive_power.top_bottom_spread,
      monotonic: input.predictive_power.monotonic,
    },
  };
}

export function mapIndependence(input: ApiIndependence): IndependenceSummary {
  return {
    runId: input.run_id,
    outputHash: input.output_hash,
    baselineIc: input.baseline_ic,
    orthogonalizedIc: input.orthogonalized_ic,
    maxAbsCorrelation: input.max_abs_correlation,
    replicatedRiskFactor: input.replicated_risk_factor,
    pairwise: (input.report?.pairwise ?? []).map((item) => ({
      factorIrHash: item.factor_ir_hash,
      pearson: item.pearson,
      spearman: item.spearman,
    })),
  };
}

export function mapPromotion(input: ApiPromotion): PromotionSummary {
  return {
    runId: input.run_id,
    outputHash: input.output_hash,
    factorIrHash: input.factor_ir_hash,
    policyId: input.policy_id,
    disposition: input.disposition as PromotionSummary["disposition"],
    totalScore: input.total_score,
    gates: input.report?.gates ?? [],
    componentScores: input.report?.component_scores ?? [],
    rationale: input.report?.rationale ?? "",
  };
}

export function mapAlphaPoolFactor(input: ApiAlphaPoolFactor): AlphaPoolFactor {
  return {
    factorIrHash: input.factor_ir_hash,
    factorId: input.factor_id ?? null,
    instruments: input.instruments ?? [],
    dataStart: input.data_start ?? null,
    dataEnd: input.data_end ?? null,
    direction: input.direction,
    market: input.market as AlphaPoolFactor["market"],
    universe: input.universe,
    horizon: input.horizon,
    policyId: input.policy_id,
    riskPremium: input.risk_premium,
    lifecycleState: input.lifecycle_state,
    oosIc: input.oos_ic,
  };
}

export function mapBacktestResult(input: ApiBacktestResult): BacktestResult {
  return {
    factorIrHash: input.factor_ir_hash,
    instrumentIds: input.instrument_ids,
    start: input.start,
    end: input.end,
    frequency: input.frequency ?? "1d",
    dataSource: input.data_source ?? "snapshot",
    artifactClass: input.artifact_class ?? null,
    initialCash: input.initial_cash,
    lotSize: input.lot_size,
    grossOfFees: input.gross_of_fees,
    metrics: {
      totalReturn: input.metrics.total_return,
      sharpe: input.metrics.sharpe,
      maxDrawdown: input.metrics.max_drawdown,
      tradeCount: input.metrics.trade_count,
    },
    equityCurve: input.equity_curve,
    trades: (input.trades ?? []).map((trade) => ({
      time: trade.time,
      instrumentId: trade.instrument_id,
      side: trade.side,
      quantity: trade.quantity,
      price: trade.price,
      commission: trade.commission,
    })),
    positions: (input.positions ?? []).map((position) => ({
      instrumentId: position.instrument_id,
      entry: position.entry,
      peakQty: position.peak_qty,
      avgPxOpen: position.avg_px_open,
      avgPxClose: position.avg_px_close,
      realizedPnl: position.realized_pnl,
      openedAt: position.opened_at,
      closedAt: position.closed_at,
    })),
    backtestHash: input.backtest_hash,
  };
}

export function mapStrategyAttachmentToApi(attachment: StrategyAttachment): {
  name: string;
  kind: "text" | "image";
  extracted_text: string;
  object_key: string;
} {
  return {
    name: attachment.name,
    kind: attachment.kind,
    extracted_text: attachment.extractedText,
    object_key: attachment.objectKey ?? "",
  };
}

export function mapStrategyDraft(input: ApiStrategyDraft): StrategyDraft {
  return {
    id: input.id,
    market: input.market,
    kind: input.kind,
    stage: input.stage,
    state: input.state,
    title: input.title,
    explanation: input.explanation,
    question: input.question,
    code: input.code,
    ready: input.ready,
    instrumentIds: input.instrument_ids,
    frequency: input.frequency,
    backtestPlan:
      input.backtest_plan === null
        ? null
        : {
            timeframes: input.backtest_plan.timeframes,
            trendTimeframe: input.backtest_plan.trend_timeframe,
            execTimeframe: input.backtest_plan.exec_timeframe,
            start: input.backtest_plan.start,
            end: input.backtest_plan.end,
            rationale: input.backtest_plan.rationale,
          },
    codeTestResult: input.code_test_result
      ? {
          passed: input.code_test_result.passed,
          exitCode: input.code_test_result.exit_code,
          stderr: input.code_test_result.stderr,
          durationMs: input.code_test_result.duration_ms,
        }
      : null,
    backtestResults: (input.backtest_results ?? []).map((entry) => ({
      backtestHash: entry.backtest_hash,
      start: entry.start,
      end: entry.end,
      frequency: entry.frequency,
      metrics: entry.metrics
        ? {
            totalReturn: entry.metrics.total_return,
            sharpe: entry.metrics.sharpe,
            maxDrawdown: entry.metrics.max_drawdown,
            tradeCount: entry.metrics.trade_count,
          }
        : null,
      ranAt: entry.ran_at,
    })),
    paperBinding: input.paper_binding
      ? {
          accountId: input.paper_binding.account_id,
          publishedAt: input.paper_binding.published_at,
        }
      : null,
    contentHash: input.content_hash,
    resourceVersion: input.resource_version,
    savedVersions: (input.saved_versions ?? []).map((version) => ({
      version: version.version,
      hash: version.hash,
      state: version.state,
      title: version.title,
      savedAt: version.saved_at,
    })),
    createdAt: input.created_at,
    updatedAt: input.updated_at,
    messages: input.messages?.map((message) => ({
      role: message.role,
      content: message.content,
      attachments: (message.attachments ?? []).map((attachment) => ({
        name: attachment.name,
        kind: attachment.kind,
        extractedText: attachment.extracted_text,
      })),
    })),
  };
}

export function mapStrategyBacktestResult(
  input: ApiStrategyBacktestResult,
): StrategyBacktestResult {
  return {
    instrumentIds: input.instrument_ids,
    start: input.start,
    end: input.end,
    frequency: input.frequency,
    initialCash: input.initial_cash,
    grossOfFees: input.gross_of_fees,
    venueSpec:
      input.venue_spec === null || input.venue_spec === undefined
        ? null
        : {
            market: input.venue_spec.market,
            costBasis: input.venue_spec.cost_basis,
            feeModel: input.venue_spec.fee_model,
            fillModel: input.venue_spec.fill_model,
            latencyModel: input.venue_spec.latency_model,
            randomSeed: input.venue_spec.random_seed,
            priceProtectionPoints: input.venue_spec.price_protection_points,
          },
    metrics: {
      totalReturn: input.metrics.total_return,
      sharpe: input.metrics.sharpe,
      maxDrawdown: input.metrics.max_drawdown,
      tradeCount: input.metrics.trade_count,
    },
    equityCurve: input.equity_curve,
    trades: (input.trades ?? []).map((trade) => ({
      time: trade.time,
      instrumentId: trade.instrument_id,
      side: trade.side,
      quantity: trade.quantity,
      price: trade.price,
      commission: trade.commission,
    })),
    positions: (input.positions ?? []).map((position) => ({
      instrumentId: position.instrument_id,
      entry: position.entry,
      peakQty: position.peak_qty,
      avgPxOpen: position.avg_px_open,
      avgPxClose: position.avg_px_close,
      realizedPnl: position.realized_pnl,
      openedAt: position.opened_at,
      closedAt: position.closed_at,
    })),
    backtestHash: input.backtest_hash,
    error: input.error,
  };
}

export function mapStrategyDataStatus(
  input: ApiStrategyDataStatus,
): StrategyDataStatus {
  const mapEntry = (
    entry: { rows: number; first_event: string; last_event: string } | null,
  ) =>
    entry === null
      ? null
      : {
          rows: entry.rows,
          firstEvent: entry.first_event,
          lastEvent: entry.last_event,
        };
  return {
    instrumentIds: input.instrument_ids,
    frequencies: input.frequencies,
    ready: input.ready,
    items: input.items.map((item) => ({
      instrumentId: item.instrument_id,
      available: item.available,
      daily: mapEntry(item.daily),
      minute: mapEntry(item.minute),
      checks: item.checks.map((check) => ({
        frequency: check.frequency,
        available: check.available,
        required: mapEntry(check.required),
      })),
    })),
  };
}

export function mapMarketDataCoverageEntry(
  input: ApiMarketDataCoverageEntry,
): MarketDataCoverageEntry {
  return {
    instrumentId: input.instrument_id,
    fieldPrefix: input.field_prefix,
    sourceId: input.source_id,
    licenseTag: input.license_tag,
    artifactClass: input.artifact_class,
    rowCount: input.row_count,
    firstEvent: input.first_event,
    lastEvent: input.last_event,
  };
}

export function mapExecutionState(input: ApiExecutionState): ExecutionState {
  return {
    stateId: input.state_id,
    killSwitchState: input.kill_switch_state,
    trippedBy: input.tripped_by,
    trippedAt: input.tripped_at,
    reason: input.reason,
    shadowPositions: input.shadow_positions,
    paperPositions: input.paper_positions,
  };
}

export function mapPaperAccount(input: ApiPaperAccount): PaperAccount {
  return {
    id: input.id,
    owner: input.owner,
    draftId: input.draft_id,
    artifactAddress: input.artifact_address,
    contentHash: input.content_hash,
    market: input.market,
    instrumentIds: input.instrument_ids,
    frequency: input.frequency,
    initialCash: input.initial_cash,
    state: input.state,
    createdAt: input.created_at,
    updatedAt: input.updated_at,
  };
}

export function mapPaperOrder(input: ApiPaperOrder): PaperOrder {
  return {
    id: input.id,
    instrumentId: input.instrument_id,
    side: input.side,
    quantity: input.quantity,
    orderClock: input.order_clock,
    status: input.status,
    rejectReason: input.reject_reason,
    filledQty: input.filled_qty,
    avgPx: input.avg_px,
    createdAt: input.created_at,
  };
}

export function mapPaperFill(input: ApiPaperFill): PaperFill {
  return {
    id: input.id,
    orderId: input.order_id,
    tradeTs: input.trade_ts,
    price: input.price,
    quantity: input.quantity,
    fee: input.fee,
    notional: input.notional,
  };
}

export function mapPaperPosition(input: ApiPaperPosition): PaperPosition {
  return {
    instrumentId: input.instrument_id,
    quantity: input.quantity,
    avgPx: input.avg_px,
    updatedAt: input.updated_at,
  };
}

export function mapPaperEquityRow(input: ApiPaperEquityRow): PaperEquityRow {
  return {
    tradeDate: input.trade_date,
    equity: input.equity,
    cash: input.cash,
    marginUsed: input.margin_used,
    drawdown: input.drawdown,
  };
}

export function mapPaperDriftReport(
  input: ApiPaperDriftReport,
): PaperDriftReport {
  return {
    schemaVersion: input.schema_version,
    points: input.points.map((point) => ({
      date: point.date,
      backtestEquity: point.backtest_equity,
      paperEquity: point.paper_equity,
      diff: point.diff,
    })),
    commonDays: input.common_days,
    paperDays: input.paper_days,
    backtestDays: input.backtest_days,
    maxAbsDiff: input.max_abs_diff,
    costBasis: input.cost_basis,
    backtestHash: input.backtest_hash,
  };
}

export function mapSession(input: ApiSession): Session {
  return {
    actor: input.actor,
    roles: input.roles,
    capabilities: input.capabilities as Capability[],
    environments: input.environments as Environment[],
    markets: input.markets as MarketId[],
  };
}

export function mapResearchBrief(input: ApiResearchBrief): ResearchBrief {
  return {
    id: input.id,
    jobId: input.job_id,
    version: input.version,
    resourceVersion: input.resource_version,
    status: input.status,
    hypothesis: input.hypothesis,
    economicMechanism: input.economic_mechanism,
    expectedDirection: input.expected_direction,
    falsificationConditions: input.falsification_conditions,
    allowedDataDomains: input.allowed_data_domains,
    forbiddenDataDomains: input.forbidden_data_domains,
    constraints: input.constraints,
    evidenceRefIds: input.evidence_ref_ids,
    uncertainties: input.uncertainties,
    contentHash: input.content_hash,
    createdAt: input.created_at,
    createdBy: input.created_by,
    frozenAt: input.frozen_at,
  };
}

function commandMetadata(reason: string) {
  return {
    reason,
    parent_artifact_id: null,
    budget: {
      candidate_limit: 20,
      llm_token_limit: 120000,
      cpu_hours: 24,
      wall_clock_minutes: 60,
    },
    schema_version: "1.0",
  };
}

function mapBriefDraft(input: ApiBriefDraft): BriefDraftInput {
  return {
    hypothesis: input.hypothesis,
    economicMechanism: input.economic_mechanism,
    expectedDirection: input.expected_direction,
    falsificationConditions: input.falsification_conditions,
    allowedDataDomains: input.allowed_data_domains,
    forbiddenDataDomains: input.forbidden_data_domains,
    constraints: input.constraints,
    evidenceRefIds: input.evidence_ref_ids,
    uncertainties: input.uncertainties,
  };
}

function mapFactorExtraction(input: ApiFactorExtraction): FactorExtractionResult {
  return {
    brief: mapBriefDraft(input.brief),
    factorIr: input.factor_ir,
    explanation: input.explanation,
  };
}

function briefCommand(brief: BriefDraftInput) {
  return {
    hypothesis: brief.hypothesis,
    economic_mechanism: brief.economicMechanism,
    expected_direction: brief.expectedDirection,
    falsification_conditions: brief.falsificationConditions,
    allowed_data_domains: brief.allowedDataDomains,
    forbidden_data_domains: brief.forbiddenDataDomains,
    constraints: brief.constraints,
    evidence_ref_ids: brief.evidenceRefIds,
    uncertainties: brief.uncertainties,
  };
}

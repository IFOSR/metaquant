import type {
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
  PreregisterExperimentInput,
  PromotionSummary,
  ProvisionInput,
  ProvisionResult,
  ProvisioningTaskStatus,
  ResearchBrief,
  ResearchJob,
  RunBacktestInput,
  Session,
  FactorExtractionResult,
  FromPaperPipelineResult,
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

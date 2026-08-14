import type {
  CreateResearchJobInput,
  Experiment,
  ExperimentArtifacts,
  ExperimentRun,
  FactorValidationReport,
  IndependenceSummary,
  PreregisterExperimentInput,
  PromotionSummary,
  ResearchBrief,
  ResearchJob,
  Session,
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

export interface QuantApiClient {
  getSession(): Promise<Session>;
  listResearchJobs(): Promise<ResearchJob[]>;
  getResearchJob(id: string): Promise<ResearchJob>;
  listBriefVersions(jobId: string): Promise<ResearchBrief[]>;
  getBrief(id: string): Promise<ResearchBrief>;
  updateBrief(id: string, brief: ResearchBrief): Promise<ResearchBrief>;
  freezeBrief(id: string, resourceVersion?: number): Promise<ResearchBrief>;
  createResearchJob(input: CreateResearchJobInput): Promise<ResearchJob>;
  preregisterExperiment(input: PreregisterExperimentInput): Promise<Experiment>;
  getExperiment(id: string): Promise<Experiment>;
  runExperiment(id: string): Promise<ExperimentRun>;
  getExperimentRun(id: string): Promise<ExperimentRun>;
  getExperimentArtifacts(id: string): Promise<ExperimentArtifacts>;
  getExperimentValidation(id: string): Promise<FactorValidationReport>;
  getExperimentIndependence(id: string): Promise<IndependenceSummary>;
  getExperimentPromotion(id: string): Promise<PromotionSummary>;
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
    this.fetcher = options.fetcher ?? fetch;
    this.idempotencyKey = options.idempotencyKey ?? (() => crypto.randomUUID());
  }

  async getSession() {
    return structuredClone(this.session);
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
    latestRunId: input.latest_run_id ?? null,
    createdAt: input.created_at,
    createdBy: input.created_by,
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

function briefCommand(brief: ResearchBrief) {
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

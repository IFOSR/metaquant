import type {
  CreateResearchJobInput,
  Experiment,
  ExperimentArtifacts,
  ExperimentRun,
  PreregisterExperimentInput,
  ResearchBrief,
  ResearchJob,
  Session,
} from "./types";
import type { QuantApiClient } from "./api";

const session: Session = {
  actor: { id: "user_researcher_018", displayName: "Lin / Research" },
  roles: ["Researcher", "StrategyResearcher"],
  capabilities: [
    "research.jobs.read",
    "research.jobs.write",
    "research.briefs.write",
    "research.briefs.freeze",
    "research.experiments.read",
    "research.experiments.preregister",
    "research.experiments.run",
    "research.jobs.propose",
    "strategy.read",
  ],
  environments: ["RESEARCH"],
  markets: ["CN_A", "CN_COMMODITY_FUTURES"],
};

const jobs: ResearchJob[] = [
  {
    id: "rj_20260811_0042",
    version: "17",
    title: "期限结构与动量联合假设",
    market: "CN_COMMODITY_FUTURES",
    environment: "RESEARCH",
    state: "RUNNING",
    owner: "Lin / Research",
    currentStage: "VALIDATION_GATE_2",
    budget: {
      candidateLimit: 20,
      llmTokenLimit: 120000,
      cpuHours: 24,
      wallClockMinutes: 60,
    },
    budgetUsed: {
      candidates: 18,
      llmTokens: 84210,
      cpuHours: 11.8,
      wallClockMinutes: 37,
    },
    latestAttempt: {
      attempt: 3,
      state: "RUNNING",
      startedAt: "2026-08-11T09:18:00+08:00",
      heartbeatAt: "2026-08-11T09:55:32+08:00",
    },
    snapshotRefs: [
      "snapshot://cn-futures/eod/2026-08-08/v4",
      "rules://cn-futures/2026-08/v2",
    ],
    policyVersion: "validation-policy://cn-futures/1.2.0",
    runFingerprint: "sha256:7a45df0f…12bc",
    experimentId: "exp_futures_curve_0042",
    freshness: {
      asOf: "2026-08-11T09:55:32+08:00",
      isStale: false,
      staleReason: null,
    },
    blockers: [],
    allowedActions: ["VIEW", "SUBSCRIBE", "REQUEST_CANCEL"],
    updatedAt: "2026-08-11T09:55:32+08:00",
  },
  {
    id: "rj_20260810_0017",
    version: "8",
    title: "成交额冲击后的短期反转",
    market: "CN_A",
    environment: "RESEARCH",
    state: "BLOCKED_POLICY",
    owner: "Lin / Research",
    currentStage: "DATA_FEASIBILITY",
    budget: {
      candidateLimit: 12,
      llmTokenLimit: 80000,
      cpuHours: 12,
      wallClockMinutes: 30,
    },
    budgetUsed: {
      candidates: 12,
      llmTokens: 32100,
      cpuHours: 5.4,
      wallClockMinutes: 18,
    },
    latestAttempt: {
      attempt: 1,
      state: "FAILED",
      startedAt: "2026-08-10T14:06:00+08:00",
      heartbeatAt: "2026-08-10T14:24:00+08:00",
    },
    snapshotRefs: ["snapshot://cn-a/daily/2026-08-08/v2"],
    policyVersion: "data-policy://cn-a/pit/0.9.0",
    runFingerprint: null,
    experimentId: "exp_cn_a_reversal_0017",
    freshness: {
      asOf: "2026-08-10T14:24:00+08:00",
      isStale: true,
      staleReason: "Point-in-time membership source requires stewardship review.",
    },
    blockers: [
      {
        code: "DATA_LICENSE_PENDING",
        title: "PIT universe license is not approved",
        detail: "The job cannot enter formal research until the source is sealed.",
        responsibility: "DATA_STEWARD",
      },
    ],
    allowedActions: ["VIEW", "REQUEST_WAIVER"],
    updatedAt: "2026-08-10T14:24:00+08:00",
  },
];

const experiments: Experiment[] = [
  {
    id: "exp_futures_curve_0042",
    projectId: "local",
    researchJobId: "rj_20260811_0042",
    briefVersionId: "brief_0042_v1",
    market: "CN_COMMODITY_FUTURES",
    state: "PREREGISTERED",
    resourceVersion: 1,
    specHash: "sha256:9341f27d5b63f42b",
    factorIrHash: "sha256:35cf688eb668da12",
    snapshotId: "snapshot-cn-futures-20260808-v4",
    snapshotManifestHash: "sha256:1fd6ae705d1bf2f0",
    latestRunId: "run_futures_curve_0042",
    createdAt: "2026-08-12T02:14:00Z",
    createdBy: "user_researcher_018",
  },
  {
    id: "exp_cn_a_reversal_0017",
    projectId: "local",
    researchJobId: "rj_20260810_0017",
    briefVersionId: "brief_0017_v1",
    market: "CN_A",
    state: "PREREGISTERED",
    resourceVersion: 1,
    specHash: "sha256:6d631cff0f6b87a4",
    factorIrHash: "sha256:141dde47431fd22a",
    snapshotId: "snapshot-cn-a-20260808-v2",
    snapshotManifestHash: "sha256:9681a4a2369097d1",
    latestRunId: "run_cn_a_reversal_0017",
    createdAt: "2026-08-12T03:11:00Z",
    createdBy: "user_researcher_018",
  },
];

const runs: ExperimentRun[] = [
  {
    id: "run_futures_curve_0042",
    experimentId: "exp_futures_curve_0042",
    market: "CN_COMMODITY_FUTURES",
    state: "SUCCEEDED",
    runFingerprint: "sha256:7a45df0f90163e874d12bc",
    attemptCount: 1,
    validationSummary: {
      observationCount: 48240,
      finiteCount: 46791,
      missingCount: 1449,
      coverageRatio: 0.9699626865671642,
      minimum: -2.8471,
      maximum: 2.9014,
      mean: 0.0018,
    },
    invariance: {
      futureTruncationPassed: true,
      sentinelIsolationPassed: true,
      baselineOutputHash: "sha256:a749538e9f8bb77d",
      futureTruncationOutputHash: "sha256:a749538e9f8bb77d",
      sentinelIsolationOutputHash: "sha256:a749538e9f8bb77d",
    },
    createdAt: "2026-08-12T02:18:00Z",
    updatedAt: "2026-08-12T02:18:06Z",
  },
  {
    id: "run_cn_a_reversal_0017",
    experimentId: "exp_cn_a_reversal_0017",
    market: "CN_A",
    state: "NON_REPRODUCIBLE",
    runFingerprint: "sha256:07a2f19f1a8e4f330a9911",
    attemptCount: 2,
    validationSummary: null,
    invariance: {
      futureTruncationPassed: true,
      sentinelIsolationPassed: false,
      baselineOutputHash: "sha256:77ad9c10baseline",
      futureTruncationOutputHash: "sha256:77ad9c10baseline",
      sentinelIsolationOutputHash: "sha256:f013ac81mismatch",
    },
    createdAt: "2026-08-12T03:15:00Z",
    updatedAt: "2026-08-12T03:17:42Z",
  },
];

const artifactsByRun: Record<string, ExperimentArtifacts> = {
  run_futures_curve_0042: {
    items: [
      {
        contentHash: "sha256:38813ea3d0f77a48",
        artifactType: "FactorComputationArtifact",
        schemaVersion: "factor-computation/v1",
        sizeBytes: 1843210,
        mediaType: "application/json",
        domainHash: "sha256:a749538e9f8bb77d",
      },
      {
        contentHash: "sha256:8f6110ee453a3b5d",
        artifactType: "ValidationArtifact",
        schemaVersion: "factor-validation/v1",
        sizeBytes: 1842,
        mediaType: "application/json",
        domainHash: "sha256:61a115ead427332e",
      },
    ],
    lineage: [
      {
        edgeHash: "sha256:22dd0ac34a00dd61",
        sourceArtifactHash: "sha256:38813ea3d0f77a48",
        targetArtifactHash: "sha256:8f6110ee453a3b5d",
        relation: "VALIDATED_BY",
      },
    ],
  },
  run_cn_a_reversal_0017: {
    items: [],
    lineage: [],
  },
};

const briefs: ResearchBrief[] = [
  {
    id: "brief_0042_v1",
    jobId: "rj_20260811_0042",
    version: 1,
    resourceVersion: 3,
    status: "DRAFT",
    hypothesis:
      "期限结构的正向斜率与近端动量共同反映库存压力和风险补偿。",
    economicMechanism:
      "远月相对近月的定价差异在库存约束下持续，趋势确认减少单一期限结构的噪声。",
    expectedDirection: "POSITIVE",
    falsificationConditions: ["OOS 方向翻转", "换月后收益衰减超过 50%"],
    allowedDataDomains: ["settlement", "actual_contract_prices", "open_interest"],
    forbiddenDataDomains: ["revised_close", "future_constituents"],
    constraints: ["1d only", "no delivery", "three-day roll confirmation"],
    evidenceRefIds: [],
    uncertainties: [],
    contentHash: null,
    createdAt: "2026-08-11T09:12:00+08:00",
    createdBy: "user_researcher_018",
    frozenAt: null,
  },
];

export const mockClient: QuantApiClient = {
  async getSession() {
    return structuredClone(session);
  },
  async listResearchJobs() {
    return structuredClone(jobs);
  },
  async getResearchJob(id: string) {
    const job = jobs.find((item) => item.id === id);
    if (job) return structuredClone(job);
    return structuredClone({
      ...jobs[0],
      id,
      version: "1",
      title: "New research job",
      state: "READY" as const,
      currentStage: "BRIEF_FROZEN",
      budgetUsed: {
        candidates: 0,
        llmTokens: 0,
        cpuHours: 0,
        wallClockMinutes: 0,
      },
      latestAttempt: {
        attempt: 1,
        state: "QUEUED" as const,
        startedAt: "",
        heartbeatAt: "",
      },
      runFingerprint: null,
      experimentId: null,
      updatedAt: new Date().toISOString(),
    });
  },
  async listBriefVersions(jobId: string) {
    return structuredClone(briefs.filter((brief) => brief.jobId === jobId));
  },
  async getBrief(id: string) {
    return structuredClone(briefs.find((brief) => brief.id === id) ?? briefs[0]);
  },
  async updateBrief(id: string, patch: Partial<ResearchBrief>) {
    const brief = briefs.find((item) => item.id === id) ?? briefs[0];
    Object.assign(brief, patch, { resourceVersion: brief.resourceVersion + 1 });
    return structuredClone(brief);
  },
  async freezeBrief(id: string, _resourceVersion?: number) {
    const brief = briefs.find((item) => item.id === id) ?? briefs[0];
    Object.assign(brief, {
      status: "FROZEN",
      resourceVersion: brief.resourceVersion + 1,
      contentHash: "sha256:brief-0042…a81e",
      frozenAt: new Date().toISOString(),
    });
    return structuredClone(brief);
  },
  async createResearchJob(input: CreateResearchJobInput) {
    const id = `rj_local_${Date.now()}`;
    const job = {
      ...jobs[0],
      id,
      title: input.market === "CN_A" ? "新建 A 股研究任务" : "新建期货研究任务",
      market: input.market,
      state: "READY" as const,
      currentStage: "BRIEF_FROZEN",
      version: "1",
      updatedAt: new Date().toISOString(),
    };
    jobs.unshift(job);
    return structuredClone(job);
  },
  async preregisterExperiment(input: PreregisterExperimentInput) {
    const experiment: Experiment = {
      id: `exp_local_${experiments.length + 1}`,
      projectId: "local",
      researchJobId: input.researchJobId,
      briefVersionId: input.briefVersionId,
      market:
        jobs.find((job) => job.id === input.researchJobId)?.market ?? "CN_A",
      state: "PREREGISTERED",
      resourceVersion: 1,
      specHash: "sha256:mock-spec",
      factorIrHash: "sha256:mock-factor-ir",
      snapshotId: input.snapshotId,
      snapshotManifestHash: input.snapshotManifestHash,
      latestRunId: null,
      createdAt: "2026-08-13T00:00:00Z",
      createdBy: session.actor.id,
    };
    experiments.push(experiment);
    return structuredClone(experiment);
  },
  async getExperiment(id: string) {
    const experiment = experiments.find((item) => item.id === id);
    if (!experiment) throw new Error(`Unknown mock experiment: ${id}`);
    return structuredClone(experiment);
  },
  async runExperiment(id: string) {
    const experiment = experiments.find((item) => item.id === id);
    if (!experiment) throw new Error(`Unknown mock experiment: ${id}`);
    const run: ExperimentRun = {
      id: `run_local_${runs.length + 1}`,
      experimentId: id,
      market: experiment.market,
      state: "SUCCEEDED",
      runFingerprint: "sha256:mock-run",
      attemptCount: 1,
      validationSummary: {
        observationCount: 0,
        finiteCount: 0,
        missingCount: 0,
        coverageRatio: 0,
        minimum: null,
        maximum: null,
        mean: null,
      },
      invariance: {
        futureTruncationPassed: true,
        sentinelIsolationPassed: true,
        baselineOutputHash: "sha256:mock-output",
        futureTruncationOutputHash: "sha256:mock-output",
        sentinelIsolationOutputHash: "sha256:mock-output",
      },
      createdAt: "2026-08-13T00:01:00Z",
      updatedAt: "2026-08-13T00:01:00Z",
    };
    runs.push(run);
    experiment.latestRunId = run.id;
    artifactsByRun[run.id] = { items: [], lineage: [] };
    return structuredClone(run);
  },
  async getExperimentRun(id: string) {
    const run = runs.find((item) => item.id === id);
    if (!run) throw new Error(`Unknown mock experiment run: ${id}`);
    return structuredClone(run);
  },
  async getExperimentArtifacts(id: string) {
    return structuredClone(artifactsByRun[id] ?? { items: [], lineage: [] });
  },
  async getExperimentValidation(id: string) {
    return {
      policyId: "policy://cn-a-daily-factor/v1",
      policyHash: "0".repeat(64),
      labelId: "label.cn_a.forward_5d",
      labelHash: "0".repeat(64),
      factorArtifactHash: "sha256:factor-computation",
      dataQuality: {
        observationCount: 46791,
        finiteCount: 46791,
        coverageRatio: 0.97,
        constantRatio: 0.12,
      },
      predictivePower: {
        meanPearsonIc: 0.042,
        meanRankIc: 0.038,
        icir: 0.55,
        nwT: 3.1,
        icDecay: [{ horizon: 5, meanIc: 0.042 }],
        quantileReturns: [
          { quantile: 1, meanReturn: -0.01 },
          { quantile: 2, meanReturn: 0.0 },
          { quantile: 3, meanReturn: 0.012 },
        ],
        topBottomSpread: 0.022,
        monotonic: true,
      },
    };
  },
  async getExperimentIndependence(id: string) {
    return {
      runId: id,
      outputHash: "0".repeat(64),
      baselineIc: 0.042,
      orthogonalizedIc: 0.031,
      maxAbsCorrelation: 0.38,
      replicatedRiskFactor: false,
      pairwise: [
        { factorIrHash: "a".repeat(64), pearson: 0.31, spearman: 0.28 },
        { factorIrHash: "b".repeat(64), pearson: 0.12, spearman: 0.09 },
      ],
    };
  },
};

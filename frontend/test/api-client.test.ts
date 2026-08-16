import { describe, expect, it, vi } from "vitest";

import {
  HttpQuantApiClient,
  QuantApiProblem,
  mapExperiment,
  mapExperimentArtifacts,
  mapExperimentRun,
  mapResearchBrief,
  mapResearchJob,
} from "../lib/api";
import type { Session } from "../lib/types";

const session: Session = {
  actor: { id: "researcher-1", displayName: "Researcher One" },
  roles: ["Researcher"],
  capabilities: [
    "research.jobs.read",
    "research.jobs.write",
    "research.briefs.write",
    "research.briefs.freeze",
  ],
  environments: ["RESEARCH"],
  markets: ["CN_A", "CN_COMMODITY_FUTURES"],
};

function response(
  body: unknown,
  init: { status?: number; headers?: Record<string, string> } = {},
) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: {
      "Content-Type": "application/json",
      ...init.headers,
    },
  });
}

function apiClient(fetcher: typeof fetch) {
  return new HttpQuantApiClient({
    baseUrl: "http://api.test/v1",
    accessToken: "test-researcher",
    session,
    fetcher,
    idempotencyKey: () => "idem-0000000000000001",
  });
}

describe("HTTP QuantApiClient", () => {
  it("maps list responses and sends the bearer token", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      response({
        items: [
          {
            id: "rj_1",
            resource_version: 2,
            title: "CN_A 20TD research",
            market: "CN_A",
            environment: "RESEARCH",
            state: "READY",
            owner: "researcher-1",
            universe_ref: "universe://csi500/pit",
            frequency: "1d",
            decision_clock: "T_CLOSE",
            trade_clock: "T_PLUS_1_OPEN",
            settlement_clock: null,
            exchange_scope: [],
            contract_selection: null,
            roll_policy: null,
            horizon: "20TD",
            research_brief_version_id: "brief://seed",
            budget: {
              candidate_limit: 10,
              llm_token_limit: 1000,
              cpu_hours: 2,
              wall_clock_minutes: 30,
            },
            created_at: "2026-08-12T01:00:00Z",
            updated_at: "2026-08-12T02:00:00Z",
          },
        ],
        next_cursor: null,
      }),
    );

    const jobs = await apiClient(fetcher).listResearchJobs();

    expect(jobs[0]).toMatchObject({
      id: "rj_1",
      version: "2",
      market: "CN_A",
      environment: "RESEARCH",
      budget: {
        candidateLimit: 10,
        llmTokenLimit: 1000,
        cpuHours: 2,
        wallClockMinutes: 30,
      },
    });
    expect(fetcher).toHaveBeenCalledWith(
      "http://api.test/v1/research-jobs",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer test-researcher",
          Accept: "application/json, application/problem+json",
        }),
      }),
    );
  });

  it("can use a same-origin proxy without exposing a browser bearer token", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValue(response({ items: [], next_cursor: null }));
    const client = new HttpQuantApiClient({
      baseUrl: "/api/quant/v1",
      session,
      fetcher,
    });

    await client.listResearchJobs();

    expect(fetcher).toHaveBeenCalledWith(
      "/api/quant/v1/research-jobs",
      expect.objectContaining({
        headers: expect.not.objectContaining({
          Authorization: expect.anything(),
        }),
      }),
    );
  });

  it("creates a job with a snake_case command and follows the receipt", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        response(
          {
            command_id: "cmd_1",
            status: "ACCEPTED",
            resource_id: "rj_2",
            submitted_at: "2026-08-12T02:00:00Z",
          },
          { status: 202 },
        ),
      )
      .mockResolvedValueOnce(
        response(
          {
            id: "rj_2",
            resource_version: 1,
            title: "CN_COMMODITY_FUTURES 5TD research",
            market: "CN_COMMODITY_FUTURES",
            environment: "RESEARCH",
            state: "READY",
            owner: "researcher-1",
            universe_ref: "futures:liquid-initial",
            frequency: "1d",
            decision_clock: "T close",
            trade_clock: "T+1 open",
            settlement_clock: "T+1 settlement",
            exchange_scope: ["SHFE"],
            contract_selection: "ACTUAL_CONTRACTS_ONLY",
            roll_policy: "roll://v1",
            horizon: "5TD",
            research_brief_version_id: "brief_1",
            budget: {
              candidate_limit: 20,
              llm_token_limit: 120000,
              cpu_hours: 24,
              wall_clock_minutes: 60,
            },
            created_at: "2026-08-12T02:00:00Z",
            updated_at: "2026-08-12T02:00:00Z",
          },
          { headers: { ETag: '"1"' } },
        ),
      );

    const job = await apiClient(fetcher).createResearchJob({
      market: "CN_COMMODITY_FUTURES",
      environment: "RESEARCH",
      universeRef: "futures:liquid-initial",
      frequency: "1d",
      decisionClock: "T close",
      tradeClock: "T+1 open",
      settlementClock: "T+1 settlement",
      exchangeScope: ["SHFE"],
      contractSelection: "ACTUAL_CONTRACTS_ONLY",
      rollPolicy: "roll://v1",
      horizon: "5TD",
      briefVersionId: "brief_1",
    });

    const [, createInit] = fetcher.mock.calls[0];
    expect(createInit?.headers).toEqual(
      expect.objectContaining({
        Authorization: "Bearer test-researcher",
        "Content-Type": "application/json",
        "Idempotency-Key": "idem-0000000000000001",
      }),
    );
    expect(JSON.parse(String(createInit?.body))).toMatchObject({
      market: "CN_COMMODITY_FUTURES",
      environment: "RESEARCH",
      universe_ref: "futures:liquid-initial",
      settlement_clock: "T+1 settlement",
      exchange_scope: ["SHFE"],
      contract_selection: "ACTUAL_CONTRACTS_ONLY",
      roll_policy: "roll://v1",
      research_brief_version_id: "brief_1",
      metadata: {
        schema_version: "1.0",
        budget: { candidate_limit: 20 },
      },
    });
    expect(fetcher.mock.calls[1][0]).toBe("http://api.test/v1/research-jobs/rj_2");
    expect(job.id).toBe("rj_2");
  });

  it("uses the resource version as If-Match and reloads updated briefs", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        response(
          {
            command_id: "cmd_2",
            status: "ACCEPTED",
            resource_id: "brief_1",
            submitted_at: "2026-08-12T02:00:00Z",
          },
          { status: 202 },
        ),
      )
      .mockResolvedValueOnce(
        response(
          {
            id: "brief_1",
            job_id: "rj_1",
            version: 1,
            resource_version: 4,
            status: "DRAFT",
            hypothesis: "Updated hypothesis",
            economic_mechanism: "A real mechanism",
            expected_direction: "POSITIVE",
            falsification_conditions: ["OOS direction flips"],
            allowed_data_domains: ["formal.market.eod"],
            forbidden_data_domains: [],
            constraints: ["daily only"],
            evidence_ref_ids: ["evidence://paper-1"],
            uncertainties: ["publication lag"],
            content_hash: null,
            created_at: "2026-08-12T01:00:00Z",
            created_by: "researcher-1",
            frozen_at: null,
            frozen_by: null,
          },
          { headers: { ETag: '"4"' } },
        ),
      );
    const brief = mapResearchBrief({
      id: "brief_1",
      job_id: "rj_1",
      version: 1,
      resource_version: 3,
      status: "DRAFT",
      hypothesis: "Original hypothesis",
      economic_mechanism: "A real mechanism",
      expected_direction: "POSITIVE",
      falsification_conditions: ["OOS direction flips"],
      allowed_data_domains: ["formal.market.eod"],
      forbidden_data_domains: [],
      constraints: ["daily only"],
      evidence_ref_ids: ["evidence://paper-1"],
      uncertainties: ["publication lag"],
      content_hash: null,
      created_at: "2026-08-12T01:00:00Z",
      created_by: "researcher-1",
      frozen_at: null,
      frozen_by: null,
    });

    const updated = await apiClient(fetcher).updateBrief(brief.id, {
      ...brief,
      hypothesis: "Updated hypothesis",
    });

    const [, updateInit] = fetcher.mock.calls[0];
    expect(updateInit?.headers).toEqual(
      expect.objectContaining({
        "Idempotency-Key": "idem-0000000000000001",
        "If-Match": '"3"',
      }),
    );
    expect(updated.resourceVersion).toBe(4);
    expect(updated.hypothesis).toBe("Updated hypothesis");
    expect(updated.evidenceRefIds).toEqual(["evidence://paper-1"]);
    expect(updated.uncertainties).toEqual(["publication lag"]);
    expect(JSON.parse(String(updateInit?.body)).brief).toMatchObject({
      evidence_ref_ids: ["evidence://paper-1"],
      uncertainties: ["publication lag"],
    });
  });

  it("parses application/problem+json into a typed error", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      response(
        {
          type: "about:blank",
          title: "Precondition failed",
          status: 412,
          detail: "The resource changed.",
          code: "PRECONDITION_FAILED",
        },
        {
          status: 412,
          headers: { "Content-Type": "application/problem+json" },
        },
      ),
    );

    await expect(apiClient(fetcher).getResearchJob("rj_stale")).rejects.toEqual(
      expect.objectContaining<Partial<QuantApiProblem>>({
        name: "QuantApiProblem",
        status: 412,
        code: "PRECONDITION_FAILED",
        detail: "The resource changed.",
      }),
    );
  });

  it("preregisters and runs an experiment through command receipts", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        response(
          {
            command_id: "cmd_preregister",
            status: "ACCEPTED",
            resource_id: "exp_1",
            submitted_at: "2026-08-13T01:00:00Z",
          },
          { status: 202 },
        ),
      )
      .mockResolvedValueOnce(
        response({
          id: "exp_1",
          project_id: "local",
          research_job_id: "rj_1",
          brief_version_id: "brief_1",
          market: "CN_A",
          state: "PREREGISTERED",
          resource_version: 1,
          spec_hash: "spec-hash",
          factor_ir_hash: "ir-hash",
          snapshot_id: "snapshot-1",
          snapshot_manifest_hash: "snapshot-hash",
          latest_run_id: null,
          created_at: "2026-08-13T01:00:00Z",
          created_by: "researcher-1",
        }),
      )
      .mockResolvedValueOnce(
        response(
          {
            command_id: "cmd_run",
            status: "ACCEPTED",
            resource_id: "run_1",
            submitted_at: "2026-08-13T01:01:00Z",
          },
          { status: 202 },
        ),
      )
      .mockResolvedValueOnce(
        response({
          id: "run_1",
          experiment_id: "exp_1",
          market: "CN_A",
          state: "SUCCEEDED",
          run_fingerprint: "run-fingerprint",
          attempt_count: 1,
          validation_summary: {
            observation_count: 100,
            finite_count: 96,
            missing_count: 4,
            coverage_ratio: 0.96,
            minimum: -1,
            maximum: 1,
            mean: 0,
          },
          invariance: {
            future_truncation_passed: true,
            sentinel_isolation_passed: true,
            baseline_output_hash: "base",
            future_truncation_output_hash: "base",
            sentinel_isolation_output_hash: "base",
          },
          created_at: "2026-08-13T01:01:00Z",
          updated_at: "2026-08-13T01:01:01Z",
        }),
      );
    const client = apiClient(fetcher);

    const experiment = await client.preregisterExperiment({
      researchJobId: "rj_1",
      briefVersionId: "brief_1",
      decisionTime: "2026-08-12T15:30:00Z",
      randomSeed: 42,
      resourceBudget: {
        cpuSeconds: 3600,
        wallClockSeconds: 1800,
        memoryMb: 2048,
        maxObservations: 100000,
      },
      factorIr: { schema_version: "factor-ir/v1" },
      snapshotId: "snapshot-1",
      snapshotManifestHash: "f".repeat(64),
    });
    const run = await client.runExperiment("exp_1");

    expect(experiment.state).toBe("PREREGISTERED");
    expect(run.state).toBe("SUCCEEDED");
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      "http://api.test/v1/experiments:preregister",
      "http://api.test/v1/experiments/exp_1",
      "http://api.test/v1/experiments/exp_1:run",
      "http://api.test/v1/experiment-runs/run_1",
    ]);
    const preregisterBody = JSON.parse(
      String(fetcher.mock.calls[0][1]?.body),
    ) as Record<string, unknown>;
    expect(Object.keys(preregisterBody).sort()).toEqual([
      "brief_version_id",
      "decision_time",
      "factor_ir",
      "metadata",
      "random_seed",
      "research_job_id",
      "resource_budget",
      "snapshot_id",
      "snapshot_manifest_hash",
    ]);
    expect(preregisterBody).toMatchObject({
      research_job_id: "rj_1",
      brief_version_id: "brief_1",
      random_seed: 42,
      resource_budget: {
        cpu_seconds: 3600,
        max_observations: 100000,
      },
      snapshot_id: "snapshot-1",
      snapshot_manifest_hash: "f".repeat(64),
    });
    expect(preregisterBody).not.toHaveProperty("snapshot");
    const runBody = JSON.parse(
      String(fetcher.mock.calls[2][1]?.body),
    ) as Record<string, unknown>;
    expect(Object.keys(runBody)).toEqual(["metadata"]);
    expect(runBody).not.toHaveProperty("code_sha");
    expect(runBody).not.toHaveProperty("image_digest");
    expect(runBody).not.toHaveProperty("dependency_lock_hash");
    expect(runBody).not.toHaveProperty("executor_version");
    expect(runBody).not.toHaveProperty("config_hash");
    expect(fetcher.mock.calls[2][1]?.headers).toEqual(
      expect.objectContaining({
        Authorization: "Bearer test-researcher",
        "Idempotency-Key": "idem-0000000000000001",
        "If-Match": '"1"',
      }),
    );
  });
});

describe("explicit API mappers", () => {
  it("does not invent paper/live or running-state evidence", () => {
    const job = mapResearchJob({
      id: "rj_3",
      resource_version: 1,
      title: "CN_A 20TD research",
      market: "CN_A",
      environment: "RESEARCH",
      state: "DRAFT",
      owner: "researcher-1",
      universe_ref: "universe://csi300/pit",
      frequency: "1d",
      decision_clock: "T_CLOSE",
      trade_clock: "T_PLUS_1_OPEN",
      settlement_clock: null,
      exchange_scope: [],
      contract_selection: null,
      roll_policy: null,
      horizon: "20TD",
      research_brief_version_id: "brief://seed",
      budget: {},
      created_at: "2026-08-12T01:00:00Z",
      updated_at: "2026-08-12T01:00:00Z",
    });

    expect(job.environment).toBe("RESEARCH");
    expect(job.snapshotRefs).toEqual([]);
    expect(job.runFingerprint).toBeNull();
    expect(job.allowedActions).toEqual(["VIEW"]);
  });

  it("maps experiment evidence without inferring validation or profitability", () => {
    const experiment = mapExperiment({
      id: "exp_1",
      project_id: "local",
      research_job_id: "rj_1",
      brief_version_id: "brief_1",
      market: "CN_COMMODITY_FUTURES",
      state: "PREREGISTERED",
      resource_version: 2,
      spec_hash: "spec-hash",
      factor_ir_hash: "ir-hash",
      snapshot_id: "snapshot-1",
      snapshot_manifest_hash: "snapshot-hash",
      latest_run_id: "run_1",
      created_at: "2026-08-13T01:00:00Z",
      created_by: "researcher-1",
    });
    const run = mapExperimentRun({
      id: "run_1",
      experiment_id: "exp_1",
      market: "CN_COMMODITY_FUTURES",
      state: "NON_REPRODUCIBLE",
      run_fingerprint: "fingerprint",
      attempt_count: 2,
      validation_summary: null,
      invariance: {
        future_truncation_passed: true,
        sentinel_isolation_passed: false,
        baseline_output_hash: "baseline",
        future_truncation_output_hash: "baseline",
        sentinel_isolation_output_hash: "mismatch",
      },
      created_at: "2026-08-13T01:00:00Z",
      updated_at: "2026-08-13T01:01:00Z",
    });
    const artifacts = mapExperimentArtifacts({
      items: [
        {
          content_hash: "sha256:artifact",
          artifact_type: "ValidationArtifact",
          schema_version: "factor-validation/v1",
          size_bytes: 512,
          media_type: "application/json",
          domain_hash: "domain-hash",
        },
      ],
      lineage: [
        {
          edge_hash: "edge-hash",
          source_artifact_hash: "sha256:source",
          target_artifact_hash: "sha256:artifact",
          relation: "VALIDATED_BY",
        },
      ],
    });

    expect(experiment).toMatchObject({
      factorIrHash: "ir-hash",
      snapshotManifestHash: "snapshot-hash",
      latestRunId: "run_1",
    });
    expect(run).toMatchObject({
      state: "NON_REPRODUCIBLE",
      attemptCount: 2,
      validationSummary: null,
      invariance: { sentinelIsolationPassed: false },
    });
    expect(artifacts.items[0]).toMatchObject({
      artifactType: "ValidationArtifact",
      sizeBytes: 512,
    });
    expect(artifacts.lineage[0].relation).toBe("VALIDATED_BY");
  });
});

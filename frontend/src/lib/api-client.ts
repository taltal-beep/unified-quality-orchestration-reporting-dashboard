export interface ExecutionRequest {
  runs: Array<{
    test_type: "pytest" | "behavex" | "behave_native" | "locust";
    target_repo: string;
    cli_args?: string[];
    timeout_s?: number;
  }>;
  persist?: boolean;
  trigger_source?: "ui";
  ci_mode?: boolean;
}

export interface ExecutionAccepted {
  execution_id: string;
  status: "queued" | "running";
  events_url: string;
  summary_url: string;
}

export interface ExecutionStatus {
  execution_id: string;
  status: "queued" | "running" | "completed" | "failed";
  summary: Record<string, unknown> | null;
  run_ids: string[];
  error: string | null;
}

export interface RunListItem {
  run_id: string;
  created_at: number;
  returncode: number;
  status: string | null;
  health_pct: number | null;
  links_under_static: Record<string, string>;
}

export type DeltaClassification = "regression" | "improvement" | "neutral" | "unknown";

export interface DeltaMetricNode {
  current_value: number | null;
  baseline_value: number | null;
  absolute_delta: number | null;
  relative_delta_pct: number | null;
  classification: DeltaClassification;
  reason: string | null;
  direction: "higher_is_better" | "lower_is_better";
  unit: "tests" | "pct" | "ms";
}

export interface DeltaComparisonResponse {
  comparison: {
    current_run_id: string;
    baseline_run_id: string;
    current_test_kind: string;
    baseline_test_kind: string;
  };
  metrics: {
    reliability: {
      total_tests: DeltaMetricNode;
      passed: DeltaMetricNode;
      failed: DeltaMetricNode;
      broken: DeltaMetricNode;
      skipped: DeltaMetricNode;
      health_pct: DeltaMetricNode;
    };
    performance: {
      wall_duration_ms: DeltaMetricNode;
      metrics_duration_ms: DeltaMetricNode;
      avg_case_ms: DeltaMetricNode;
    };
  };
  status_summary: {
    regressions: string[];
    improvements: string[];
    unchanged: string[];
    unknown: string[];
  };
  highlights: string[];
}

export interface RunDetailResponse {
  run: {
    run_id: string;
    test_kind: string;
    returncode: number;
    created_at: number;
    started_at: number;
    finished_at: number;
    wall_duration_ms: number;
    health_pct: number | null;
  };
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init
  });
  if (!resp.ok) {
    throw new Error(`API error ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export const apiClient = {
  createExecution(payload: ExecutionRequest): Promise<ExecutionAccepted> {
    return api<ExecutionAccepted>("/api/v1/executions", {
      method: "POST",
      body: JSON.stringify({
        persist: true,
        trigger_source: "ui",
        ci_mode: false,
        ...payload
      })
    });
  },
  getExecution(executionId: string): Promise<ExecutionStatus> {
    return api<ExecutionStatus>(`/api/v1/executions/${executionId}`);
  },
  listRuns(): Promise<{ items: RunListItem[] }> {
    return api<{ items: RunListItem[] }>("/api/v1/runs");
  },
  getRun(runId: string): Promise<RunDetailResponse> {
    return api<RunDetailResponse>(`/api/v1/runs/${runId}`);
  },
  getRunReports(runId: string): Promise<{ static_links: Record<string, string>; artifact_links: string[] }> {
    return api<{ static_links: Record<string, string>; artifact_links: string[] }>(`/api/v1/runs/${runId}/reports`);
  },
  getDeltaComparison(currentRunId: string, baselineRunId: string): Promise<DeltaComparisonResponse> {
    const params = new URLSearchParams({
      current_run_id: currentRunId,
      baseline_run_id: baselineRunId
    });
    return api<DeltaComparisonResponse>(`/api/v1/analytics/delta?${params.toString()}`);
  }
};

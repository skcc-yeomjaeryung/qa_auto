/** Phase 13 — 건별(interactive) 시나리오 실행 계약 · Console 호출부. */

import { apiFetch } from "./apiClient";

// inferred = 분석된 필드명·타입에서 자동 생성한 합성 테스트값 (실행 가능 · 수정 가능)
export type InputConfidence = "confirmed" | "inferred" | "review_required" | "unresolved";
export type PlanStage = "a_input" | "request" | "b_ui";

export type RunPreviewScreen = {
  screen: string;
  route?: string | null;
  routePattern?: string | null;
};

export type RunPreviewApi = {
  stepId?: string | null;
  method: string;
  path: string;
};

export type RunPreviewField = {
  field: string;
  value: unknown;
  displayValue?: string | null;
  required: boolean;
  category?: string | null;
  expectedPath?: string | null;
  locator?: string | null;
  source?: string | null;
  rationale?: string | null;
  confidence: InputConfidence;
  synthesized?: boolean;
  masked: boolean;
  editable: boolean;
  candidates: Array<{
    value?: unknown;
    displayValue?: string | null;
    category?: string | null;
    expectedPath?: string | null;
    uncertain?: boolean;
  }>;
};

export type RunPreviewStep = {
  stepId: string;
  action: string;
  stage: PlanStage;
  target?: string | null;
  description: string;
};

export type RunPreview = {
  scenarioId: string;
  scenarioName: string;
  scenarioVersion: string;
  scenarioStatus: string;
  projectId?: string | null;
  serviceId?: string | null;
  aScreen: RunPreviewScreen;
  bScreen: RunPreviewScreen;
  expectedApis: RunPreviewApi[];
  fields: RunPreviewField[];
  reviewFieldCount: number;
  inferredFieldCount?: number;
  destructive: boolean;
  destructiveReasons: string[];
  dataMutationAllowed: boolean;
  dataMutationPolicySource: "environment" | "one_time_confirmation";
  plannedSteps: RunPreviewStep[];
  recommendationId?: string | null;
  inputProfileId?: string | null;
  inputProfileVersion?: string | null;
  inputProfileStatus?: string | null;
  commitRefs: Record<string, string>;
  environmentId?: string | null;
  environmentName?: string | null;
  baseUrl?: string | null;
  previousRun?: {
    runId: string;
    status: string;
    inputs: Record<string, unknown>;
    outcomeKind?: string | null;
    createdAt?: string | null;
  } | null;
  unresolved: Array<Record<string, unknown>>;
  missingData: string[];
  generatedAt?: string | null;
};

export type RunStep = {
  stepId: string;
  action: string;
  status: string;
  mcpTool?: string | null;
  refOrLocator?: string | null;
  startedAt?: string | null;
  endedAt?: string | null;
  screenshotPath?: string | null;
  snapshotPath?: string | null;
  observationSummary?: string | null;
  missingData: string[];
};

export type RunSummary = {
  runId: string;
  scenarioId: string;
  status: string;
  mode?: string;
  scenarioVersion?: string | null;
  inputProfileId?: string | null;
  inputProfileVersion?: string | null;
  overrides?: Record<string, unknown>;
  reusedFromRunId?: string | null;
  inputs: Record<string, unknown>;
  steps: RunStep[];
  plannedStepCount: number;
  progressPercent: number;
  currentStepId?: string | null;
  failedStepId?: string | null;
  outcomeKind?: string | null;
  outcomeSummary?: string | null;
  observationSummary?: string | null;
  screenshotCount: number;
  snapshotCount: number;
  missingData: string[];
  hitlRequired: boolean;
  partialEvidence: boolean;
  backendTraceStatus?: string | null;
  environmentName?: string | null;
  commitSha?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
  /** 실행기 원본 결과 — 실행 요약·입력 바인딩 등 관측 재료 */
  result?: {
    runNarrative?: string | null;
    runNarrativeMode?: string | null;
    inputBindings?: Array<{
      field: string;
      value?: string | null;
      source?: string;
      rationale?: string;
      filled?: boolean;
    }>;
  } | null;
};

export const RUN_ACTIVE_STATUSES = ["QUEUED", "PREPARING", "RUNNING"];

export function isRunActive(status: string | undefined): boolean {
  return RUN_ACTIVE_STATUSES.includes(String(status || ""));
}

export class StaleVersionError extends Error {
  constructor(
    message: string,
    readonly currentVersion?: string,
    readonly requestedVersion?: string,
  ) {
    super(message);
    this.name = "StaleVersionError";
  }
}

async function readError(res: Response): Promise<never> {
  let detail: unknown;
  try {
    detail = (await res.json())?.detail;
  } catch {
    detail = undefined;
  }
  if (res.status === 409 && detail && typeof detail === "object") {
    const body = detail as Record<string, string>;
    throw new StaleVersionError(
      body.message || "버전이 변경되었습니다",
      body.currentVersion,
      body.requestedVersion,
    );
  }
  if (res.status === 409 && typeof detail === "string") {
    throw new StaleVersionError(detail);
  }
  throw new Error(typeof detail === "string" ? detail : `요청 실패 (${res.status})`);
}

export async function fetchRunPreview(
  scenarioId: string,
  body: {
    environmentId?: string | null;
    inputProfileId?: string | null;
    reuseFromRunId?: string | null;
    refreshRecommendation?: boolean;
  } = {},
): Promise<RunPreview> {
  const res = await apiFetch(`/api/scenarios/${scenarioId}/run-preview`, {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!res.ok) await readError(res);
  return (await res.json()) as RunPreview;
}

export async function startInteractiveRun(
  scenarioId: string,
  body: {
    environmentId?: string | null;
    inputProfileId?: string | null;
    inputProfileVersion?: string | null;
    scenarioVersion?: string | null;
    inputs?: Record<string, unknown>;
    overrides?: Record<string, unknown>;
    reuseFromRunId?: string | null;
    allowDestructive?: boolean;
  },
): Promise<RunSummary> {
  const res = await apiFetch(`/api/scenarios/${scenarioId}/runs`, {
    method: "POST",
    body: JSON.stringify({ ...body, consent: true, mode: "interactive" }),
  });
  if (!res.ok) await readError(res);
  return (await res.json()) as RunSummary;
}

export async function fetchRun(runId: string): Promise<RunSummary> {
  const res = await apiFetch(`/api/runs/${runId}`, { cache: "no-store" });
  if (!res.ok) await readError(res);
  return (await res.json()) as RunSummary;
}

export async function cancelRun(runId: string): Promise<RunSummary> {
  const res = await apiFetch(`/api/runs/${runId}/cancel`, { method: "POST" });
  if (!res.ok) await readError(res);
  return (await res.json()) as RunSummary;
}

export async function retestRun(
  runId: string,
  body: { reuseFromRunId?: string | null; overrides?: Record<string, unknown> } = {},
): Promise<RunSummary> {
  const res = await apiFetch(`/api/runs/${runId}/retest`, {
    method: "POST",
    body: JSON.stringify({ ...body, consent: true, mode: "interactive" }),
  });
  if (!res.ok) await readError(res);
  return (await res.json()) as RunSummary;
}

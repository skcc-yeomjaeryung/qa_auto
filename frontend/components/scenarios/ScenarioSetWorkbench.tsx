"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { formatDateTime } from "../../lib/datetime";
import { scenarioTitleKo } from "../../lib/scenarioLabels";
import { Breadcrumbs } from "../Breadcrumbs";
import { FlowCanvas } from "../flow/FlowCanvas";
import { CommonDataTable } from "../CommonDataTable";
import { PageShell, PageStickyFooter } from "../PageShell";
import { matchesQuery, ScreenSearch } from "../ScreenSearch";
import {
  TableBulkDeleteForm,
  TableRowCheckbox,
  TableSelectAllCheckbox,
  confirmBulkDelete,
} from "../TableBulkDeleteForm";
import { Button } from "../ui";
import { ProgressBarType1, TableProgressCell } from "../ProgressBar";
import { actionToastId, showActionToast } from "../../lib/actionToast";
import {
  ExecutionAccountDialog,
  type ExecutionAccountChoice,
  type ExecutionEnvironmentChoice,
} from "../ExecutionAccountDialog";
import { ScenarioDetailPanel } from "./ScenarioDetailPanel";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";

type ApiScenario = {
  scenarioId: string;
  serviceId: string;
  projectId?: string | null;
  graphId?: string | null;
  name: string;
  status: string;
  unresolvedCount: number;
  createdAt?: string | null;
  businessPath?: string[];
  assignedRole?: string | null;
  result?: Record<string, any> | null;
};

type RunRow = {
  runId: string;
  scenarioId: string;
  status: string;
  outcomeKind?: string | null;
  outcomeSummary?: string | null;
  observationSummary?: string | null;
  createdAt?: string | null;
  progressPercent?: number;
  currentStepId?: string | null;
};

type ScenarioSet = { setId: string; repositoryName: string };

type AccountRunRequest = {
  scenarioIds: string[];
  noun: string;
  projectId: string;
  environment: ExecutionEnvironmentChoice | null;
  accounts: ExecutionAccountChoice[];
};

type BulkProgress = {
  total: number;
  completed: number;
  running: number;
  success: number;
  failed: number;
  cancelled: number;
  percent: number;
  targetScenarioIds: string[];
  runs: Array<{
    runId: string;
    scenarioId: string;
    status: string;
    outcomeKind?: string | null;
    progressPercent?: number;
    currentStepId?: string | null;
  }>;
};

type BulkRunSeed = {
  runId: string;
  scenarioId: string;
  status: string;
  outcomeKind?: string | null;
};

type ScenarioRunPresentation = {
  label: string;
  tone: "idle" | "queued" | "running" | "success" | "warning" | "review";
  percent: number;
  detail: string;
  createdAt?: string | null;
  showProgress: boolean;
};

type ScenarioGroup = {
  setId: string;
  label: string;
  rows: ApiScenario[];
  projectId?: string | null;
  runCount: number;
  successCount: number;
  failureCount: number;
  runningCount: number;
  latestRunAt: string | null;
  createdAt: string | null;
};

type BusinessProgress = {
  total: number;
  completed: number;
  running: number;
  success: number;
  failed: number;
  percent: number;
};

const RUNNING_STATUSES = new Set(["QUEUED", "RUNNING", "IN_PROGRESS", "ACTIVE", "STARTED"]);
const TERMINAL_STATUSES = new Set(["WAITING_FOR_REVIEW", "AUTO_FAILED", "CANCELLED"]);

/** 실패로 관측된 결과 종류 — Pass/Fail 확정이 아니라 관측 분류다 */
const FAILURE_KINDS = new Set(["be_error", "business_error", "fe_error", "failure"]);

/**
 * 테스트 시나리오 화면 — 그룹(저장소 단위 생성 묶음) → 시나리오 목록 + 우측 상세 2단 구조.
 *
 * 그룹에서 일괄 실행하고, 목록은 계속 보이는 상태로 우측 슬라이드 패널에서
 * 시나리오 상세·실행·증적을 읽는다. 화면을 갈아 끼우지 않아 어떤 시나리오가 있는지 잊지 않는다.
 */
export function ScenarioSetWorkbench() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const graphIdParam = searchParams.get("graphId");
  const scenarioIdParam = searchParams.get("scenarioId");
  const serviceIdParam = searchParams.get("serviceId");
  const setIdParam = searchParams.get("setId");
  const viewParam = searchParams.get("view");

  const [scenarios, setScenarios] = useState<ApiScenario[]>([]);
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [repoBySet, setRepoBySet] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [startingSetIds, setStartingSetIds] = useState<Set<string>>(new Set());
  const [stopBusySetIds, setStopBusySetIds] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [groupView, setGroupView] = useState("all");
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [accountRunRequest, setAccountRunRequest] = useState<AccountRunRequest | null>(null);
  const [bulkProgress, setBulkProgress] = useState<BulkProgress | null>(null);
  const [focusedBusinessKey, setFocusedBusinessKey] = useState<string | null>(null);
  const progressSourceRef = useRef<EventSource | null>(null);
  const loadRequestRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++loadRequestRef.current;
    setLoading(true);
    try {
      const fetchLists = async () => {
        const responses = await Promise.all([
          fetch(`${API}/api/scenarios`, { cache: "no-store" }),
          fetch(`${API}/api/runs`, { cache: "no-store" }),
          fetch(`${API}/api/console/scenario-sets`, { cache: "no-store" }),
        ]);
        if (!responses[0].ok) throw new Error("테스트 시나리오 목록을 불러오지 못했습니다");
        return responses;
      };
      let responses: [Response, Response, Response];
      try {
        responses = await fetchLists() as [Response, Response, Response];
      } catch {
        // Strict Mode/HMR 또는 백엔드 재기동 경계의 순간 연결 실패는 대기 없이 한 번 복구한다.
        responses = await fetchLists() as [Response, Response, Response];
      }
      const [sRes, rRes, setRes] = responses;
      if (requestId !== loadRequestRef.current) return;
      setScenarios((await sRes.json()) as ApiScenario[]);
      if (rRes.ok) setRuns((await rRes.json()) as RunRow[]);
      if (setRes.ok) {
        const sets = (await setRes.json()) as ScenarioSet[];
        setRepoBySet(Object.fromEntries(sets.map((s) => [s.setId, s.repositoryName])));
      }
      setMessage(null);
    } catch (e) {
      if (requestId === loadRequestRef.current) {
        setMessage(e instanceof Error ? e.message : "불러오지 못했습니다");
      }
    } finally {
      if (requestId === loadRequestRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /** 시나리오별 최근 실행 1건 */
  const runsByScenario = useMemo(() => {
    const map: Record<string, RunRow> = {};
    for (const run of runs) if (!map[run.scenarioId]) map[run.scenarioId] = run;
    return map;
  }, [runs]);

  const runningByScenario = useMemo(() => {
    const set = new Set<string>();
    for (const run of runs) {
      if (RUNNING_STATUSES.has((run.status || "").toUpperCase())) set.add(run.scenarioId);
    }
    return set;
  }, [runs]);

  function setIdOf(row: ApiScenario): string {
    return String(row.graphId || row.result?.sourceRefs?.graphId || `${row.projectId}:unlinked`);
  }

  async function copyScenarioId(event: MouseEvent<HTMLElement>, scenarioId: string) {
    event.preventDefault();
    event.stopPropagation();
    try {
      await navigator.clipboard.writeText(scenarioId);
      setMessage(`테스트 시나리오 ID ${scenarioId}를 복사했습니다. 실행 이력에서 검색할 수 있습니다.`);
    } catch {
      setMessage(`테스트 시나리오 ID를 복사하지 못했습니다. 기술 상세에서 ${scenarioId}를 확인하세요.`);
    }
  }

  /** 테스트 시나리오 그룹 = 저장소 분석 1회로 생성된 시나리오 묶음 */
  const groups = useMemo(() => {
    const scoped = serviceIdParam
      ? scenarios.filter((s) => s.serviceId === serviceIdParam)
      : scenarios;
    const map = new Map<string, ScenarioGroup>();
    for (const row of scoped) {
      const setId = setIdOf(row);
      const entry =
        map.get(setId) ??
        {
          setId,
          label: repoBySet[setId] || "연결 저장소",
          rows: [],
          projectId: row.projectId,
          runCount: 0,
          successCount: 0,
          failureCount: 0,
          runningCount: 0,
          latestRunAt: null,
          createdAt: null,
        };
      entry.rows.push(row);
      const run = runsByScenario[row.scenarioId];
      if (run) {
        entry.runCount += 1;
        const kind = (run.outcomeKind || "").toLowerCase();
        if (kind === "success") entry.successCount += 1;
        else if (FAILURE_KINDS.has(kind)) entry.failureCount += 1;
        if (run.createdAt && (!entry.latestRunAt || run.createdAt > entry.latestRunAt)) {
          entry.latestRunAt = run.createdAt;
        }
      }
      if (runningByScenario.has(row.scenarioId)) entry.runningCount += 1;
      if (row.createdAt && (!entry.createdAt || row.createdAt < entry.createdAt)) {
        entry.createdAt = row.createdAt;
      }
      map.set(setId, entry);
    }
    // 실행 결과를 먼저 보는 화면 — 실행된 시나리오가 위로 온다
    for (const entry of map.values()) {
      entry.rows.sort((a, b) => {
        const ra = runsByScenario[a.scenarioId] ? 0 : 1;
        const rb = runsByScenario[b.scenarioId] ? 0 : 1;
        return ra - rb;
      });
    }
    return Array.from(map.values()).sort((a, b) => b.runCount - a.runCount);
  }, [scenarios, repoBySet, serviceIdParam, runsByScenario, runningByScenario]);

  const visibleGroups = useMemo(
    () =>
      groups.filter((group) => {
        if (groupView === "executed" && group.runCount === 0) return false;
        if (groupView === "failed" && group.failureCount === 0) return false;
        if (groupView === "pending" && group.runCount >= group.rows.length) return false;
        return matchesQuery(
          query,
          group.label,
          group.setId,
          ...group.rows.map((r) => r.scenarioId),
          ...group.rows.map((r) =>
            scenarioTitleKo({ name: r.name, serviceId: r.serviceId, result: r.result as never }),
          ),
        );
      }),
    [groupView, groups, query],
  );

  const selectedGroupRun = useMemo(() => {
    const selectedGroups = groups.filter((group) => checked.has(group.setId));
    const scenarioIds = selectedGroups.flatMap((group) => group.rows.map((row) => row.scenarioId));
    const projectCount = new Set(selectedGroups.map((group) => group.projectId).filter(Boolean)).size;
    const label = selectedGroups.length <= 2
      ? selectedGroups.map((group) => group.label).join(", ")
      : `${selectedGroups[0]?.label} 외 ${selectedGroups.length - 1}개 그룹`;
    return { groupCount: selectedGroups.length, scenarioIds, projectCount, label };
  }, [checked, groups]);

  const openGroup = useMemo(
    () => groups.find((g) => g.setId === setIdParam) ?? null,
    [groups, setIdParam],
  );

  const openScenario = useMemo(
    () => scenarios.find((s) => s.scenarioId === scenarioIdParam) ?? null,
    [scenarios, scenarioIdParam],
  );

  useEffect(() => {
    setChecked(new Set());
  }, [setIdParam]);

  const groupRows = useMemo(() => {
    if (!openGroup) return [];
    return openGroup.rows.filter((row) =>
      matchesQuery(
        query,
        row.scenarioId,
        row.name,
        row.result?.caseId,
        scenarioTitleKo({ name: row.name, serviceId: row.serviceId, result: row.result as never }),
        runsByScenario[row.scenarioId]?.outcomeKind,
      ),
    );
  }, [openGroup, query, runsByScenario]);

  const businessTree = useMemo(() => {
    const l1Map = new Map<string, Map<string, ApiScenario[]>>();
    for (const row of groupRows) {
      const path = row.businessPath?.length === 3
        ? row.businessPath
        : (row.result?.businessHierarchy?.path as string[] | undefined) ?? ["공통 업무", "기타 담당", row.name];
      const l1 = path[0] || "공통 업무";
      const l2 = path[1] || row.assignedRole || "기타 담당";
      const l2Map = l1Map.get(l1) ?? new Map<string, ApiScenario[]>();
      const rows = l2Map.get(l2) ?? [];
      rows.push(row);
      l2Map.set(l2, rows);
      l1Map.set(l1, l2Map);
    }
    return Array.from(l1Map.entries()).map(([label, l2Map]) => ({
      label,
      children: Array.from(l2Map.entries()).map(([childLabel, rows]) => ({ label: childLabel, rows })),
    }));
  }, [groupRows]);

  const liveBulkByScenario = useMemo(
    () => new Map((bulkProgress?.runs ?? []).map((run) => [run.scenarioId, run])),
    [bulkProgress],
  );

  function runPresentation(scenarioId: string): ScenarioRunPresentation {
    const live = liveBulkByScenario.get(scenarioId);
    const stored = runsByScenario[scenarioId];
    if (!live && !stored) {
      return { label: "미실행", tone: "idle", percent: 0, detail: "실행 전", showProgress: false };
    }

    const status = String(live?.status || stored?.status || "").toUpperCase();
    const outcomeKind = String(live?.outcomeKind || stored?.outcomeKind || "").toLowerCase();
    const terminal = TERMINAL_STATUSES.has(status);
    const percent = Math.max(
      0,
      Math.min(100, Number(live?.progressPercent ?? stored?.progressPercent ?? (terminal ? 100 : 0))),
    );
    const currentStepId = live?.currentStepId || stored?.currentStepId;
    const createdAt = stored?.createdAt;

    if (!terminal) {
      const queued = status === "QUEUED" || status === "CREATED";
      return {
        label: queued ? "실행 대기" : `실행 중 ${percent}%`,
        tone: queued ? "queued" : "running",
        percent,
        detail: currentStepId ? `현재 ${currentStepId} 단계 처리 중` : queued ? "실행 순서를 기다리고 있어요" : "실행 결과를 실시간으로 수집하고 있어요",
        createdAt,
        showProgress: true,
      };
    }
    if (status === "CANCELLED") {
      return { label: "실행 취소", tone: "warning", percent, detail: "실행이 취소됐습니다", createdAt, showProgress: true };
    }
    if (status === "AUTO_FAILED" || FAILURE_KINDS.has(outcomeKind)) {
      return { label: "확인 필요", tone: "warning", percent: 100, detail: "실행 결과에서 확인할 내용이 발견됐습니다", createdAt, showProgress: true };
    }
    if (outcomeKind === "success") {
      return { label: "정상 관측", tone: "success", percent: 100, detail: "시나리오 관측을 완료했습니다", createdAt, showProgress: true };
    }
    return { label: "실행 완료 · 검토 대기", tone: "review", percent: 100, detail: "관측 자료를 담당자가 확인할 차례입니다", createdAt, showProgress: true };
  }

  function progressForRows(rows: ApiScenario[]): BusinessProgress {
    let completed = 0;
    let running = 0;
    let success = 0;
    let failed = 0;
    for (const row of rows) {
      const live = liveBulkByScenario.get(row.scenarioId);
      const liveStatus = (live?.status || "").toUpperCase();
      const liveIsRunning = Boolean(
        live && ((live.progressPercent ?? 0) < 100 || RUNNING_STATUSES.has(liveStatus)),
      );
      if (liveIsRunning || runningByScenario.has(row.scenarioId)) {
        running += 1;
        continue;
      }
      const run = runsByScenario[row.scenarioId];
      if (!run && !live) continue;
      completed += 1;
      const outcomeKind = (live?.outcomeKind || run?.outcomeKind || "").toLowerCase();
      if (FAILURE_KINDS.has(outcomeKind) || liveStatus === "AUTO_FAILED") failed += 1;
      else if (outcomeKind === "success") success += 1;
    }
    const total = rows.length;
    return {
      total,
      completed,
      running,
      success,
      failed,
      percent: total ? Math.round((completed / total) * 100) : 0,
    };
  }

  /** 현재 일괄 실행에 포함된 행만 집계한다. 이전 실행 이력이 새 Progress에 섞이지 않는다. */
  function activeProgressForRows(rows: ApiScenario[]): BusinessProgress | null {
    if (!bulkProgress) return null;
    const rowIds = new Set(rows.map((row) => row.scenarioId));
    const targetIds = bulkProgress.targetScenarioIds.filter((scenarioId) => rowIds.has(scenarioId));
    if (targetIds.length === 0) return null;
    const liveById = new Map(bulkProgress.runs.map((run) => [run.scenarioId, run]));
    let completed = 0;
    let success = 0;
    let failed = 0;
    for (const scenarioId of targetIds) {
      const live = liveById.get(scenarioId);
      const status = (live?.status || "").toUpperCase();
      if (!TERMINAL_STATUSES.has(status)) continue;
      completed += 1;
      const outcomeKind = (live?.outcomeKind || "").toLowerCase();
      if (status === "AUTO_FAILED" || FAILURE_KINDS.has(outcomeKind)) failed += 1;
      else if (outcomeKind === "success") success += 1;
    }
    return {
      total: targetIds.length,
      completed,
      running: Math.max(0, targetIds.length - completed),
      success,
      failed,
      percent: targetIds.length ? Math.round((completed / targetIds.length) * 100) : 0,
    };
  }

  function displayProgressForRows(rows: ApiScenario[]): BusinessProgress {
    return activeProgressForRows(rows) ?? progressForRows(rows);
  }

  const focusedBusiness = useMemo(() => {
    if (!focusedBusinessKey) return null;
    for (const level1 of businessTree) {
      if (`l1:${level1.label}` === focusedBusinessKey) {
        return {
          label: level1.label,
          rows: level1.children.flatMap((child) => child.rows),
        };
      }
      for (const level2 of level1.children) {
        if (`l2:${level1.label}:${level2.label}` === focusedBusinessKey) {
          return { label: `${level1.label} · ${level2.label}`, rows: level2.rows };
        }
      }
    }
    return null;
  }, [businessTree, focusedBusinessKey]);

  async function deleteScenarios(ids: string[], noun: string) {
    if (ids.length === 0) return;
    if (!confirmBulkDelete(noun, ids.length)) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/scenarios/bulk-delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenarioIds: ids }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "삭제 실패");
      setMessage(body.message || `${noun} ${ids.length}건을 삭제했습니다.`);
      setChecked(new Set());
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "삭제 실패");
    } finally {
      setBusy(false);
    }
  }

  /** 등록된 실행환경과 비밀값이 제거된 계정 메타데이터를 읽는다. */
  async function resolveEnvironment(
    projectId: string,
  ): Promise<{ environment: ExecutionEnvironmentChoice | null; accounts: ExecutionAccountChoice[] }> {
    try {
      const res = await fetch(`${API}/api/projects/${projectId}/environments`, {
        cache: "no-store",
      });
      if (!res.ok) return { environment: null, accounts: [] };
      const envs = (await res.json()) as Array<ExecutionEnvironmentChoice & { status?: string }>;
      if (!Array.isArray(envs) || envs.length === 0) return { environment: null, accounts: [] };
      const active = envs.filter((env) => !env.status || env.status === "active");
      const pool = active.length ? active : envs;
      const environment = pool.find((env) => (env.frontendBaseUrl || "").includes("cymbal-bank")) || pool[0];
      const accountRes = await fetch(`${API}/api/environments/${environment.id}/accounts`, { cache: "no-store" });
      const accounts = accountRes.ok ? ((await accountRes.json()) as ExecutionAccountChoice[]) : [];
      return { environment, accounts };
    } catch {
      return { environment: null, accounts: [] };
    }
  }

  /** 실행 전 계정·권한 확인 팝업을 연다. 계정 값은 LLM 입력으로 전달하지 않는다. */
  async function bulkRun(scenarioIds: string[], noun: string) {
    if (scenarioIds.length === 0) {
      setMessage("실행할 테스트 시나리오를 선택하세요.");
      return;
    }
    const toastId = actionToastId("scenario-bulk-run", scenarioIds.slice().sort().join("-"));
    showActionToast({
      id: toastId,
      title: "테스트 시나리오 일괄 실행",
      message: `${noun} 테스트 시나리오 그룹의 일괄 실행 요청을 시작했습니다. 실행 계정을 확인합니다.`,
      tone: "progress",
    });
    setBusy(true);
    try {
      const selected = scenarios.filter((s) => scenarioIds.includes(s.scenarioId));
      const projectId = selected.find((s) => s.projectId)?.projectId;
      if (!projectId) throw new Error("시나리오의 프로젝트를 확인할 수 없습니다");
      if (selected.some((scenario) => scenario.projectId !== projectId)) {
        throw new Error("한 번에 같은 프로젝트의 시나리오만 실행할 수 있습니다");
      }
      const resolved = await resolveEnvironment(projectId);
      setAccountRunRequest({ scenarioIds, noun, projectId, ...resolved });
    } catch (e) {
      const errorMessage = e instanceof Error ? e.message : "실행 계정 확인 실패";
      setMessage(errorMessage);
      showActionToast({ id: toastId, title: "일괄 실행 준비 실패", message: errorMessage, tone: "error" });
    } finally {
      setBusy(false);
    }
  }

  function watchBulkRuns(initialRuns: BulkRunSeed[]) {
    const runIds = initialRuns.map((run) => run.runId);
    const targetScenarioIds = initialRuns.map((run) => run.scenarioId);
    progressSourceRef.current?.close();
    setBulkProgress({
      total: runIds.length,
      completed: 0,
      running: runIds.length,
      success: 0,
      failed: 0,
      cancelled: 0,
      percent: 0,
      targetScenarioIds,
      runs: initialRuns.map((run) => ({ ...run, progressPercent: 0, currentStepId: null })),
    });
    const source = new EventSource(`${API}/api/console/bulk-runs/events?runIds=${encodeURIComponent(runIds.join(","))}`);
    progressSourceRef.current = source;
    const update = (event: MessageEvent) => {
      const next = JSON.parse(event.data) as Omit<BulkProgress, "targetScenarioIds">;
      setBulkProgress({ ...next, targetScenarioIds });
      setMessage((current) => current?.startsWith("실행 상황 연결을 복구") ? null : current);
    };
    source.addEventListener("progress", update as EventListener);
    source.addEventListener("complete", ((event: MessageEvent) => {
      update(event);
      source.close();
      progressSourceRef.current = null;
      void load();
    }) as EventListener);
    source.onerror = () => {
      if (source.readyState !== EventSource.CLOSED) {
        setMessage("실행 상황 연결을 복구하고 있어요. 각 시나리오의 현재 상태는 그대로 유지됩니다.");
      }
    };
  }

  useEffect(() => () => progressSourceRef.current?.close(), []);

  async function executeBulkRun(environmentId: string, scenarioAccountIds: Record<string, string>) {
    const request = accountRunRequest;
    if (!request) return;
    const targetSetIds = new Set(
      scenarios.filter((scenario) => request.scenarioIds.includes(scenario.scenarioId)).map(setIdOf),
    );
    const toastId = actionToastId("scenario-bulk-run", request.scenarioIds.slice().sort().join("-"));
    setStartingSetIds((current) => new Set([...current, ...targetSetIds]));
    setAccountRunRequest(null);
    setBusy(true);
    try {
      const runBody: Record<string, unknown> = {
        scenarioIds: request.scenarioIds,
        consent: true,
        environmentId,
        scenarioAccountIds,
        inputs: { customerId: "CUS-1001" },
      };
      const res = await fetch(`${API}/api/console/bulk-runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(runBody),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "일괄 실행 실패");
      setMessage(`${data.message} · 선택 계정/권한으로 실제 브라우저 실행을 시작했습니다`);
      showActionToast({
        id: toastId,
        title: "일괄 실행 시작",
        message: `${request.noun} 테스트 시나리오 그룹 ${request.scenarioIds.length}건의 실행을 시작했습니다.`,
        tone: "success",
      });
      setChecked(new Set());
      await load();
      const initialRuns = (data.runs || []).filter(
        (row: Partial<BulkRunSeed>): row is BulkRunSeed =>
          typeof row.runId === "string" && typeof row.scenarioId === "string",
      );
      if (initialRuns.length > 0) watchBulkRuns(initialRuns);
      setMessage((previous) => `${previous ?? ""} (${request.noun} ${request.scenarioIds.length}건)`.trim());
    } catch (e) {
      const errorMessage = e instanceof Error ? e.message : "일괄 실행 실패";
      setMessage(errorMessage);
      showActionToast({ id: toastId, title: "일괄 실행 실패", message: errorMessage, tone: "error" });
    } finally {
      setBusy(false);
      setStartingSetIds((current) => {
        const next = new Set(current);
        targetSetIds.forEach((setId) => next.delete(setId));
        return next;
      });
    }
  }

  /** 「테스트 종료」 — 그룹 안에서 아직 끝나지 않은 실행만 취소한다 */
  async function stopSet(setId: string) {
    setStopBusySetIds((current) => new Set(current).add(setId));
    try {
      const res = await fetch(
        `${API}/api/console/scenario-sets/${encodeURIComponent(setId)}/stop`,
        { method: "POST" },
      );
      const body = (await res.json()) as { message?: string; detail?: string };
      if (!res.ok) throw new Error(body.detail || "테스트 종료 요청이 처리되지 않았습니다");
      setMessage(body.message ?? "테스트 종료를 요청했습니다.");
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "테스트 종료 실패");
    } finally {
      setStopBusySetIds((current) => {
        const next = new Set(current);
        next.delete(setId);
        return next;
      });
    }
  }

  function openScenarioDetail(setId: string, scenarioId: string) {
    setFocusedBusinessKey(null);
    router.push(
      `/scenarios?setId=${encodeURIComponent(setId)}&scenarioId=${encodeURIComponent(scenarioId)}`,
    );
  }

  const isGraphView = viewParam === "graph" || Boolean(graphIdParam);

  // 보조 화면 — 의존관계 그래프 (시나리오가 지정되면 그 시나리오 범위만)
  if (isGraphView) {
    const backHref = openGroup
      ? scenarioIdParam
        ? `/scenarios?setId=${encodeURIComponent(openGroup.setId)}&scenarioId=${encodeURIComponent(scenarioIdParam)}`
        : `/scenarios?setId=${encodeURIComponent(openGroup.setId)}`
      : "/scenarios";
    return (
      <div data-testid="scenario-graph-view">
        <div className="flow-mode-bar" style={{ padding: "8px 16px" }}>
          <Button variant="secondary" size="sm" onClick={() => router.push(backHref)}>
            테스트 시나리오로 돌아가기
          </Button>
          <span className="muted" style={{ fontSize: 11, marginLeft: 10 }}>
            의존관계 그래프는 분석 결과(화면·API 연결)를 보는 보조 화면입니다.
          </span>
        </div>
        <FlowCanvas
          scenarioId={scenarioIdParam || undefined}
          setScenarios={openGroup?.rows.map((row) => ({
            scenarioId: row.scenarioId,
            title: scenarioTitleKo({
              name: row.name,
              serviceId: row.serviceId,
              result: row.result as never,
            }),
            graphId: row.graphId || row.result?.sourceRefs?.graphId || null,
          }))}
          backHref={backHref}
        />
      </div>
    );
  }

  const level: "groups" | "group" = openGroup ? "group" : "groups";

  const trail: Array<{ label: string; href?: string }> = [
    { label: "콘솔", href: "/" },
    { label: "테스트 시나리오", href: "/scenarios" },
  ];
  if (openGroup) {
    trail.push({
      label: `${openGroup.label} 테스트 시나리오 그룹`,
      href: `/scenarios?setId=${encodeURIComponent(openGroup.setId)}`,
    });
  }
  if (openScenario) {
    trail.push({
      label: scenarioTitleKo({
        name: openScenario.name,
        serviceId: openScenario.serviceId,
        result: openScenario.result as never,
      }),
    });
  }

  const heading =
    level === "group" ? `${openGroup?.label} 테스트 시나리오 그룹` : "테스트 시나리오";

  const lead =
    level === "group"
      ? "왼쪽 목록에서 시나리오를 고르면 오른쪽에 상세 설명·실행 흐름·실행 콘솔이 열립니다. 목록은 계속 보입니다."
      : "분석으로 생성된 테스트 시나리오 그룹입니다. 그룹을 클릭하면 그 그룹의 시나리오를 보고 일괄 실행할 수 있습니다.";

  const groupSummary = openGroup
    ? [
        { label: "시나리오", value: openGroup.rows.length, unit: "건" },
        { label: "정상 관측", value: openGroup.successCount, unit: "건" },
        { label: "실패 관측", value: openGroup.failureCount, unit: "건", accent: true },
        {
          label: "미실행",
          value: Math.max(0, openGroup.rows.length - openGroup.runCount),
          unit: "건",
        },
      ]
    : [];

  return (
    <PageShell
      testId="scenario-set-workbench"
      header={
        <div className="content-header">
          <div>
            <Breadcrumbs trail={trail.map((t) => (t.href ? t : { label: t.label }))} />
            <h2>{heading}</h2>
            <p className="muted" style={{ marginTop: 6 }}>
              {lead}
            </p>
          </div>
          {level === "group" && (
            <div className="header-actions-inline">
              <ScreenSearch
                value={query}
                onChange={setQuery}
                placeholder="시나리오명 · 케이스 ID · 결과"
                testId="scenario-search"
                hint="시나리오명·최근 결과로 찾습니다"
              />
            </div>
          )}
        </div>
      }
      footer={
        <PageStickyFooter
          testId="scenario-set-footer"
          note="실행 흐름·상태는 관측 자료입니다. 최종 합격 판정은 담당자가 합니다."
          actions={
            level === "group" && openGroup ? (
              <>
                <Button
                  variant="secondary"
                  size="md"
                  onClick={() => router.push("/scenarios")}
                >
                  그룹 목록으로
                </Button>
                <Button
                  variant="secondary"
                  size="md"
                  busy={stopBusySetIds.has(openGroup.setId)}
                  disabled={
                    stopBusySetIds.has(openGroup.setId) ||
                    (openGroup.runningCount === 0 && !startingSetIds.has(openGroup.setId))
                  }
                  title={
                    openGroup.runningCount === 0
                      ? "진행 중인 실행이 없습니다"
                      : `진행 중 ${openGroup.runningCount}건을 종료합니다`
                  }
                  onClick={() => void stopSet(openGroup.setId)}
                >
                  테스트 종료
                </Button>
                <button
                  type="button"
                  className="action-btn action-btn-analyze"
                  disabled={busy || checked.size === 0}
                  onClick={() => void bulkRun(Array.from(checked), openGroup.label)}
                  data-testid="scenario-bulk-run"
                >
                  선택 {checked.size}건 테스트 수행
                </button>
              </>
            ) : (
              <>
                <Button variant="secondary" size="md" onClick={() => void load()} disabled={loading}>
                  새로고침
                </Button>
                <Link className="ghost-btn" href="/batches">
                  배치 실행 관리
                </Link>
                <Link className="ghost-btn" href="/analysis">
                  분석 메뉴로 이동
                </Link>
                <Button
                  variant="primary"
                  size="md"
                  busy={busy}
                  disabled={selectedGroupRun.groupCount === 0 || selectedGroupRun.projectCount > 1}
                  title={
                    selectedGroupRun.projectCount > 1
                      ? "같은 프로젝트의 그룹만 함께 실행할 수 있습니다"
                      : `선택한 ${selectedGroupRun.groupCount}개 그룹의 시나리오 ${selectedGroupRun.scenarioIds.length}건을 실행합니다`
                  }
                  onClick={() => void bulkRun(selectedGroupRun.scenarioIds, selectedGroupRun.label || `${selectedGroupRun.groupCount}개 그룹`)}
                  data-testid="scenario-selected-groups-run"
                >
                  선택 {selectedGroupRun.groupCount}개 그룹 일괄 실행
                </Button>
              </>
            )
          }
        />
      }
    >
      {message && <div className="connect-banner is-warn anim-slide-down">{message}</div>}
      {level === "groups" && (
        <>
          <CommonDataTable
            rows={visibleGroups}
            totalCount={groups.length}
            toolbar={
              <>
                <ScreenSearch
                  value={query}
                  onChange={setQuery}
                  placeholder="그룹명 · 생성 ID"
                  testId="scenario-search"
                  hint="저장소·생성 ID로 찾습니다"
                />
                <TableBulkDeleteForm
                  embedded
                  noun="테스트 시나리오 그룹"
                  totalCount={visibleGroups.length}
                  selectedCount={checked.size}
                  busy={busy}
                  onDelete={() =>
                    void deleteScenarios(
                      visibleGroups
                        .filter((g) => checked.has(g.setId))
                        .flatMap((g) => g.rows.map((r) => r.scenarioId)),
                      "그룹 시나리오",
                    )
                  }
                  testId="scenario-group-bulk-form"
                />
              </>
            }
            filters={
              <label>
                <select aria-label="실행 상태" value={groupView} onChange={(event) => setGroupView(event.target.value)} data-testid="scenario-group-view-filter">
                  <option value="all">전체 그룹</option>
                  <option value="executed">실행 이력 있음</option>
                  <option value="failed">실패 관측 있음</option>
                  <option value="pending">미실행 포함</option>
                </select>
              </label>
            }
            rowKey={(group) => group.setId}
            columns={[
              { key: "group", label: "테스트 시나리오 그룹", cell: (group) => <strong className="id-link">{group.label}</strong>, sortValue: (group) => group.label },
              { key: "setId", label: "시나리오 생성 ID", cell: (group) => <span className="mono-cell">{group.setId}</span>, sortValue: (group) => group.setId },
              { key: "scenarios", label: "시나리오", cell: (group) => <>{group.rows.length}건</>, sortValue: (group) => group.rows.length },
              {
                key: "observations",
                label: "실행 관측",
                cell: (group) => {
                  const progress = displayProgressForRows(group.rows);
                  return (
                    <TableProgressCell
                      total={progress.total}
                      completed={progress.completed}
                      success={progress.success}
                      failed={progress.failed}
                      running={progress.running}
                      testId={`scenario-progress-${group.setId}`}
                    />
                  );
                },
                sortValue: (group) => displayProgressForRows(group.rows).percent,
              },
              { key: "latestRun", label: "최근 실행", cell: (group) => formatDateTime(group.latestRunAt), sortValue: (group) => group.latestRunAt ? new Date(group.latestRunAt).getTime() : null },
            ]}
            timestamps={{ createdAt: (group) => group.createdAt, updatedAt: () => null }}
            actions={(group) => (
              <>
                <button type="button" className="proc-btn" disabled={busy || group.rows.length === 0} title={`${group.label} 그룹 시나리오 ${group.rows.length}건을 일괄 실행합니다`} onClick={() => void bulkRun(group.rows.map((row) => row.scenarioId), group.label)} data-testid={`scenario-group-run-${group.setId}`}>일괄 실행</button>
                <button type="button" className="proc-btn" disabled={stopBusySetIds.has(group.setId) || (group.runningCount === 0 && !startingSetIds.has(group.setId))} title={group.runningCount === 0 ? "진행 중인 실행이 없습니다" : `진행 중 ${group.runningCount}건을 종료합니다`} onClick={() => void stopSet(group.setId)}>종료</button>
                <button type="button" className="proc-btn proc-btn-danger" onClick={() => void deleteScenarios(group.rows.map((row) => row.scenarioId), `${group.label} 그룹 시나리오`)}>삭제</button>
              </>
            )}
            selection={{ selected: checked, onChange: setChecked, label: (group) => `${group.label} 테스트 시나리오 그룹 선택` }}
            loading={loading}
            emptyText={query || groupView !== "all" ? "현재 검색·필터 조건과 맞는 테스트 시나리오 그룹이 없습니다." : "표시할 테스트 시나리오 그룹이 없습니다. 분석 메뉴에서 시나리오를 생성하세요."}
            loadingText="테스트 시나리오 그룹을 불러오는 중입니다"
            onRowClick={(group) => router.push(`/scenarios?setId=${encodeURIComponent(group.setId)}`)}
            testId="scenario-group-table"
          />
        </>
      )}

      {level === "group" && openGroup && (
        <>
          <div className="scn-summary" data-testid="scenario-set-summary">
            {groupSummary.map((tile) => (
              <div
                className={`scn-summary-tile${tile.accent && tile.value > 0 ? " is-accent" : ""}`}
                key={tile.label}
              >
                <span className="scn-summary-label">{tile.label}</span>
                <strong className="scn-summary-value">
                  {tile.value}
                  <em>{tile.unit}</em>
                </strong>
              </div>
            ))}
            <div className="scn-summary-aside">
              <p>
                최근 실행 {formatDateTime(openGroup.latestRunAt)}
                {openGroup.runningCount > 0 ? ` · 진행 중 ${openGroup.runningCount}건` : ""}
              </p>
              <Link className="qa-panel-link" href="/runs">
                실행 이력 보기
              </Link>
            </div>
          </div>

          <div className="scn-split" data-testid="scenario-split">
            <aside className="scn-list" aria-label="테스트 시나리오 목록">
              <div className="scn-list-head">
                <TableSelectAllCheckbox
                  id="scenario-select-all"
                  allIds={groupRows.map((r) => r.scenarioId)}
                  selected={checked}
                  onChange={setChecked}
                />
                <span className="scn-list-count">
                  테스트 시나리오 {groupRows.length}건
                  {checked.size > 0 ? ` · 선택 ${checked.size}건` : ""}
                </span>
                <button
                  type="button"
                  className="proc-btn proc-btn-danger"
                  disabled={busy || checked.size === 0}
                  onClick={() => void deleteScenarios(Array.from(checked), "시나리오")}
                >
                  삭제
                </button>
              </div>

              <ul className="scn-rows">
                {loading && <li className="scn-row-empty">테스트 시나리오를 불러오는 중입니다</li>}
                {!loading && groupRows.length === 0 && (
                  <li className="scn-row-empty">이 그룹에 표시할 시나리오가 없습니다.</li>
                )}
                {!loading && businessTree.map((level1) => {
                  const level1Ids = level1.children.flatMap((child) => child.rows.map((row) => row.scenarioId));
                  return (
                    <li className="scn-tree-l1" key={level1.label}>
                      <details open>
                        <summary
                          onClick={() => setFocusedBusinessKey(`l1:${level1.label}`)}
                          data-testid={`scenario-business-${level1.label}`}
                        >
                          <TableRowCheckbox
                            id={`scenario-l1-${level1.label}`}
                            checked={level1Ids.every((id) => checked.has(id))}
                            label={`${level1.label} 전체 선택`}
                            onCheckedChange={(on) => setChecked((previous) => {
                              const next = new Set(previous);
                              level1Ids.forEach((id) => on ? next.add(id) : next.delete(id));
                              return next;
                            })}
                          />
                          <strong>{level1.label}</strong><span>{level1Ids.length}건</span>
                          {(() => {
                            const progress = displayProgressForRows(
                              level1.children.flatMap((child) => child.rows),
                            );
                            return (
                              <span className="scn-tree-progress" aria-label={`${level1.label} 실행 진행률 ${progress.percent}%`}>
                                <span><i style={{ width: `${progress.percent}%` }} /></span>
                                <em>{progress.completed}/{progress.total}{progress.running ? ` · 진행 ${progress.running}` : ""}</em>
                              </span>
                            );
                          })()}
                        </summary>
                        <ul>
                          {level1.children.map((level2) => {
                            const level2Ids = level2.rows.map((row) => row.scenarioId);
                            return (
                              <li className="scn-tree-l2" key={level2.label}>
                                <div
                                  className="scn-tree-l2-head"
                                  role="button"
                                  tabIndex={0}
                                  onClick={() => setFocusedBusinessKey(`l2:${level1.label}:${level2.label}`)}
                                  onKeyDown={(event) => {
                                    if (event.key === "Enter" || event.key === " ") {
                                      setFocusedBusinessKey(`l2:${level1.label}:${level2.label}`);
                                    }
                                  }}
                                >
                                  <TableRowCheckbox
                                    id={`scenario-l2-${level2.label}`}
                                    checked={level2Ids.every((id) => checked.has(id))}
                                    label={`${level2.label} 전체 선택`}
                                    onCheckedChange={(on) => setChecked((previous) => {
                                      const next = new Set(previous);
                                      level2Ids.forEach((id) => on ? next.add(id) : next.delete(id));
                                      return next;
                                    })}
                                  />
                                  <strong>{level2.label}</strong><span>{level2.rows.length}건</span>
                                  {(() => {
                                    const progress = displayProgressForRows(level2.rows);
                                    return (
                                      <span className="scn-tree-progress">
                                        <span><i style={{ width: `${progress.percent}%` }} /></span>
                                        <em>{progress.completed}/{progress.total}</em>
                                      </span>
                                    );
                                  })()}
                                </div>
                                <ul>
                                  {level2.rows.map((row) => {
                                    const presentation = runPresentation(row.scenarioId);
                                    const title = scenarioTitleKo({ name: row.name, serviceId: row.serviceId, result: row.result as never });
                                    const active = row.scenarioId === scenarioIdParam;
                                    return (
                                      <li key={row.scenarioId} className={`scn-row${active ? " is-active" : ""}`} data-testid={`scenario-row-${row.scenarioId}`}>
                                        <TableRowCheckbox
                                          id={`scenario-pick-${row.scenarioId}`}
                                          checked={checked.has(row.scenarioId)}
                                          label={`${title} 선택`}
                                          onCheckedChange={(on) => setChecked((prev) => {
                                            const next = new Set(prev);
                                            if (on) next.add(row.scenarioId); else next.delete(row.scenarioId);
                                            return next;
                                          })}
                                        />
                                        <button
                                          type="button"
                                          className="scn-row-main"
                                          onClick={(event) => event.ctrlKey ? void copyScenarioId(event, row.scenarioId) : openScenarioDetail(openGroup.setId, row.scenarioId)}
                                          onContextMenu={(event) => event.ctrlKey ? void copyScenarioId(event, row.scenarioId) : undefined}
                                          aria-current={active ? "true" : undefined}
                                          title="클릭: 상세 보기 · Ctrl+클릭: 시나리오 ID 복사"
                                        >
                                          <span className="scn-row-title">{title}</span>
                                          <span className="scn-row-meta">{row.result?.caseId || row.scenarioId}{presentation.createdAt ? ` · ${formatDateTime(presentation.createdAt)}` : ""}</span>
                                          <span className={`outcome-pill outcome-${presentation.tone}`}>{presentation.label}</span>
                                          {presentation.showProgress ? (
                                            <span className={`scn-row-live-progress is-${presentation.tone}`} aria-label={`${title} ${presentation.label}`}>
                                              <span role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={presentation.percent}>
                                                <i style={{ width: `${presentation.percent}%` }} />
                                              </span>
                                              <em>{presentation.detail}</em>
                                            </span>
                                          ) : null}
                                        </button>
                                      </li>
                                    );
                                  })}
                                </ul>
                              </li>
                            );
                          })}
                        </ul>
                      </details>
                    </li>
                  );
                })}
              </ul>
            </aside>

            <section className="scn-detail" aria-label="테스트 시나리오 상세">
              {openScenario ? (
                <div className="scn-detail-slide anim-slide-left" key={openScenario.scenarioId}>
                  <ScenarioDetailPanel
                    scenarioId={openScenario.scenarioId}
                    graphHref={
                      openScenario.graphId || openScenario.result?.sourceRefs?.graphId
                        ? `/scenarios?setId=${encodeURIComponent(
                            openGroup.setId,
                          )}&scenarioId=${encodeURIComponent(openScenario.scenarioId)}&view=graph`
                        : null
                    }
                  />
                </div>
              ) : focusedBusiness ? (
                <div className="scn-business-progress-card anim-slide-left" data-testid="scenario-business-progress-card">
                  <span className="panel-kicker">업무 단위 실행 Progress</span>
                  <h3>{focusedBusiness.label}</h3>
                  {(() => {
                    const progress = displayProgressForRows(focusedBusiness.rows);
                    const progressStatus = progress.running > 0
                      ? "progressing"
                      : progress.failed > 0
                        ? "warning"
                        : progress.percent === 100
                          ? "complete"
                          : "empty";
                    return (
                      <>
                        <ProgressBarType1
                          percent={progress.percent}
                          label={`완료 ${progress.completed}/${progress.total} · 진행 중 ${progress.running} · 오류 관측 ${progress.failed}`}
                          status={progressStatus}
                          testId="scenario-business-progress-type1"
                        />
                        <div className="scn-business-progress-facts">
                          <span>전체 <strong>{progress.total}</strong></span>
                          <span>실행 완료 <strong>{progress.completed}</strong></span>
                          <span>진행 중 <strong>{progress.running}</strong></span>
                          <span>오류 관측 <strong>{progress.failed}</strong></span>
                        </div>
                      </>
                    );
                  })()}
                  <p className="muted">업무 아래 시나리오를 선택하면 이 영역에 단계별 실행 흐름과 증적이 열립니다.</p>
                </div>
              ) : (
                <div className="scn-detail-placeholder">
                  <span className="scn-detail-placeholder-icon" aria-hidden="true">←</span>
                  <p className="scn-detail-placeholder-title">
                    왼쪽에서 테스트 시나리오를 선택하세요
                  </p>
                  <p className="muted">
                    선택하면 이 자리에 무엇을 어떻게 확인하는 시나리오인지와 실행 흐름·증적·실행
                    콘솔이 열립니다.
                  </p>
                </div>
              )}
            </section>
          </div>
        </>
      )}
      <ExecutionAccountDialog
        open={Boolean(accountRunRequest)}
        projectId={accountRunRequest?.projectId ?? ""}
        environment={accountRunRequest?.environment ?? null}
        initialAccounts={accountRunRequest?.accounts ?? []}
        scenarios={(accountRunRequest?.scenarioIds ?? []).map((scenarioId) => {
          const row = scenarios.find((scenario) => scenario.scenarioId === scenarioId);
          return { scenarioId, name: row?.name || scenarioId };
        })}
        onClose={() => setAccountRunRequest(null)}
        onConfirm={(environmentId, assignments) => void executeBulkRun(environmentId, assignments)}
      />
    </PageShell>
  );
}

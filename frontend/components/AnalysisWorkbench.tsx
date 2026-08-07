"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  CodeResourceTree,
  attachChildren,
  mapNodes,
  type ResourceNode,
} from "./CodeResourceTree";
import { Breadcrumbs } from "./Breadcrumbs";
import { Icon } from "./Icon";
import { CommonDataTable } from "./CommonDataTable";
import { PageShell, PageStickyFooter } from "./PageShell";
import { matchesQuery, ScreenSearch } from "./ScreenSearch";
import { Button } from "./ui";
import { useRightPanel } from "./RightPanelContext";
import {
  TableBulkDeleteForm,
  confirmBulkDelete,
} from "./TableBulkDeleteForm";
import { formatDateTime } from "../lib/datetime";
import { apiFetch } from "../lib/apiClient";
import { ScenarioGenerationDialog, type ScenarioTemplateRow } from "./ScenarioGenerationDialog";
import {
  ScenarioGenerationProgressDialog,
  type ScenarioGenerationStatus,
} from "./ScenarioGenerationProgressDialog";
import { TableProgressCell } from "./ProgressBar";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";

type CatalogItem = {
  analysisId: string;
  projectId: string;
  projectName?: string;
  repositorySetId?: string | null;
  repositoryName?: string;
  role: string;
  label: string;
  pairNote?: string | null;
  isLatestForRole?: boolean;
  status: string;
  screenCount?: number;
  endpointCount?: number;
  componentCount?: number;
  unresolvedCount?: number;
  fileTotal?: number;
  fileCompleted?: number;
  fileFailed?: number;
  progressPercent?: number;
  createdAt?: string | null;
  workspacePath?: string | null;
  commitSha?: string | null;
  previousAnalysisId?: string | null;
  previousCommitSha?: string | null;
  changedFromPrevious?: boolean;
  delta?: {
    screenCount: number;
    componentCount: number;
    endpointCount: number;
    unresolvedCount: number;
  } | null;
};

/** 연결 저장소 단위 묶음 — 화면은 저장소 목록이 먼저 보인다 */
type RepoGroup = {
  key: string;
  name: string;
  projectId: string;
  projectName?: string;
  analyses: CatalogItem[];
  screenCount: number;
  componentCount: number;
  endpointCount: number;
  fileTotal: number;
  fileCompleted: number;
  fileFailed: number;
  progressPercent: number;
  createdAt: string | null;
  latestAt: string | null;
  status: string;
  changeCount: number;
  delta: {
    screenCount: number;
    componentCount: number;
    endpointCount: number;
    unresolvedCount: number;
  };
};

type ScenarioGenerationUiState = {
  status: ScenarioGenerationStatus;
  progress: number;
  startedAt: number | null;
  sourceMode: "ai" | "test_data_csv";
  analysisCount: number;
  resultCount: number;
  error: string | null;
  selectedModel: string | null;
  selectionSummary: string | null;
};

const INITIAL_GENERATION_STATE: ScenarioGenerationUiState = {
  status: "idle",
  progress: 0,
  startedAt: null,
  sourceMode: "ai",
  analysisCount: 0,
  resultCount: 0,
  error: null,
  selectedModel: null,
  selectionSummary: null,
};

const ROLE_LABEL: Record<string, string> = {
  frontend: "화면·Flask(Frontend)",
  backend: "서버(Backend)",
  workspace: "작업공간",
};

function roleLabel(role: string): string {
  return ROLE_LABEL[role] ?? role.toUpperCase();
}

/** 진행중 > 오류 > 완료 순으로 저장소 대표 상태를 정한다 */
function groupStatus(items: CatalogItem[]): string {
  const keys = items.map((i) => (i.status || "").toLowerCase());
  if (keys.some((k) => ["progressing", "running", "analyzing", "syncing", "queued", "pending"].includes(k))) {
    return "progressing";
  }
  if (keys.some((k) => k === "error" || k === "failed")) return "error";
  return keys[0] ?? "";
}

function groupByRepository(catalog: CatalogItem[]): RepoGroup[] {
  const map = new Map<string, RepoGroup>();
  for (const item of catalog) {
    const name = item.repositoryName ?? "연결 저장소";
    const key = item.repositorySetId ?? `${item.projectId}:${name}`;
    const group =
      map.get(key) ??
      {
        key,
        name,
        projectId: item.projectId,
        projectName: item.projectName,
        analyses: [],
        screenCount: 0,
        componentCount: 0,
        endpointCount: 0,
        fileTotal: 0,
        fileCompleted: 0,
        fileFailed: 0,
        progressPercent: 0,
        createdAt: null,
        latestAt: null,
        status: "",
        changeCount: 0,
        delta: { screenCount: 0, componentCount: 0, endpointCount: 0, unresolvedCount: 0 },
      };
    group.analyses.push(item);
    group.screenCount += item.screenCount ?? 0;
    group.componentCount += item.componentCount ?? 0;
    group.endpointCount += item.endpointCount ?? 0;
    group.fileTotal += item.fileTotal ?? 0;
    group.fileCompleted += item.fileCompleted ?? 0;
    group.fileFailed += item.fileFailed ?? 0;
    if (item.createdAt && (!group.createdAt || item.createdAt < group.createdAt)) {
      group.createdAt = item.createdAt;
    }
    if (item.createdAt && (!group.latestAt || item.createdAt > group.latestAt)) {
      group.latestAt = item.createdAt;
    }
    if (item.changedFromPrevious) group.changeCount += 1;
    if (item.delta) {
      group.delta.screenCount += item.delta.screenCount;
      group.delta.componentCount += item.delta.componentCount;
      group.delta.endpointCount += item.delta.endpointCount;
      group.delta.unresolvedCount += item.delta.unresolvedCount;
    }
    map.set(key, group);
  }
  const groups = Array.from(map.values());
  for (const g of groups) {
    // 진행 중인 새 분석과 직전 완료본이 함께 조회될 수 있으므로 역할별 최신 행만 집계한다.
    const latestByRole = new Map<string, CatalogItem>();
    for (const item of [...g.analyses].sort((a, b) => (b.createdAt || "").localeCompare(a.createdAt || ""))) {
      if (!latestByRole.has(item.role)) latestByRole.set(item.role, item);
    }
    g.analyses = Array.from(latestByRole.values()).sort((a, b) =>
      a.role === "frontend" ? -1 : b.role === "frontend" ? 1 : 0,
    );
    g.screenCount = g.analyses.reduce((sum, item) => sum + (item.screenCount ?? 0), 0);
    g.componentCount = g.analyses.reduce((sum, item) => sum + (item.componentCount ?? 0), 0);
    g.endpointCount = g.analyses.reduce((sum, item) => sum + (item.endpointCount ?? 0), 0);
    g.fileTotal = g.analyses.reduce((sum, item) => sum + (item.fileTotal ?? 0), 0);
    g.fileCompleted = g.analyses.reduce((sum, item) => sum + (item.fileCompleted ?? 0), 0);
    g.fileFailed = g.analyses.reduce((sum, item) => sum + (item.fileFailed ?? 0), 0);
    const processedFiles = Math.min(g.fileTotal, g.fileCompleted + g.fileFailed);
    g.progressPercent = g.fileTotal
      ? Math.round((processedFiles / g.fileTotal) * 100)
      : Math.round(
          g.analyses.filter((item) => ["complete", "cached", "error", "failed"].includes((item.status || "").toLowerCase())).length
          / Math.max(1, g.analyses.length)
          * 100,
        );
    g.status = groupStatus(g.analyses);
  }
  return groups.sort((a, b) => a.name.localeCompare(b.name));
}

function analysisStatusDisplay(status: string): { text: string; dotClass: string } {
  const key = (status || "").toLowerCase();
  if (key === "complete" || key === "cached") {
    return { text: "분석완료", dotClass: "status-dot-ok" };
  }
  if (key === "error" || key === "failed") {
    return { text: "오류", dotClass: "status-dot-bad" };
  }
  if (key === "progressing" || key === "running" || key === "analyzing" || key === "syncing") {
    return { text: "진행중", dotClass: "status-dot-warn" };
  }
  if (key === "queued" || key === "pending") {
    return { text: "대기", dotClass: "status-dot-warn" };
  }
  if (!key) {
    return { text: "—", dotClass: "status-dot-warn" };
  }
  return { text: status, dotClass: "status-dot-warn" };
}

function signed(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}

export function AnalysisWorkbench() {
  const router = useRouter();
  const searchParams = useSearchParams();
  /** 대시보드 프로젝트 카드에서 들어오면 그 프로젝트 저장소만 본다 */
  const projectIdParam = searchParams.get("projectId");
  const { setPanel } = useRightPanel();
  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [nodes, setNodes] = useState<ResourceNode[]>([]);
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [excludedByAnalysis, setExcludedByAnalysis] = useState<Record<string, string[]>>({});
  const [preview, setPreview] = useState<{ path: string; name: string; content?: string } | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [openRepoKey, setOpenRepoKey] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [generationDialogOpen, setGenerationDialogOpen] = useState(false);
  const [generation, setGeneration] = useState<ScenarioGenerationUiState>(INITIAL_GENERATION_STATE);

  const selected = useMemo(
    () => catalog.find((c) => c.analysisId === selectedId) ?? null,
    [catalog, selectedId],
  );
  const scopedCatalog = useMemo(
    () => (projectIdParam ? catalog.filter((c) => c.projectId === projectIdParam) : catalog),
    [catalog, projectIdParam],
  );
  const scopedProjectName = useMemo(
    () => scopedCatalog.find((c) => c.projectName)?.projectName ?? projectIdParam,
    [scopedCatalog, projectIdParam],
  );
  // 화면 내 검색 — 저장소명·프로젝트·분석 ID로 목록을 좁힌다
  const repoGroups = useMemo(
    () =>
      groupByRepository(scopedCatalog).filter((group) =>
        matchesQuery(
          query,
          group.name,
          group.projectName,
          ...group.analyses.flatMap((a) => [a.analysisId, a.role, a.status]),
        ),
      ),
    [scopedCatalog, query],
  );
  const openRepo = useMemo(
    () => repoGroups.find((g) => g.key === openRepoKey) ?? null,
    [repoGroups, openRepoKey],
  );
  // 목록은 그룹 1건 = 1행. 화면(FE)·서버(BE) 구분은 상세에서만 나눈다.
  const analysisRows = repoGroups;
  const isDetailOpen = Boolean(openRepoKey && selectedId);

  async function loadCatalog(silent = false) {
    if (!silent) setLoading(true);
    try {
      const res = await fetch(`${API}/api/console/analyses`, { cache: "no-store" });
      if (!res.ok) throw new Error("분석 목록을 불러오지 못했습니다");
      const data = (await res.json()) as CatalogItem[];
      setCatalog(data);
      setMessage((current) => current && /failed to fetch|불러오지 못했습니다/i.test(current) ? null : current);
      if (selectedId && !data.some((d) => d.analysisId === selectedId)) {
        setSelectedId(null);
        setOpenRepoKey(null);
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }

  /** 목록 행 클릭 → 소스 탐색 상세로 전환한다 (화면 분석을 먼저 보여준다) */
  function openAnalysis(group: RepoGroup, item?: CatalogItem) {
    const first =
      item ?? group.analyses.find((a) => a.role === "frontend") ?? group.analyses[0] ?? null;
    if (!first) return;
    setOpenRepoKey(group.key);
    setSelectedId(first.analysisId);
  }

  /** 체크된 그룹에 속한 분석 ID 전체 — 삭제·생성은 그룹 단위로 다룬다 */
  const checkedAnalysisIds = useMemo(
    () =>
      repoGroups
        .filter((g) => checked.has(g.key))
        .flatMap((g) => g.analyses.map((a) => a.analysisId)),
    [repoGroups, checked],
  );

  function backToList() {
    setOpenRepoKey(null);
    setSelectedId(null);
  }

  async function deleteGroup(group: RepoGroup) {
    const ids = group.analyses.map((a) => a.analysisId);
    if (!window.confirm(`${group.name} 분석 결과 ${ids.length}건을 삭제할까요?`)) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/console/analyses/bulk-delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ analysisIds: ids }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "삭제 실패");
      setMessage(body.message);
      if (selectedId && ids.includes(selectedId)) backToList();
      await loadCatalog();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "삭제 실패");
    } finally {
      setBusy(false);
    }
  }

  async function loadTree(analysisId: string) {
    const res = await fetch(`${API}/api/console/analyses/${analysisId}/tree?maxDepth=3`, {
      cache: "no-store",
    });
    if (!res.ok) throw new Error((await res.json()).detail || "트리 로드 실패");
    const data = await res.json();
    setNodes(data.nodes ?? []);
    setPreview(null);
  }

  useEffect(() => {
    loadCatalog().catch((err: Error) => setMessage(err.message));
  }, []);

  // 프로젝트 화면에서 시작한 분석도 현재 목록에 나타나도록 조용히 갱신한다.
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") {
        void loadCatalog(true).catch(() => undefined);
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setNodes([]);
      setExcluded(new Set());
      return;
    }
    setExcluded(new Set(excludedByAnalysis[selectedId] ?? []));
    loadTree(selectedId).catch((err: Error) => setMessage(err.message));
  }, [selectedId]);

  useEffect(() => {
    setPanel(
      <div className="right-panel">
        <p className="panel-kicker">분석</p>
        <h3 className="panel-title">{selected?.repositoryName ?? "저장소 선택"}</h3>
        <dl className="detail-list">
          <div>
            <dt>분석 ID</dt>
            <dd className="mono-cell">{selected?.analysisId ?? "—"}</dd>
          </div>
          <div>
            <dt>저장소</dt>
            <dd>{selected?.repositoryName ?? "—"}</dd>
          </div>
          <div>
            <dt>프로젝트</dt>
            <dd>{selected?.projectId ?? "—"}</dd>
          </div>
          <div>
            <dt>직전 분석 대비</dt>
            <dd>
              {!selected?.previousAnalysisId
                ? "비교 기준 없음"
                : selected.changedFromPrevious
                  ? `변경 있음 · ${selected.previousCommitSha?.slice(0, 8) ?? "커밋 미상"} → ${selected.commitSha?.slice(0, 8) ?? "커밋 미상"}`
                  : "변경 없음"}
            </dd>
          </div>
        </dl>
      </div>,
    );
    return () => setPanel(null);
  }, [selected, setPanel]);

  async function expandNode(path: string) {
    if (!selectedId) return;
    setBusy(true);
    try {
      const res = await fetch(
        `${API}/api/console/analyses/${selectedId}/tree?expandPath=${encodeURIComponent(path)}`,
        { cache: "no-store" },
      );
      if (!res.ok) throw new Error((await res.json()).detail || "펼치기 실패");
      const data = await res.json();
      setNodes((prev) => attachChildren(prev, path, data.nodes ?? []));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "펼치기 실패");
    } finally {
      setBusy(false);
    }
  }

  async function openFile(path: string, name: string) {
    if (!selectedId) return;
    setPreview({ path, name, content: "// 불러오는 중…" });
    try {
      const res = await fetch(
        `${API}/api/console/analyses/${selectedId}/file?path=${encodeURIComponent(path)}`,
        { cache: "no-store" },
      );
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "파일 로드 실패");
      setPreview({ path: body.path || path, name: body.name || name, content: body.content || "" });
    } catch (err) {
      setPreview({
        path,
        name,
        content: `// 파일을 열 수 없습니다\n// ${err instanceof Error ? err.message : "오류"}`,
      });
    }
  }

  async function bulkDelete() {
    if (!confirmBulkDelete("분석", checked.size)) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/console/analyses/bulk-delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ analysisIds: checkedAnalysisIds }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "일괄 삭제 실패");
      setMessage(body.message);
      setChecked(new Set());
      await loadCatalog();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "일괄 삭제 실패");
    } finally {
      setBusy(false);
    }
  }

  async function generateScenarios(
    sourceMode: "ai" | "test_data_csv" = "ai",
    testDataRows: ScenarioTemplateRow[] = [],
  ) {
    const targets =
      checkedAnalysisIds.length > 0
        ? catalog.filter((c) => checkedAnalysisIds.includes(c.analysisId))
        : openRepo
          ? openRepo.analyses
          : selected
            ? [selected]
          : [];
    if (targets.length === 0) {
      setMessage("시나리오를 생성할 분석을 선택하세요.");
      return;
    }
    setGenerationDialogOpen(false);
    setGeneration({
      status: "running",
      progress: 4,
      startedAt: Date.now(),
      sourceMode,
      analysisCount: targets.length,
      resultCount: 0,
      error: null,
      selectedModel: null,
      selectionSummary: null,
    });
    setBusy(true);
    try {
      const byProject = new Map<string, string[]>();
      for (const t of targets) {
        const list = byProject.get(t.projectId) ?? [];
        list.push(t.analysisId);
        byProject.set(t.projectId, list);
      }
      const projectEntries = Array.from(byProject.entries());
      const previews = await Promise.all(projectEntries.map(async ([projectId]) => {
        const response = await apiFetch("/api/agent-monitor/selection-preview", {
          method: "POST",
          body: JSON.stringify({ workflowId: "wf_scenario_dsl", projectId }),
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.detail || "프로젝트 모델 선택을 확인하지 못했습니다");
        const decision = (body.steps ?? [])
          .map((step: { modelDecision?: Record<string, unknown> | null }) => step.modelDecision)
          .find(Boolean) as Record<string, unknown> | undefined;
        return {
          name: String(decision?.selectedDisplayName || "규칙 기반 생성"),
          summary: String(decision?.decisionSummary || "선택 가능한 모델이 없어 코드 근거 규칙으로 생성합니다."),
        };
      }));
      const selectedModels = Array.from(new Set(previews.map((preview) => preview.name)));
      setGeneration((current) => ({
        ...current,
        progress: 8,
        selectedModel: selectedModels.join(" · "),
        selectionSummary: previews.map((preview) => preview.summary).join(" "),
      }));
      setGeneration((current) => ({ ...current, progress: 10 }));
      await Promise.all(targets.map(async (target) => {
        const selectionResponse = await fetch(`${API}/api/console/resource-selection`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            analysisId: target.analysisId,
            excludedPaths:
              target.analysisId === selectedId
                ? Array.from(excluded)
                : excludedByAnalysis[target.analysisId] ?? [],
            selectedPaths: [],
          }),
        });
        if (!selectionResponse.ok) {
          const selectionError = await selectionResponse.json().catch(() => ({}));
          throw new Error(selectionError.detail || "분석 범위를 저장하지 못했습니다");
        }
      }));
      setGeneration((current) => ({ ...current, progress: 26 }));

      let total = 0;
      // 모델별 연결과 프로젝트 문맥이 섞이지 않도록 프로젝트 단위 생성은 순차 실행한다.
      for (const [projectIndex, [projectId, analysisIds]] of projectEntries.entries()) {
        setGeneration((current) => ({
          ...current,
          progress: 28 + Math.round((projectIndex / Math.max(1, projectEntries.length)) * 60),
        }));
        const res = await fetch(`${API}/api/console/generate-scenarios`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            projectId,
            analysisIds,
            excludedPaths: [],
            sourceMode,
            testDataRows,
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || "시나리오 생성 실패");
        if (!data.scenarioIds?.length && data.status !== "complete") {
          throw new Error(data.message || "시나리오 생성 Workflow가 완료되지 않았습니다");
        }
        total += data.scenarioIds?.length ?? 0;
        setGeneration((current) => ({
          ...current,
          progress: 28 + Math.round(((projectIndex + 1) / Math.max(1, projectEntries.length)) * 64),
        }));
      }
      setMessage(
        total > 0
          ? `코드와 화면 근거로 시나리오 ${total}건을 만들었습니다. 실제 모델 호출 여부는 Agent 모니터링의 호출 영수증에서 확인할 수 있어요.`
          : "시나리오가 생성되지 않았습니다. 분석 결과·Graph를 확인하세요.",
      );
      if (total > 0) {
        setGeneration((current) => ({
          ...current,
          status: "complete",
          progress: 100,
          resultCount: total,
          error: null,
        }));
      } else {
        setGeneration((current) => ({
          ...current,
          status: "error",
          error: "생성된 시나리오가 없습니다. 분석 결과와 Interaction Graph를 확인해 주세요.",
        }));
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "시나리오 생성 실패";
      setMessage(errorMessage);
      setGeneration((current) => ({ ...current, status: "error", error: errorMessage }));
    } finally {
      setBusy(false);
    }
  }

  const canGenerate = checked.size > 0 || Boolean(selected);

  return (
    <PageShell
      testId="analysis-workbench"
      className="analysis-page"
      header={
        <div className="content-header">
          <div>
            <Breadcrumbs
              trail={[
                { label: "콘솔", href: "/" },
                { label: "분석" },
              ]}
            />
            <h2>저장소 분석</h2>
            <p className="muted" style={{ marginTop: 6 }}>
              한 행이 분석 그룹 한 건입니다. 화면(Frontend)·서버(Backend) 구분은 행을 클릭한 상세에서
              전환해 봅니다. 분석에서 제외할 파일은 체크를 해제하고, 아래 CTA로 테스트 시나리오를
              생성하세요.
            </p>
          </div>
          <div className="header-actions-inline">
            <button type="button" className="ghost-btn" disabled={busy} onClick={() => void loadCatalog()}>
              <Icon name="refresh" size={14} />
              새로고침
            </button>
          </div>
        </div>
      }
      footer={
        <PageStickyFooter
          testId="analysis-footer"
          note="분석 완료 후 시나리오 초안을 생성합니다. Complete ≠ HITL Pass."
          actions={
            <>
              <Link className="ghost-btn" href="/scenarios">
                시나리오 메뉴
              </Link>
              <Button
                variant="primary"
                size="md"
                busy={busy}
                disabled={!canGenerate}
                onClick={() => setGenerationDialogOpen(true)}
                data-testid="analysis-generate-scenarios"
              >
                {busy ? "시나리오 생성 중…" : "테스트 시나리오 생성 시작"}
              </Button>
            </>
          }
        />
      }
    >
        {message && <div className="connect-banner is-ok anim-slide-down">{message}</div>}

        {projectIdParam && (
          <div className="connect-banner is-info anim-slide-down" data-testid="analysis-project-scope">
            프로젝트 <strong>{scopedProjectName}</strong> 저장소만 보고 있습니다.
            <Link className="ghost-btn" href="/analysis" style={{ marginLeft: 10 }}>
              전체 저장소 보기
            </Link>
          </div>
        )}

        {!isDetailOpen && (
        <CommonDataTable
          rows={analysisRows}
          totalCount={repoGroups.length}
          toolbar={
            <>
              <ScreenSearch
                value={query}
                onChange={setQuery}
                placeholder="프로젝트명 · 저장소명"
                testId="analysis-search"
                hint="프로젝트·저장소·분석 상태로 찾습니다"
              />
              <TableBulkDeleteForm
                embedded
                noun="분석"
                totalCount={repoGroups.length}
                selectedCount={checked.size}
                busy={busy}
                onDelete={() => void bulkDelete()}
                testId="analysis-bulk-form"
              />
            </>
          }
          rowKey={(group) => group.key}
          columns={[
            {
              key: "groupId",
              label: "분석 그룹",
              cell: (group) => (
                <strong className="id-link">{group.projectName || "프로젝트"} 분석 그룹</strong>
              ),
              sortValue: (group) => `${group.projectName || "프로젝트"} 분석 그룹`,
            },
            {
              key: "repository",
              label: "연결 저장소",
              cell: (group) => (
                <div className="cell-stack">
                  <span>{group.name}</span>
                  {(group.projectName ?? group.projectId) !== group.name && (
                    <span className="muted">{group.projectName ?? group.projectId}</span>
                  )}
                </div>
              ),
              sortValue: (group) => group.name,
            },
            {
              key: "summary",
              label: "분석 결과 요약",
              cell: (group) => {
                const unresolved = group.analyses.reduce((sum, item) => sum + (item.unresolvedCount ?? 0), 0);
                const changeSummary = group.changeCount > 0
                  ? `직전 분석 대비 ${group.changeCount}개 영역 변경 · 화면 ${signed(group.delta.screenCount)} · 컴포넌트 ${signed(group.delta.componentCount)} · 엔드포인트 ${signed(group.delta.endpointCount)}`
                  : undefined;
                return (
                  <div className="analysis-tag-row" data-testid={`analysis-coverage-${group.key}`}>
                    <span className="analysis-metric-chip is-screen">화면 {group.screenCount}</span>
                    <span className="analysis-metric-chip is-component">컴포넌트 {group.componentCount}</span>
                    <span className="analysis-metric-chip is-endpoint">Endpoint {group.endpointCount}</span>
                    {group.analyses.map((analysis) => (
                      <span
                        className={`analysis-role-chip is-${analysis.role}`}
                        key={analysis.analysisId}
                        title={roleLabel(analysis.role)}
                      >
                        {analysis.role === "frontend" ? "화면" : analysis.role === "backend" ? "서버" : roleLabel(analysis.role)} {analysis.status === "complete" || analysis.status === "cached" ? "완료" : analysis.status}
                      </span>
                    ))}
                    {unresolved > 0 && <span className="analysis-metric-chip is-warning">확인 {unresolved}</span>}
                    {changeSummary && (
                      <span
                        className="analysis-metric-chip is-change"
                        data-testid={`analysis-change-${group.key}`}
                        title={changeSummary}
                      >
                        변경 {group.changeCount}
                      </span>
                    )}
                  </div>
                );
              },
              sortValue: (group) => group.screenCount + group.componentCount + group.endpointCount,
            },
            {
              key: "status",
              label: "분석 진행",
              cell: (group) => {
                const status = analysisStatusDisplay(group.status);
                const processed = Math.min(group.fileTotal, group.fileCompleted + group.fileFailed);
                return (
                  <TableProgressCell
                    total={group.fileTotal || group.analyses.length}
                    completed={group.fileTotal ? processed : group.analyses.filter((item) => ["complete", "cached", "error", "failed"].includes((item.status || "").toLowerCase())).length}
                    success={group.fileTotal ? group.fileCompleted : group.analyses.filter((item) => ["complete", "cached"].includes((item.status || "").toLowerCase())).length}
                    failed={group.fileTotal ? group.fileFailed : group.analyses.filter((item) => ["error", "failed"].includes((item.status || "").toLowerCase())).length}
                    running={status.text === "진행중" || status.text === "대기" ? 1 : 0}
                    successLabel="완료"
                    failureLabel="오류"
                    emptyLabel={status.text === "—" ? "분석 대기" : status.text}
                    status={status.text === "진행중" || status.text === "대기" ? "progressing" : group.fileFailed > 0 ? "error" : group.progressPercent >= 100 ? "complete" : "empty"}
                    testId={`analysis-progress-${group.key}`}
                  />
                );
              },
              sortValue: (group) => group.progressPercent,
            },
          ]}
          timestamps={{ createdAt: (group) => group.createdAt, updatedAt: (group) => group.latestAt }}
          actions={(group) => (
            <>
              <button type="button" className="proc-btn" onClick={() => openAnalysis(group)}>소스 탐색</button>
              <button type="button" className="proc-btn proc-btn-danger" onClick={() => void deleteGroup(group)}>삭제</button>
            </>
          )}
          selection={{ selected: checked, onChange: setChecked, label: (group) => `${group.name} 분석 선택` }}
          loading={loading}
          emptyText={query ? "검색 결과가 없습니다. 검색어를 지우고 다시 확인하세요." : "연결된 저장소가 없습니다. 프로젝트 메뉴에서 저장소를 먼저 연결하세요."}
          loadingText="연결된 저장소 분석 목록을 불러오는 중입니다"
          onRowClick={(group) => openAnalysis(group)}
          rowClassName={(group) => openRepoKey === group.key ? "is-selected" : ""}
          testId="analysis-table"
        />
        )}

      {isDetailOpen && openRepo && selected && (
        <div className="analysis-source-card anim-slide-up" style={{ marginTop: 12 }}>
          <div className="content-header">
            <div>
              <Breadcrumbs
                trail={[
                  { label: "저장소 분석", href: "/analysis" },
                  { label: `${openRepo.name} 분석 상세` },
                  { label: `${roleLabel(selected.role)} 소스 탐색` },
                ]}
                testId="analysis-source-crumbs"
              />
              <h2 style={{ fontSize: 16 }}>
                {openRepo.name}
                <button
                  type="button"
                  className="ghost-btn"
                  style={{ marginLeft: 12 }}
                  onClick={backToList}
                  data-testid="analysis-back-to-list"
                >
                  목록으로
                </button>
              </h2>
              <p className="muted" style={{ marginTop: 4 }}>
                분석 완료 {formatDateTime(selected.createdAt)}
              </p>
              <p className="muted" style={{ marginTop: 4 }}>
                {roleLabel(selected.role)} 분석 결과({selected.analysisId})를 보고 있습니다. 체크를 해제한
                파일은 시나리오 생성 대상에서 제외됩니다.
              </p>
            </div>
            {openRepo.analyses.length > 1 && (
              <div className="role-switch" role="tablist" aria-label="분석 대상 전환">
                {openRepo.analyses.map((a) => (
                  <button
                    type="button"
                    role="tab"
                    aria-selected={a.analysisId === selectedId}
                    className={`role-switch-btn${a.analysisId === selectedId ? " is-active" : ""}`}
                    onClick={() => setSelectedId(a.analysisId)}
                    key={a.analysisId}
                  >
                    {roleLabel(a.role)}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="source-explorer" data-testid="source-explorer">
            <div className="source-tree-pane" data-testid="source-tree-pane">
              <CodeResourceTree
                nodes={nodes}
                busy={busy}
                onToggle={(path, on) => {
                  setExcluded((prev) => {
                    const next = new Set(prev);
                    if (on) next.delete(path);
                    else next.add(path);
                    if (selectedId) {
                      setExcludedByAnalysis((current) => ({
                        ...current,
                        [selectedId]: Array.from(next),
                      }));
                    }
                    return next;
                  });
                  setNodes((prev) => mapNodes(prev, path, on));
                }}
                onExpand={(path) => void expandNode(path)}
                onOpenFile={(path, name) => void openFile(path, name)}
              />
            </div>
            <div className="source-preview-pane" data-testid="source-preview-pane">
              <div className="source-preview-bar">
                <span>{preview?.path ?? "파일을 선택하면 코드가 표시됩니다"}</span>
              </div>
              <pre className="source-preview-body">
                {preview?.content ??
                  `// ${openRepo.name}\n// 왼쪽 트리에서 파일을 클릭하면 코드 미리보기가 열립니다.\n// 긴 코드는 오른쪽 미리보기만 스크롤됩니다.`}
              </pre>
            </div>
          </div>
        </div>
      )}
      <ScenarioGenerationDialog
        open={generationDialogOpen && generation.status === "idle"}
        busy={busy}
        onClose={() => !busy && setGenerationDialogOpen(false)}
        onGenerate={(mode, rows) => void generateScenarios(mode, rows)}
      />
      <ScenarioGenerationProgressDialog
        status={generation.status}
        progress={generation.progress}
        startedAt={generation.startedAt}
        sourceMode={generation.sourceMode}
        analysisCount={generation.analysisCount}
        resultCount={generation.resultCount}
        error={generation.error}
        selectedModel={generation.selectedModel}
        selectionSummary={generation.selectionSummary}
        onClose={() => setGeneration(INITIAL_GENERATION_STATE)}
        onRetry={() => {
          setGeneration(INITIAL_GENERATION_STATE);
          setGenerationDialogOpen(true);
        }}
        onNavigate={() => {
          setGeneration(INITIAL_GENERATION_STATE);
          router.push("/scenarios");
        }}
      />
    </PageShell>
  );
}

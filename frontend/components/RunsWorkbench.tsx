"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { lsSet } from "../lib/localStore";
import { Icon } from "./Icon";
import { PageShell, PageStickyFooter } from "./PageShell";
import { Button } from "./ui";
import { Breadcrumbs } from "./Breadcrumbs";
import { CommonDataTable } from "./CommonDataTable";
import { matchesQuery, ScreenSearch } from "./ScreenSearch";
import {
  TableBulkDeleteForm,
  confirmBulkDelete,
} from "./TableBulkDeleteForm";
import { deleteRuns, useTableSelection } from "../lib/tableSelection";
import { RunEvidenceDrawer } from "./RunEvidenceDrawer";
import { getCurrentUserId } from "../lib/user";
import { apiFetch } from "../lib/apiClient";
import {
  buildScenarioRunContexts,
  type ContextProject,
  type ContextScenarioSet,
} from "../lib/runContext";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";

type RunRow = {
  runId: string;
  scenarioId: string;
  serviceId?: string | null;
  status: string;
  outcomeKind?: string | null;
  outcomeSummary?: string | null;
  observationSummary?: string | null;
  screenshotCount: number;
  snapshotCount: number;
  createdAt?: string | null;
  updatedAt?: string | null;
  changedFromPrevious?: boolean;
};

type ScenarioOpt = {
  scenarioId: string;
  name: string;
  serviceId: string;
  projectId?: string | null;
  graphId?: string | null;
  businessPath?: string[];
  result?: Record<string, unknown> | null;
};

type RunSearchField =
  | "all"
  | "group"
  | "scenarioId"
  | "scenarioName"
  | "runId"
  | "status"
  | "summary"
  | "change";

const RUN_SEARCH_FIELD_LABELS: Record<RunSearchField, string> = {
  all: "전체 필드",
  group: "테스트 시나리오 그룹",
  scenarioId: "테스트 시나리오 ID",
  scenarioName: "시나리오 한글명",
  runId: "실행 ID",
  status: "상태",
  summary: "요약",
  change: "결과 변경",
};

export function RunsWorkbench() {
  const router = useRouter();
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [query, setQuery] = useState("");
  const [searchField, setSearchField] = useState<RunSearchField>("all");
  const [runView, setRunView] = useState("all");
  const [scenarios, setScenarios] = useState<ScenarioOpt[]>([]);
  const [projects, setProjects] = useState<ContextProject[]>([]);
  const [scenarioSets, setScenarioSets] = useState<ContextScenarioSet[]>([]);
  const [projectScope, setProjectScope] = useState("");
  const [groupScope, setGroupScope] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const loadRequestRef = useRef(0);

  async function load() {
    const requestId = ++loadRequestRef.current;
    setBusy(true);
    try {
      let pair: [Response, Response, Response, Response] | null = null;
      for (let attempt = 0; attempt < 2 && !pair; attempt += 1) {
        try {
          const responses = await Promise.all([
            apiFetch(`${API}/api/runs`, { cache: "no-store" }),
            apiFetch(`${API}/api/scenarios`, { cache: "no-store" }),
            apiFetch(`${API}/api/projects?ownerUserId=${encodeURIComponent(getCurrentUserId())}`, { cache: "no-store" }),
            apiFetch(`${API}/api/console/scenario-sets`, { cache: "no-store" }),
          ]);
          if (responses.every((response) => response.ok)) {
            pair = responses as [Response, Response, Response, Response];
          }
        } catch {
          // 개발 서버 전환 순간의 취소된 요청은 즉시 한 번 재시도한다.
        }
      }
      if (!pair) throw new Error("실행 이력과 시나리오를 불러오지 못했습니다");
      if (requestId !== loadRequestRef.current) return;
      const [rRes, sRes, pRes, setRes] = pair;
      const list = (await rRes.json()) as RunRow[];
      const data = (await sRes.json()) as ScenarioOpt[];
      const projectData = (await pRes.json()) as ContextProject[];
      const scenarioSetData = (await setRes.json()) as ContextScenarioSet[];
      if (rRes.ok) {
        setRuns(list);
        lsSet("history.runs", {
          at: new Date().toISOString(),
          count: list.length,
          items: list.slice(0, 50).map((r) => ({
            runId: r.runId,
            scenarioId: r.scenarioId,
            status: r.status,
            outcomeKind: r.outcomeKind,
            screenshotCount: r.screenshotCount,
            snapshotCount: r.snapshotCount,
            createdAt: r.createdAt,
          })),
        });
      }
      if (sRes.ok) {
        setScenarios(data);
        lsSet("history.scenarios", {
          at: new Date().toISOString(),
          count: data.length,
          ids: data.map((s) => s.scenarioId).slice(0, 100),
        });
      }
      setProjects(projectData);
      setScenarioSets(scenarioSetData);
      const firstRunProject = data.find((scenario) => scenario.scenarioId === list[0]?.scenarioId)?.projectId;
      setProjectScope((current) =>
        current && projectData.some((project) => project.id === current)
          ? current
          : String(firstRunProject || projectData[0]?.id || ""),
      );
      setMessage(null);
    } catch (e) {
      if (requestId === loadRequestRef.current) {
        setMessage(e instanceof Error ? e.message : "로드 실패");
      }
    } finally {
      if (requestId === loadRequestRef.current) setBusy(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  function scenarioNameKo(id: string) {
    return scenarioContexts.get(id)?.scenarioName || "시나리오 정보 없음";
  }

  const scenarioContexts = useMemo(
    () => buildScenarioRunContexts(projects, scenarios, scenarioSets),
    [projects, scenarios, scenarioSets],
  );

  const scopedGroups = useMemo(() => {
    const map = new Map<string, { id: string; name: string; count: number }>();
    for (const run of runs) {
      const context = scenarioContexts.get(run.scenarioId);
      if (!context || context.projectId !== projectScope) continue;
      const current = map.get(context.groupId) ?? { id: context.groupId, name: context.groupName, count: 0 };
      current.count += 1;
      map.set(context.groupId, current);
    }
    return Array.from(map.values()).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  }, [runs, scenarioContexts, projectScope]);

  useEffect(() => {
    if (scopedGroups.length === 0) {
      setGroupScope("");
      return;
    }
    if (!scopedGroups.some((group) => group.id === groupScope)) {
      setGroupScope(scopedGroups[0].id);
    }
  }, [scopedGroups, groupScope]);

  // 화면 내 검색 — 실행 ID·시나리오·상태·관측 요약으로 좁힌다
  const comparedRuns = useMemo(() => {
    const byScenario = new Map<string, RunRow[]>();
    for (const run of runs) {
      const history = byScenario.get(run.scenarioId) ?? [];
      history.push(run);
      byScenario.set(run.scenarioId, history);
    }
    const changed = new Map<string, boolean>();
    for (const history of byScenario.values()) {
      history.sort((a, b) => (b.createdAt ?? "").localeCompare(a.createdAt ?? ""));
      history.forEach((run, index) => {
        const previous = history[index + 1];
        changed.set(
          run.runId,
          Boolean(
            previous &&
              (run.status !== previous.status ||
                run.outcomeKind !== previous.outcomeKind ||
                run.outcomeSummary !== previous.outcomeSummary ||
                run.observationSummary !== previous.observationSummary),
          ),
        );
      });
    }
    return runs.map((run) => ({ ...run, changedFromPrevious: changed.get(run.runId) ?? false }));
  }, [runs]);

  const visibleRuns = comparedRuns.filter((row) => {
    const context = scenarioContexts.get(row.scenarioId);
    if (!context || context.projectId !== projectScope) return false;
    if (groupScope && context.groupId !== groupScope) return false;
    const outcome = (row.outcomeKind || "").toLowerCase();
    if (runView === "success" && outcome !== "success") return false;
    if (runView === "attention" && outcome === "success") return false;
    if (runView === "changed" && !row.changedFromPrevious) return false;
    const fields: Record<RunSearchField, unknown[]> = {
      all: [
        context.groupName,
        context.businessGroupName,
        row.scenarioId,
        context.scenarioName,
        row.runId,
        row.status,
        statusKo(row.status),
        row.outcomeSummary,
        row.observationSummary,
        row.changedFromPrevious ? "결과 변경" : "변경 없음",
      ],
      group: [context.groupName, context.businessGroupName],
      scenarioId: [row.scenarioId],
      scenarioName: [context.scenarioName],
      runId: [row.runId],
      status: [row.status, statusKo(row.status)],
      summary: [row.outcomeSummary, row.observationSummary],
      change: [row.changedFromPrevious ? "결과 변경 직전 대비 변경" : "변경 없음"],
    };
    return matchesQuery(query, ...fields[searchField]);
  });

  const selectedRunContext = selectedRunId
    ? scenarioContexts.get(runs.find((row) => row.runId === selectedRunId)?.scenarioId || "")
    : null;

  const { checked, setChecked, selectedIds, clear } = useTableSelection(
    visibleRuns.map((r) => r.runId),
  );

  async function removeRuns(ids: string[]) {
    if (!confirmBulkDelete("실행 이력", ids.length)) return;
    setBusy(true);
    try {
      setMessage(await deleteRuns(ids));
      clear();
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "삭제 실패");
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell
      testId="runs-workbench"
      header={
        <div className="content-header">
          <div>
            <Breadcrumbs trail={[{ label: "콘솔", href: "/" }, { label: "실행 이력" }]} />
            <h2>실행 이력</h2>
            <p className="muted" style={{ marginTop: 6 }}>
              실행 ID를 클릭하면 우측에서 단계·판정 근거·증적을 함께 확인하고 ZIP으로 내려받습니다.
            </p>
          </div>
          <div className="header-actions-inline">
            <button type="button" className="ghost-btn" disabled={busy} onClick={() => void load()}>
              <Icon name="refresh" size={14} />
              새로고침
            </button>
          </div>
        </div>
      }
      footer={
        <PageStickyFooter
          testId="runs-footer"
          note="실행은 테스트 시나리오 상세에서 시작하고, 이 화면에서는 이력과 증적을 확인합니다."
          actions={
            <Button variant="primary" size="md" onClick={() => router.push(groupScope ? `/scenarios?setId=${encodeURIComponent(groupScope)}` : "/scenarios")}>
              테스트 시나리오 보기
            </Button>
          }
        />
      }
    >
        <section className="context-scope-bar" data-testid="runs-context-scope">
          <div className="context-scope-copy">
            <strong>{projects.find((project) => project.id === projectScope)?.name || "프로젝트 선택"}</strong>
            <p>프로젝트와 테스트 시나리오 그룹에 해당하는 실행만 표시합니다.</p>
          </div>
          <label>
            <span>프로젝트</span>
            <select value={projectScope} onChange={(event) => setProjectScope(event.target.value)}>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>{project.name}</option>
              ))}
            </select>
          </label>
          <label>
            <span>테스트 시나리오 그룹</span>
            <select value={groupScope} onChange={(event) => setGroupScope(event.target.value)}>
              {scopedGroups.map((group) => (
                <option key={group.id} value={group.id}>{group.name} · 실행 {group.count}건</option>
              ))}
            </select>
          </label>
        </section>
        {message && <div className="connect-banner is-warn">{message}</div>}
        <CommonDataTable
          rows={visibleRuns}
          totalCount={comparedRuns.length}
          toolbar={
            <>
              <ScreenSearch
                value={query}
                onChange={setQuery}
                placeholder={`${RUN_SEARCH_FIELD_LABELS[searchField]} 검색`}
                testId="runs-search"
                hint={`${RUN_SEARCH_FIELD_LABELS[searchField]}에서 영문 대소문자 구분 없이 일부 일치로 찾습니다`}
              />
              <label>
                <select aria-label="실행 관측" value={runView} onChange={(event) => setRunView(event.target.value)} data-testid="runs-view-filter">
                  <option value="all">전체 실행</option>
                  <option value="success">성공 관측</option>
                  <option value="attention">확인 필요</option>
                  <option value="changed">직전 대비 변경</option>
                </select>
              </label>
              <TableBulkDeleteForm
                embedded
                noun="실행 이력"
                totalCount={visibleRuns.length}
                selectedCount={selectedIds.length}
                busy={busy}
                onDelete={() => void removeRuns(selectedIds)}
                testId="runs-bulk-form"
              />
            </>
          }
          filters={
            <label>
              <select aria-label="검색 기준" value={searchField} onChange={(event) => setSearchField(event.target.value as RunSearchField)} data-testid="runs-search-field">
                {Object.entries(RUN_SEARCH_FIELD_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </label>
          }
          rowKey={(row) => row.runId}
          columns={[
            {
              key: "group",
              label: "테스트 시나리오 그룹",
              cell: (row) => (
                <div className="cell-stack">
                  <strong>{scenarioContexts.get(row.scenarioId)?.groupName || "그룹 정보 없음"}</strong>
                  <span>{scenarioContexts.get(row.scenarioId)?.businessGroupName}</span>
                </div>
              ),
              sortValue: (row) => scenarioContexts.get(row.scenarioId)?.groupName || "",
            },
            {
              key: "scenarioId",
              label: "테스트 시나리오 ID",
              cell: (row) => {
                const context = scenarioContexts.get(row.scenarioId);
                return (
                  <Link
                    className="id-link mono-cell"
                    href={context ? `/scenarios?setId=${encodeURIComponent(context.groupId)}&scenarioId=${encodeURIComponent(row.scenarioId)}` : `/scenarios?scenarioId=${encodeURIComponent(row.scenarioId)}`}
                  >
                    {row.scenarioId}
                  </Link>
                );
              },
              sortValue: (row) => row.scenarioId,
            },
            { key: "scenarioName", label: "시나리오 한글명", cell: (row) => <strong>{scenarioNameKo(row.scenarioId)}</strong>, sortValue: (row) => scenarioNameKo(row.scenarioId) },
            {
              key: "runId",
              label: "실행 ID",
              cell: (row) => <button type="button" className="id-link id-link-button" onClick={() => setSelectedRunId(row.runId)} data-testid={`run-open-${row.runId}`}>{row.runId}</button>,
              sortValue: (row) => row.runId,
            },
            { key: "status", label: "상태", cell: (row) => <span className="status-badge status-info">{statusKo(row.status)}</span>, sortValue: (row) => statusKo(row.status) },
            { key: "summary", label: "요약", cell: (row) => <span className="reason-cell">{row.outcomeSummary || row.observationSummary || "—"}</span>, sortValue: (row) => row.outcomeSummary || row.observationSummary || "" },
            {
              key: "change",
              label: "결과 변경",
              cell: (row) => row.changedFromPrevious ? <span className="status-badge status-warn" data-testid={`run-change-${row.runId}`}>직전 대비 변경</span> : <span className="muted">변경 없음</span>,
              sortValue: (row) => row.changedFromPrevious ? 1 : 0,
            },
            { key: "evidence", label: "증적", cell: (row) => <>화면 {row.screenshotCount} · 스냅 {row.snapshotCount}</>, sortValue: (row) => row.screenshotCount + row.snapshotCount },
          ]}
          timestamps={{ createdAt: (row) => row.createdAt, updatedAt: (row) => row.updatedAt }}
          actions={(row) => (
            <>
              <button type="button" className="proc-btn" onClick={() => setSelectedRunId(row.runId)}>상세·증적</button>
              <button type="button" className="proc-btn proc-btn-danger" onClick={() => void removeRuns([row.runId])}>삭제</button>
            </>
          )}
          selection={{ selected: checked, onChange: setChecked, label: (row) => `${row.runId} 실행 이력 선택` }}
          loading={busy && runs.length === 0}
          emptyText={query || runView !== "all" ? "현재 검색·필터 조건과 맞는 실행 이력이 없습니다." : "실행 이력이 없습니다. 테스트 시나리오에서 테스트를 수행하세요."}
          loadingText="실행 이력을 불러오는 중입니다"
          onRowClick={(row) => setSelectedRunId(row.runId)}
          testId="runs-table"
        />
        <RunEvidenceDrawer
          runId={selectedRunId}
          open={Boolean(selectedRunId)}
          onClose={() => setSelectedRunId(null)}
          context={selectedRunContext}
        />
    </PageShell>
  );
}

function statusKo(status: string) {
  const map: Record<string, string> = {
    WAITING_FOR_REVIEW: "검토 대기",
    AUTO_FAILED: "자동 실패",
    CANCELLED: "취소됨",
    RUNNING: "실행 중",
    PREPARING: "준비 중",
    QUEUED: "대기",
  };
  return map[status] || status;
}

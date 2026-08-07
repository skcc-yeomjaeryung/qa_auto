"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PageShell, PageStickyFooter } from "../../components/PageShell";
import { apiFetch } from "../../lib/apiClient";
import { Breadcrumbs } from "../../components/Breadcrumbs";
import { CommonDataTable } from "../../components/CommonDataTable";
import { matchesQuery, ScreenSearch } from "../../components/ScreenSearch";
import {
  TableBulkDeleteForm,
  confirmBulkDelete,
} from "../../components/TableBulkDeleteForm";
import { deleteRuns, useTableSelection } from "../../lib/tableSelection";
import { RunReportDrawer } from "../../components/RunReportDrawer";
import { getCurrentUserId } from "../../lib/user";
import {
  buildScenarioRunContexts,
  type ContextProject,
  type ContextScenarioSet,
} from "../../lib/runContext";
import { Button } from "../../components/ui";

type RunRow = {
  runId: string;
  scenarioId: string;
  status: string;
  outcomeKind?: string | null;
  observationSummary?: string | null;
  screenshotCount: number;
  snapshotCount: number;
  partialEvidence: boolean;
  backendTraceStatus?: string | null;
  backendTraceConstraint?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
};

type ScenarioRow = {
  scenarioId: string;
  projectId?: string | null;
  graphId?: string | null;
  serviceId?: string;
  name?: string;
  businessPath?: string[];
  result?: Record<string, unknown> | null;
};

const REVIEW_STATUSES = new Set(["WAITING_FOR_REVIEW", "AUTO_FAILED", "CANCELLED"]);

function HitlQueue() {
  const router = useRouter();
  const params = useSearchParams();
  const focusRunId = params.get("runId");
  const [rows, setRows] = useState<RunRow[]>([]);
  const [projects, setProjects] = useState<ContextProject[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioRow[]>([]);
  const [scenarioSets, setScenarioSets] = useState<ContextScenarioSet[]>([]);
  const [projectScope, setProjectScope] = useState("");
  const [groupScope, setGroupScope] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(focusRunId);
  const loadRequestRef = useRef(0);

  const load = useCallback(async () => {
    const requestId = ++loadRequestRef.current;
    setLoading(true);
    try {
      let responses: [Response, Response, Response, Response] | null = null;
      for (let attempt = 0; attempt < 2 && !responses; attempt += 1) {
        try {
          const candidates = await Promise.all([
            apiFetch("/api/runs", { cache: "no-store" }),
            apiFetch("/api/scenarios", { cache: "no-store" }),
            apiFetch(`/api/projects?ownerUserId=${encodeURIComponent(getCurrentUserId())}`, { cache: "no-store" }),
            apiFetch("/api/console/scenario-sets", { cache: "no-store" }),
          ]);
          if (candidates.every((response) => response.ok)) {
            responses = candidates as [Response, Response, Response, Response];
          }
        } catch {
          // 개발 서버 전환 시 취소된 첫 요청은 즉시 재시도한다.
        }
      }
      if (!responses) throw new Error("실행 목록과 프로젝트 문맥을 불러오지 못했습니다");
      const [runRes, scenarioRes, projectRes, setRes] = responses;
      const all = (await runRes.json()) as RunRow[];
      const scenarioData = (await scenarioRes.json()) as ScenarioRow[];
      const projectData = (await projectRes.json()) as ContextProject[];
      const scenarioSetData = (await setRes.json()) as ContextScenarioSet[];
      if (requestId !== loadRequestRef.current) return;
      const reviewRows = all.filter((run) => REVIEW_STATUSES.has(run.status));
      setRows(reviewRows);
      setScenarios(scenarioData);
      setProjects(projectData);
      setScenarioSets(scenarioSetData);
      const firstProject = scenarioData.find((scenario) => scenario.scenarioId === reviewRows[0]?.scenarioId)?.projectId;
      setProjectScope((current) =>
        current && projectData.some((project) => project.id === current)
          ? current
          : String(firstProject || projectData[0]?.id || ""),
      );
      setError(null);
    } catch (e) {
      if (requestId === loadRequestRef.current) {
        setError(e instanceof Error ? e.message : "실행 목록을 불러오지 못했습니다");
      }
    } finally {
      if (requestId === loadRequestRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setSelectedRunId(focusRunId);
  }, [focusRunId]);

  const scenarioContexts = useMemo(
    () => buildScenarioRunContexts(projects, scenarios, scenarioSets),
    [projects, scenarios, scenarioSets],
  );
  const scopedGroups = useMemo(() => {
    const map = new Map<string, { id: string; name: string; count: number }>();
    for (const row of rows) {
      const context = scenarioContexts.get(row.scenarioId);
      if (!context || context.projectId !== projectScope) continue;
      const current = map.get(context.groupId) ?? { id: context.groupId, name: context.groupName, count: 0 };
      current.count += 1;
      map.set(context.groupId, current);
    }
    return Array.from(map.values()).sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  }, [rows, scenarioContexts, projectScope]);

  useEffect(() => {
    if (scopedGroups.length === 0) {
      setGroupScope("");
      return;
    }
    if (!scopedGroups.some((group) => group.id === groupScope)) {
      setGroupScope(scopedGroups[0].id);
    }
  }, [scopedGroups, groupScope]);

  /** 화면 내 검색 — 선택한 프로젝트·그룹 안에서만 실행 ID·시나리오·상태를 좁힌다. */
  const visibleRows = rows.filter((row) => {
    const context = scenarioContexts.get(row.scenarioId);
    if (!context || context.projectId !== projectScope) return false;
    if (groupScope && context.groupId !== groupScope) return false;
    return matchesQuery(
      query,
      context.projectName,
      context.groupName,
      context.businessGroupName,
      context.scenarioName,
      row.runId,
      row.scenarioId,
      technicalStatusKo(row.status),
      row.observationSummary,
    );
  });
  const { checked, setChecked, selectedIds, clear } = useTableSelection(
    visibleRows.map((row) => row.runId),
  );
  const selectedRunContext = selectedRunId
    ? scenarioContexts.get(rows.find((row) => row.runId === selectedRunId)?.scenarioId || "")
    : null;

  /** 검토 목록 정리 — 증적 파일은 남기고 대기 목록에서만 제거한다 */
  async function removeRuns(ids: string[]) {
    if (!confirmBulkDelete("검토 대기 실행", ids.length)) return;
    setBusy(true);
    try {
      await deleteRuns(ids);
      clear();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "삭제 실패");
    } finally {
      setBusy(false);
    }
  }

  function openReview(runId: string) {
    setSelectedRunId(runId);
    router.replace(`/hitl?runId=${encodeURIComponent(runId)}`, { scroll: false });
  }

  function closeReview() {
    setSelectedRunId(null);
    router.replace("/hitl", { scroll: false });
  }

  return (
    <PageShell
      header={
        <div className="content-header">
          <div>
            <Breadcrumbs trail={[{ label: "콘솔", href: "/" }, { label: "승인 검토(HITL)" }]} />
            <h2>HITL 검증 대기</h2>
            <p className="muted" style={{ marginTop: 6 }}>
              실행 이력 데이터를 통해 리포트를 생성하여 담당자/관리자가 승인 할 수 있는 화면 입니다.
            </p>
          </div>
        </div>
      }
      footer={
        <PageStickyFooter
          testId="hitl-footer"
          note="한 실행씩 증적을 확인한 뒤 담당자가 최종 판정을 남깁니다. 기술 실행 완료는 HITL Pass가 아닙니다."
          actions={
            <>
              <Button variant="secondary" size="md" onClick={() => void load()} disabled={loading || busy}>
                새로고침
              </Button>
              <Button
                variant="primary"
                size="md"
                disabled={selectedIds.length !== 1}
                title={selectedIds.length > 1 ? "증적·리포트 검토는 한 실행씩 진행합니다" : undefined}
                onClick={() => selectedIds[0] && openReview(selectedIds[0])}
                data-testid="hitl-selected-review"
              >
                선택 {selectedIds.length}건 증적/리포트 검토
              </Button>
            </>
          }
        />
      }
    >
      {error && (
        <div className="connect-banner is-warn" role="alert">
          {error}
        </div>
      )}

      <div className="hitl-review-guide" data-testid="hitl-review-guide">
        <strong>검토 우선순위</strong>
        <span>서버·화면 오류 → 기대 불충족 → 누락 증적 → 정상 관측 증적 순으로 확인하세요.</span>
      </div>

      <CommonDataTable
        rows={visibleRows}
        totalCount={rows.length}
        filters={
          <>
            <label>
              <select aria-label="프로젝트" value={projectScope} onChange={(event) => setProjectScope(event.target.value)}>
                {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
              </select>
            </label>
            <label>
              <select aria-label="테스트 시나리오 그룹" value={groupScope} onChange={(event) => setGroupScope(event.target.value)}>
                {scopedGroups.map((group) => <option key={group.id} value={group.id}>{group.name} · 검토 {group.count}건</option>)}
              </select>
            </label>
          </>
        }
        toolbar={
          <>
            <ScreenSearch
              value={query}
              onChange={setQuery}
              placeholder="실행 ID · 시나리오 · 상태"
              testId="hitl-search"
              hint="검토 대기 실행을 ID·상태·관측 요약으로 찾습니다"
            />
            <TableBulkDeleteForm
              embedded
              noun="검토 대기 실행"
              totalCount={visibleRows.length}
              selectedCount={selectedIds.length}
              busy={busy}
              onDelete={() => void removeRuns(selectedIds)}
              testId="hitl-bulk-form"
            />
          </>
        }
        rowKey={(row) => row.runId}
        columns={[
          {
            key: "scenarioName",
            label: "시나리오 한글명",
            cell: (row) => (
              <div className="cell-stack hitl-scenario-cell">
                <strong>{scenarioContexts.get(row.scenarioId)?.scenarioName || "시나리오 정보 없음"}</strong>
                <span>{scenarioContexts.get(row.scenarioId)?.businessGroupName || "업무 분류 없음"}</span>
              </div>
            ),
            sortValue: (row) => scenarioContexts.get(row.scenarioId)?.scenarioName || "",
          },
          { key: "status", label: "자동 실행 상태", cell: (row) => <span className="status-badge status-info">{technicalStatusKo(row.status)}</span>, sortValue: (row) => technicalStatusKo(row.status) },
          {
            key: "evidence",
            label: "증적 상태",
            cell: (row) => (
              <div className="hitl-evidence-tags">
                <span>화면 {row.screenshotCount}</span>
                <span>스냅샷 {row.snapshotCount}</span>
                {row.backendTraceStatus === "external_network_only" ? <em>외부 관측</em> : row.partialEvidence ? <em>일부 누락</em> : null}
              </div>
            ),
            sortValue: (row) => row.screenshotCount + row.snapshotCount,
          },
        ]}
        timestamps={{ createdAt: (row) => row.createdAt, updatedAt: (row) => row.updatedAt }}
        actions={(row) => <><button className="proc-btn proc-btn-primary" type="button" onClick={() => openReview(row.runId)}>증적/리포트 검토</button><button type="button" className="proc-btn proc-btn-danger" onClick={() => void removeRuns([row.runId])}>삭제</button></>}
        selection={{ selected: checked, onChange: setChecked, label: (row) => `${row.runId} 검토 대기 실행 선택` }}
        loading={loading}
        emptyText={query ? `검색어 「${query}」와 맞는 검토 대기 실행이 없습니다.` : "검토를 기다리는 실행이 없습니다."}
        loadingText="검토 대기 목록을 불러오는 중입니다"
        onRowClick={(row) => openReview(row.runId)}
        rowClassName={(row) => row.runId === selectedRunId ? "is-focused" : ""}
        testId="hitl-table"
      />
      <RunReportDrawer
        runId={selectedRunId}
        open={Boolean(selectedRunId)}
        onClose={closeReview}
        context={selectedRunContext}
      />
    </PageShell>
  );
}

export default function HitlPage() {
  return (
    <Suspense fallback={<p className="muted">검증 대기 목록을 불러오는 중입니다…</p>}>
      <HitlQueue />
    </Suspense>
  );
}

const TECHNICAL_STATUS_KO: Record<string, string> = {
  WAITING_FOR_REVIEW: "실행 완료 · 검토 대기",
  AUTO_FAILED: "자동 실패 · 원인 확인 필요",
  CANCELLED: "실행 취소",
};

function technicalStatusKo(status: string) {
  return TECHNICAL_STATUS_KO[status] ?? status;
}

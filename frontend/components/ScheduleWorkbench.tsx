"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "../lib/apiClient";
import type { CsvRow } from "../lib/csv";
import { formatDateTime } from "../lib/datetime";
import {
  buildScenarioRunContexts,
  type ContextProject,
  type ContextScenarioSet,
} from "../lib/runContext";
import { matchesQuery, ScreenSearch } from "./ScreenSearch";
import { Breadcrumbs } from "./Breadcrumbs";
import { CommonDataTable } from "./CommonDataTable";
import { PageShell } from "./PageShell";
import {
  TableBulkDeleteForm,
  confirmBulkDelete,
} from "./TableBulkDeleteForm";
import { useTableSelection } from "../lib/tableSelection";
import { Button } from "./ui";

type Scenario = {
  scenarioId: string;
  projectId?: string | null;
  graphId?: string | null;
  serviceId?: string;
  name?: string;
  businessPath?: string[];
  result?: Record<string, unknown> | null;
};
type Environment = { id: string; projectId: string; name: string; status?: string; lastHealthStatus?: string };
type ScheduleScenario = {
  scenarioId: string;
  scenarioName: string;
  scenarioGroupId: string;
  scenarioGroupName: string;
  businessPath: string[];
};
type ScheduleExecution = {
  executionId: string;
  trigger: "manual" | "scheduled";
  status: string;
  totalCount: number;
  completedCount: number;
  failedCount: number;
  runIds: string[];
};
type Schedule = {
  scheduleId: string;
  projectId: string;
  projectName: string;
  name: string;
  scenarios: ScheduleScenario[];
  environmentId?: string | null;
  environmentName?: string | null;
  cronExpression: string;
  cronSummary: string;
  timezone: string;
  startDate?: string | null;
  endDate?: string | null;
  enabled: boolean;
  status: string;
  nextRunAt?: string | null;
  lastRunAt?: string | null;
  runCount: number;
  progressCompleted: number;
  progressTotal: number;
  lastMessage?: string | null;
  lastExecution?: ScheduleExecution | null;
  createdAt: string;
  updatedAt: string;
};
type ScheduleForm = {
  scheduleId: string;
  name: string;
  projectId: string;
  scenarioIds: string[];
  environmentId: string;
  naturalLanguage: string;
  cronExpression: string;
  timezone: string;
  startDate: string;
  endDate: string;
  enabled: boolean;
  note: string;
};
type CronPreview = {
  cronExpression: string;
  summary: string;
  timezone: string;
  suggestedStartDate?: string | null;
  suggestedEndDate?: string | null;
  nextRunAt?: string | null;
};

const EMPTY_FORM: ScheduleForm = {
  scheduleId: "",
  name: "",
  projectId: "",
  scenarioIds: [],
  environmentId: "",
  naturalLanguage: "매일 새벽 5시에 실행",
  cronExpression: "0 5 * * *",
  timezone: "Asia/Seoul",
  startDate: "",
  endDate: "",
  enabled: true,
  note: "",
};

function newScheduleId(): string {
  const stamp = new Date().toISOString().replace(/[-:TZ.]/g, "").slice(0, 12);
  return `SCH-${stamp}`;
}

function scheduleStatusKo(status: string): string {
  return ({
    ACTIVE: "예약 활성",
    PAUSED: "일시정지",
    RUNNING: "실행 중",
    COMPLETED: "예약 종료",
    ERROR: "실행 오류",
  } as Record<string, string>)[status] || status;
}

function scheduleStatusClass(status: string): string {
  if (status === "RUNNING") return "status-info";
  if (status === "ACTIVE") return "status-ok";
  if (status === "ERROR") return "status-bad";
  return "status-warn";
}

export function ScheduleWorkbench() {
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [projects, setProjects] = useState<ContextProject[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioSets, setScenarioSets] = useState<ContextScenarioSet[]>([]);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [query, setQuery] = useState("");
  const [projectScope, setProjectScope] = useState("");
  const [statusScope, setStatusScope] = useState("ALL");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerQuery, setPickerQuery] = useState("");
  const [form, setForm] = useState<ScheduleForm>(EMPTY_FORM);
  const [cronPreview, setCronPreview] = useState<CronPreview | null>(null);

  const load = useCallback(async () => {
    const [scheduleRes, projectRes, scenarioRes, setRes] = await Promise.all([
      apiFetch("/api/schedules", { cache: "no-store" }),
      apiFetch("/api/projects", { cache: "no-store" }),
      apiFetch("/api/scenarios", { cache: "no-store" }),
      apiFetch("/api/console/scenario-sets", { cache: "no-store" }),
    ]);
    if (![scheduleRes, projectRes, scenarioRes, setRes].every((response) => response.ok)) {
      throw new Error("스케줄링 목록과 테스트 시나리오 문맥을 불러오지 못했습니다");
    }
    const scheduleData = (await scheduleRes.json()) as Schedule[];
    const projectData = (await projectRes.json()) as ContextProject[];
    setSchedules(scheduleData);
    setProjects(projectData);
    setScenarios((await scenarioRes.json()) as Scenario[]);
    setScenarioSets((await setRes.json()) as ContextScenarioSet[]);
    setProjectScope((current) =>
      current && projectData.some((project) => project.id === current)
        ? current
        : scheduleData[0]?.projectId || projectData[0]?.id || "",
    );
  }, []);

  useEffect(() => {
    load()
      .catch((error: Error) => setMessage(error.message))
      .finally(() => setLoading(false));
  }, [load]);

  useEffect(() => {
    if (!form.projectId) {
      setEnvironments([]);
      return;
    }
    apiFetch(`/api/projects/${encodeURIComponent(form.projectId)}/environments`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("실행환경 조회 실패");
        setEnvironments((await response.json()) as Environment[]);
      })
      .catch(() => setEnvironments([]));
  }, [form.projectId]);

  useEffect(() => {
    if (!schedules.some((schedule) => schedule.status === "RUNNING")) return;
    const timer = window.setInterval(() => void load().catch(() => undefined), 1500);
    return () => window.clearInterval(timer);
  }, [schedules, load]);

  const scenarioContexts = useMemo(
    () => buildScenarioRunContexts(projects, scenarios, scenarioSets),
    [projects, scenarios, scenarioSets],
  );
  const visibleSchedules = schedules.filter((schedule) =>
    (!projectScope || schedule.projectId === projectScope) &&
    (statusScope === "ALL" || schedule.status === statusScope) &&
    matchesQuery(
      query,
      schedule.scheduleId,
      schedule.name,
      schedule.projectName,
      schedule.status,
      schedule.cronExpression,
      schedule.cronSummary,
      ...schedule.scenarios.flatMap((scenario) => [
        scenario.scenarioId,
        scenario.scenarioName,
        scenario.scenarioGroupName,
      ]),
    ),
  );
  const { checked, setChecked, selectedIds, clear } = useTableSelection(
    visibleSchedules.map((schedule) => schedule.scheduleId),
  );

  const formScenarios = scenarios.filter((scenario) => scenario.projectId === form.projectId);
  const groupedPickerScenarios = useMemo(() => {
    const groups = new Map<string, { name: string; rows: Scenario[] }>();
    for (const scenario of formScenarios) {
      const context = scenarioContexts.get(scenario.scenarioId);
      if (!context || !matchesQuery(pickerQuery, context.groupName, context.scenarioName, scenario.scenarioId, context.businessGroupName)) continue;
      const entry = groups.get(context.groupId) ?? { name: context.groupName, rows: [] };
      entry.rows.push(scenario);
      groups.set(context.groupId, entry);
    }
    return Array.from(groups.entries());
  }, [formScenarios, scenarioContexts, pickerQuery]);

  function openCreate() {
    const projectId = projectScope || projects[0]?.id || "";
    setForm({ ...EMPTY_FORM, scheduleId: newScheduleId(), projectId });
    setCronPreview(null);
    setMessage(null);
    setDrawerOpen(true);
  }

  async function generateCron(phrase = form.naturalLanguage) {
    setBusy(true);
    try {
      const response = await apiFetch("/api/schedules/cron-preview", {
        method: "POST",
        body: JSON.stringify({ naturalLanguage: phrase, timezone: form.timezone }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "자연어 주기를 크론으로 변환하지 못했습니다");
      const preview = body as CronPreview;
      setCronPreview(preview);
      setForm((current) => ({
        ...current,
        naturalLanguage: phrase,
        cronExpression: preview.cronExpression,
        startDate: preview.suggestedStartDate || current.startDate,
        endDate: preview.suggestedEndDate || current.endDate,
      }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "크론 생성 실패");
    } finally {
      setBusy(false);
    }
  }

  async function createSchedule() {
    if (!form.scheduleId || !form.name || !form.projectId || form.scenarioIds.length === 0) {
      setMessage("스케줄 ID·명칭·프로젝트·실행 시나리오를 모두 입력하세요.");
      return;
    }
    setBusy(true);
    try {
      const response = await apiFetch("/api/schedules", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          environmentId: form.environmentId || null,
          startDate: form.startDate || null,
          endDate: form.endDate || null,
          note: form.note || null,
          overlapPolicy: "skip",
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "스케줄 등록 실패");
      setMessage(`${body.name} 스케줄을 등록했습니다. 다음 실행 ${formatDateTime(body.nextRunAt)}`);
      setDrawerOpen(false);
      clear();
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "스케줄 등록 실패");
    } finally {
      setBusy(false);
    }
  }

  async function executeSchedules(ids: string[]) {
    if (ids.length === 0) return;
    setBusy(true);
    try {
      let started = 0;
      const failures: string[] = [];
      for (const id of ids) {
        const response = await apiFetch(`/api/schedules/${encodeURIComponent(id)}/execute`, { method: "POST" });
        const body = await response.json();
        if (response.ok) started += 1;
        else failures.push(`${id}: ${body.detail || "실행 실패"}`);
      }
      setMessage(`스케줄 ${started}건 실행 요청${failures.length ? ` · 실패 ${failures.length}건` : ""}`);
      clear();
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "스케줄 실행 실패");
    } finally {
      setBusy(false);
    }
  }

  async function toggleSchedule(schedule: Schedule) {
    setBusy(true);
    try {
      const response = await apiFetch(`/api/schedules/${encodeURIComponent(schedule.scheduleId)}`, {
        method: "PATCH",
        body: JSON.stringify({ enabled: !schedule.enabled }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "스케줄 상태 변경 실패");
      setMessage(`${body.name} · ${scheduleStatusKo(body.status)}`);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "스케줄 상태 변경 실패");
    } finally {
      setBusy(false);
    }
  }

  async function removeSchedules(ids: string[]) {
    if (!confirmBulkDelete("스케줄", ids.length)) return;
    setBusy(true);
    try {
      const response = await apiFetch("/api/schedules/bulk-delete", {
        method: "POST",
        body: JSON.stringify({ scheduleIds: ids }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "스케줄 삭제 실패");
      setMessage(body.message);
      clear();
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "스케줄 삭제 실패");
    } finally {
      setBusy(false);
    }
  }

  async function importSchedules(rows: CsvRow[]) {
    setBusy(true);
    let imported = 0;
    const failures: string[] = [];
    try {
      for (const row of rows) {
        const value = (...keys: string[]) => keys.map((key) => row[key]).find((item) => item != null)?.trim() || "";
        const projectKey = value("projectId", "프로젝트 ID", "프로젝트");
        const project = projects.find((item) => item.id === projectKey || item.name === projectKey);
        const scenarioIds = value("scenarioIds", "시나리오 ID", "테스트 시나리오 ID")
          .split(/[|;,]/)
          .map((item) => item.trim())
          .filter(Boolean);
        const scheduleId = value("scheduleId", "스케줄 ID", "스케쥴 ID");
        try {
          const response = await apiFetch("/api/schedules", {
            method: "POST",
            body: JSON.stringify({
              scheduleId,
              name: value("name", "스케줄 명", "스케쥴 명", "한글명"),
              projectId: project?.id || projectKey,
              scenarioIds,
              environmentId: value("environmentId", "실행환경 ID") || null,
              cronExpression: value("cronExpression", "크론", "크론식") || "0 5 * * *",
              timezone: value("timezone", "시간대") || "Asia/Seoul",
              startDate: value("startDate", "시작일") || null,
              endDate: value("endDate", "종료일") || null,
              enabled: !["false", "0", "중지"].includes(value("enabled", "활성").toLowerCase()),
              overlapPolicy: "skip",
              naturalLanguage: value("naturalLanguage", "자연어 주기") || null,
              note: value("note", "비고") || null,
            }),
          });
          const body = await response.json();
          if (!response.ok) throw new Error(body.detail || "등록 실패");
          imported += 1;
        } catch (error) {
          failures.push(`${scheduleId || "ID 없음"}: ${error instanceof Error ? error.message : "등록 실패"}`);
        }
      }
      setMessage(`스케줄 CSV ${imported}건 등록${failures.length ? ` · 실패 ${failures.length}건` : ""}`);
      await load();
      if (failures.length) throw new Error(failures.slice(0, 2).join(" · "));
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell
      testId="schedule-workbench"
      className="schedule-page"
      header={
        <div className="content-header">
          <div>
            <Breadcrumbs trail={[{ label: "콘솔", href: "/" }, { label: "관리" }, { label: "스케줄링" }]} />
            <h2>테스트 시나리오 스케줄링</h2>
            <p className="muted" style={{ marginTop: 6 }}>
              프로젝트와 테스트 시나리오 그룹을 고정해 반복 실행합니다. 기술 실행 완료는 HITL Pass가 아닙니다.
            </p>
          </div>
        </div>
      }
    >
      {message && <div className="connect-banner is-warn anim-slide-down" role="status">{message}</div>}

      <CommonDataTable
        rows={visibleSchedules}
        totalCount={schedules.length}
        filters={
          <>
            <label><select aria-label="프로젝트" value={projectScope} onChange={(event) => setProjectScope(event.target.value)}>{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
            <label><select aria-label="스케줄 상태" value={statusScope} onChange={(event) => setStatusScope(event.target.value)}><option value="ALL">전체 상태</option><option value="ACTIVE">예약 활성</option><option value="RUNNING">실행 중</option><option value="PAUSED">일시정지</option><option value="ERROR">실행 오류</option><option value="COMPLETED">예약 종료</option></select></label>
          </>
        }
        toolbar={
          <>
            <ScreenSearch
              value={query}
              onChange={setQuery}
              placeholder="스케줄 ID · 명칭 · 시나리오"
              hint="현재 프로젝트의 스케줄과 시나리오를 찾습니다"
              testId="schedule-search"
            />
            <TableBulkDeleteForm
              embedded
              noun="스케줄링 목록"
              totalCount={visibleSchedules.length}
              selectedCount={selectedIds.length}
              busy={busy}
              onDelete={() => void removeSchedules(selectedIds)}
              onImportCsv={(rows) => importSchedules(rows)}
              testId="schedule-bulk-form"
              extraActions={
                <>
                  <a className="ghost-btn" href="/templates/schedule-template.csv" download>템플릿 다운로드</a>
                  <button type="button" className="ghost-btn" onClick={openCreate} data-testid="schedule-create-open">스케줄링 등록</button>
                  <button type="button" className="action-btn" disabled={selectedIds.length === 0 || busy} onClick={() => void executeSchedules(selectedIds)} data-testid="schedule-run-selected">선택 실행</button>
                </>
              }
            />
          </>
        }
        rowKey={(schedule) => schedule.scheduleId}
        testId="schedule-table"
        loading={loading}
        emptyText={query ? `검색어 「${query}」와 맞는 스케줄이 없습니다.` : "현재 프로젝트에 등록된 스케줄이 없습니다."}
        loadingText="스케줄링 목록을 불러오는 중입니다"
        selection={{
          selected: checked,
          onChange: setChecked,
          label: (schedule) => `${schedule.name} 스케줄 선택`,
        }}
        timestamps={{
          createdAt: (schedule) => schedule.createdAt,
          updatedAt: (schedule) => schedule.updatedAt,
        }}
        columns={[
          {
            key: "id",
            label: "스케줄 ID",
            sortValue: (schedule) => schedule.scheduleId,
            cell: (schedule) => <span className="cell-stack mono-cell"><strong>{schedule.scheduleId}</strong><span>{schedule.timezone}</span></span>,
          },
          {
            key: "name",
            label: "한글명",
            sortValue: (schedule) => schedule.name,
            cell: (schedule) => <div className="cell-stack"><strong>{schedule.name}</strong><span>연결 시나리오 {schedule.scenarios.length}건</span></div>,
          },
          {
            key: "scope",
            label: "프로젝트 · 시나리오 그룹",
            sortValue: (schedule) => `${schedule.projectName} ${schedule.scenarios.map((scenario) => scenario.scenarioGroupName).join(" ")}`,
            cell: (schedule) => {
              const groups = Array.from(new Set(schedule.scenarios.map((scenario) => scenario.scenarioGroupName)));
              return <div className="cell-stack"><strong>{schedule.projectName}</strong><span>{groups.join(", ")}</span><small>{schedule.scenarios.slice(0, 2).map((scenario) => scenario.scenarioId).join(" · ")}{schedule.scenarios.length > 2 ? ` 외 ${schedule.scenarios.length - 2}건` : ""}</small></div>;
            },
          },
          {
            key: "status",
            label: "스케줄 상태",
            sortValue: (schedule) => schedule.status,
            cell: (schedule) => <><span className={`status-badge ${scheduleStatusClass(schedule.status)}`}>{scheduleStatusKo(schedule.status)}</span><div className="cell-subtle">{schedule.lastMessage || (schedule.enabled ? "중복 실행 건너뜀" : "예약 중지")}</div></>,
          },
          {
            key: "progress",
            label: "진행 건수",
            sortValue: (schedule) => schedule.progressTotal ? schedule.progressCompleted / schedule.progressTotal : 0,
            cell: (schedule) => {
              const progress = schedule.progressTotal ? Math.round((schedule.progressCompleted / schedule.progressTotal) * 100) : 0;
              return <div className="schedule-progress-cell"><strong>{schedule.progressCompleted}/{schedule.progressTotal || schedule.scenarios.length}건</strong><div className="schedule-mini-progress"><span style={{ width: `${progress}%` }} /></div><small>누적 실행 {schedule.runCount}건</small></div>;
            },
          },
          {
            key: "cron",
            label: "스케줄 주기",
            sortValue: (schedule) => schedule.cronExpression,
            cell: (schedule) => <div className="cell-stack"><strong>{schedule.cronSummary}</strong><span className="mono-cell">{schedule.cronExpression}</span></div>,
          },
          {
            key: "runAt",
            label: "실행 날짜",
            sortValue: (schedule) => new Date(schedule.nextRunAt || schedule.lastRunAt || 0).getTime(),
            cell: (schedule) => <div className="cell-stack"><strong>다음 {formatDateTime(schedule.nextRunAt)}</strong><span>최근 {formatDateTime(schedule.lastRunAt)}</span><small>{schedule.startDate || "즉시"} ~ {schedule.endDate || "종료일 없음"}</small></div>,
          },
        ]}
        actions={(schedule) => <><button type="button" className="proc-btn" disabled={busy || schedule.status === "RUNNING"} onClick={() => void executeSchedules([schedule.scheduleId])}>실행</button><button type="button" className="proc-btn" disabled={busy || schedule.status === "RUNNING"} onClick={() => void toggleSchedule(schedule)}>{schedule.enabled ? "중지" : "활성"}</button></>}
      />

      {drawerOpen && (
        <div className="schedule-drawer-layer" data-testid="schedule-drawer-layer">
          <button type="button" className="schedule-drawer-scrim" aria-label="스케줄 등록 닫기" onClick={() => setDrawerOpen(false)} />
          <aside className="schedule-drawer anim-slide-left" role="dialog" aria-modal="true" aria-labelledby="schedule-drawer-title" data-testid="schedule-drawer">
            <header className="schedule-drawer-head"><div><span className="panel-kicker">SCHEDULE REGISTRATION</span><h2 id="schedule-drawer-title">스케줄링 등록</h2><p>실행 영역·주기·운영 안전조건을 한 번에 등록합니다.</p></div><button type="button" className="ghost-btn" onClick={() => setDrawerOpen(false)}>닫기</button></header>
            <div className="schedule-drawer-body">
              <section className="schedule-form-section"><div className="section-heading-row"><div><span className="panel-kicker">01 · 기본 정보</span><h3>스케줄 식별 정보</h3></div><span className="status-badge status-info">SQLite 저장</span></div><div className="schedule-form-grid"><label><span>스케줄 ID (고유값)</span><input value={form.scheduleId} onChange={(event) => setForm((current) => ({ ...current, scheduleId: event.target.value }))} placeholder="SCH-WEEKDAY-0500" /></label><label><span>스케줄 명</span><input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} placeholder="매일 새벽 핵심 금융 시나리오" /></label></div></section>

              <section className="schedule-form-section"><div className="section-heading-row"><div><span className="panel-kicker">02 · 실행 대상</span><h3>프로젝트와 테스트 시나리오 연결</h3></div><span className="status-badge status-info">{form.scenarioIds.length}건 선택</span></div><label className="schedule-field"><span>프로젝트</span><select value={form.projectId} onChange={(event) => setForm((current) => ({ ...current, projectId: event.target.value, scenarioIds: [], environmentId: "" }))}>{projects.map((project) => <option key={project.id} value={project.id}>{project.name} · {project.id}</option>)}</select></label><button type="button" className="schedule-scenario-connect" onClick={() => setPickerOpen(true)} data-testid="schedule-scenario-picker-open"><span><strong>실행 스케줄 연결</strong><small>고유 ID와 한글명을 확인하고 테스트 시나리오를 선택합니다.</small></span><b>{form.scenarioIds.length ? `${form.scenarioIds.length}건 연결됨` : "목록 열기"}</b></button>{form.scenarioIds.length > 0 && <div className="schedule-selected-scenarios">{form.scenarioIds.map((id) => <span key={id}>{scenarioContexts.get(id)?.scenarioName || id}<small>{id}</small></span>)}</div>}<label className="schedule-field"><span>실행 환경</span><select value={form.environmentId} onChange={(event) => setForm((current) => ({ ...current, environmentId: event.target.value }))}><option value="">프로젝트 기본 활성 환경 자동 선택</option>{environments.map((environment) => <option key={environment.id} value={environment.id}>{environment.name} · {environment.lastHealthStatus || environment.status || "상태 미확인"}</option>)}</select></label></section>

              <section className="schedule-form-section"><div className="section-heading-row"><div><span className="panel-kicker">03 · 반복 주기</span><h3>자연어·캘린더·크론 설정</h3></div>{cronPreview && <span className="status-badge status-ok">{cronPreview.summary}</span>}</div><label className="schedule-field"><span>자연어로 주기 만들기</span><div className="schedule-inline-field"><input value={form.naturalLanguage} onChange={(event) => setForm((current) => ({ ...current, naturalLanguage: event.target.value }))} placeholder="일주일 동안 매일 새벽 5시에 돌려줘" /><Button size="sm" busy={busy} onClick={() => void generateCron()}>크론 생성</Button></div></label><div className="schedule-example-chips"><button type="button" onClick={() => void generateCron("매일 새벽 5시에 실행")}>매일 05:00</button><button type="button" onClick={() => void generateCron("평일 오전 9시에 실행")}>평일 09:00</button><button type="button" onClick={() => void generateCron("매주 월요일 오전 9시에 실행")}>매주 월 09:00</button></div><div className="schedule-form-grid three"><label><span>시작일</span><input type="date" value={form.startDate} onChange={(event) => setForm((current) => ({ ...current, startDate: event.target.value }))} /></label><label><span>종료일</span><input type="date" value={form.endDate} onChange={(event) => setForm((current) => ({ ...current, endDate: event.target.value }))} /></label><label><span>시간대</span><select value={form.timezone} onChange={(event) => setForm((current) => ({ ...current, timezone: event.target.value }))}><option value="Asia/Seoul">Asia/Seoul</option><option value="UTC">UTC</option><option value="America/New_York">America/New_York</option></select></label></div><label className="schedule-field"><span>크론탭 (분 시 일 월 요일)</span><input className="mono-cell" value={form.cronExpression} onChange={(event) => setForm((current) => ({ ...current, cronExpression: event.target.value }))} placeholder="0 5 * * *" /><small>예시: 0 5 * * * = 매일 05:00 · 0 9 * * 1-5 = 평일 09:00</small></label>{cronPreview?.nextRunAt && <div className="schedule-next-preview"><strong>다음 실행 예상</strong><span>{formatDateTime(cronPreview.nextRunAt)}</span></div>}</section>

              <section className="schedule-form-section"><div className="section-heading-row"><div><span className="panel-kicker">04 · 운영 안전</span><h3>자동 실행 보호 조건</h3></div></div><div className="schedule-safety-grid"><label><input type="checkbox" checked={form.enabled} onChange={(event) => setForm((current) => ({ ...current, enabled: event.target.checked }))} /><span><strong>등록 즉시 예약 활성화</strong><small>비활성으로 등록하면 목록에서 검토 후 활성화할 수 있습니다.</small></span></label><div><strong>중복 실행 건너뜀</strong><small>이전 실행이 끝나지 않았으면 같은 스케줄을 다시 시작하지 않습니다.</small></div><div><strong>데이터 변경 보호</strong><small>자동 스케줄은 파괴적 단계 허용 없이 실행하고 예외를 실행 이력과 HITL로 전달합니다.</small></div><div><strong>최종 판정 분리</strong><small>스케줄 완료는 기술 실행 완료이며 최종 Pass/Fail은 담당자가 확정합니다.</small></div></div><label className="schedule-field"><span>비고</span><textarea value={form.note} onChange={(event) => setForm((current) => ({ ...current, note: event.target.value }))} placeholder="담당자, 실행 목적, 확인할 운영 조건을 기록하세요." /></label></section>
            </div>
            <footer className="schedule-drawer-foot"><button type="button" className="ghost-btn" onClick={() => setDrawerOpen(false)}>취소</button><Button variant="primary" busy={busy} onClick={() => void createSchedule()} data-testid="schedule-create-submit">스케줄 등록</Button></footer>
          </aside>
        </div>
      )}

      {pickerOpen && (
        <div className="schedule-picker-layer" role="dialog" aria-modal="true" aria-labelledby="schedule-picker-title" data-testid="schedule-scenario-picker">
          <button type="button" className="schedule-picker-scrim" aria-label="시나리오 선택 닫기" onClick={() => setPickerOpen(false)} />
          <section className="schedule-picker"><header><div><span className="panel-kicker">TEST SCENARIO SELECTOR</span><h2 id="schedule-picker-title">실행할 테스트 시나리오 선택</h2><p>{projects.find((project) => project.id === form.projectId)?.name} 프로젝트 안에서만 선택합니다.</p></div><button type="button" className="ghost-btn" onClick={() => setPickerOpen(false)}>닫기</button></header><div className="schedule-picker-search"><ScreenSearch value={pickerQuery} onChange={setPickerQuery} placeholder="그룹명 · 시나리오명 · ID" testId="schedule-picker-search" /></div><div className="schedule-picker-body">{groupedPickerScenarios.map(([groupId, group]) => <section key={groupId}><header><strong>{group.name}</strong><span>{group.rows.length}건</span></header>{group.rows.map((scenario) => { const context = scenarioContexts.get(scenario.scenarioId); const checkedScenario = form.scenarioIds.includes(scenario.scenarioId); return <label key={scenario.scenarioId} className={checkedScenario ? "is-selected" : ""}><input type="checkbox" checked={checkedScenario} onChange={(event) => setForm((current) => ({ ...current, scenarioIds: event.target.checked ? [...current.scenarioIds, scenario.scenarioId] : current.scenarioIds.filter((id) => id !== scenario.scenarioId) }))} /><span><strong>{context?.scenarioName || scenario.name}</strong><small>{scenario.scenarioId}</small><em>{context?.businessGroupName}</em></span></label>; })}</section>)}{groupedPickerScenarios.length === 0 && <div className="empty-state">현재 프로젝트에 선택 가능한 시나리오가 없습니다.</div>}</div><footer><span>선택 {form.scenarioIds.length}건</span><Button variant="primary" onClick={() => setPickerOpen(false)}>선택 적용</Button></footer></section>
        </div>
      )}
    </PageShell>
  );
}

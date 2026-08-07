"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "../lib/apiClient";
import type { CsvRow } from "../lib/csv";
import { formatDateTime } from "../lib/datetime";
import { Breadcrumbs } from "./Breadcrumbs";
import { CommonDataTable } from "./CommonDataTable";
import { PageShell } from "./PageShell";
import { matchesQuery, ScreenSearch } from "./ScreenSearch";
import { TableBulkDeleteForm } from "./TableBulkDeleteForm";
import { Button } from "./ui/Button";

type MonitorSummary = {
  traces: number;
  running: number;
  complete: number;
  errors: number;
  modelDecisions: number;
  modelInvocations: number;
  modelFailures: number;
  selectedWithoutInvocation: number;
};
type Trace = {
  traceId: string;
  workflowId?: string | null;
  projectId?: string | null;
  startedAt: string;
  finishedAt?: string | null;
  status: string;
  durationMs?: number | null;
  stepCount: number;
  selectedModel?: string | null;
  selectedRoute?: string | null;
  decisionSummary?: string | null;
  modelExecutionStatus?: string | null;
  modelCallCount: number;
  modelTotalTokens: number;
  eventCount: number;
};
type AgentEvent = {
  eventId: string;
  traceId: string;
  occurredAt: string;
  eventType: string;
  workflowId?: string | null;
  projectId?: string | null;
  stepId?: string | null;
  agent?: string | null;
  skill?: string | null;
  tool?: string | null;
  status: string;
  summary: string;
  details: Record<string, unknown>;
};
type TraceDetail = { trace: Trace; events: AgentEvent[]; privacyNotice: string };
type Project = { id: string; name: string };

const EMPTY_SUMMARY: MonitorSummary = {
  traces: 0,
  running: 0,
  complete: 0,
  errors: 0,
  modelDecisions: 0,
  modelInvocations: 0,
  modelFailures: 0,
  selectedWithoutInvocation: 0,
};
const EVENT_LABEL: Record<string, string> = {
  workflow_started: "Workflow 시작",
  plan_created: "Plan 생성",
  model_candidates_evaluated: "모델 후보 평가",
  model_selected: "호출 후보 선택",
  model_invocation_completed: "모델 추론 확인",
  model_invocation_failed: "모델 응답 미사용",
  model_not_invoked: "모델 호출 없음",
  step_started: "Skill 실행 시작",
  step_completed: "Skill 실행 완료",
  step_failed: "Skill 실행 실패",
  review_completed: "Reviewer 검토",
  reduce_completed: "Context Reduce",
  workflow_completed: "Workflow 완료",
  workflow_failed: "Workflow 실패",
};

function statusLabel(status: string) {
  return { running: "진행 중", complete: "완료", error: "오류", info: "정보" }[status] || status;
}

function durationLabel(value?: number | null) {
  if (value == null) return "—";
  return value >= 1000 ? `${(value / 1000).toFixed(1)}초` : `${value}ms`;
}

function modelUsageLabel(status?: string | null) {
  return {
    used: "실제 호출 확인",
    failed: "응답 미사용",
    not_invoked: "호출 안 함",
    unverified: "과거 로그 · 확인 불가",
    not_required: "모델 불필요",
  }[status || ""] || "확인 전";
}

function modelUsageTone(status?: string | null) {
  if (status === "used") return "ok";
  if (status === "failed") return "bad";
  return "warn";
}

export function AgentMonitorWorkbench() {
  const [summary, setSummary] = useState(EMPTY_SUMMARY);
  const [traces, setTraces] = useState<Trace[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [projectId, setProjectId] = useState("");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [detail, setDetail] = useState<TraceDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const load = useCallback(async () => {
    const params = new URLSearchParams({ limit: "200" });
    if (status) params.set("status", status);
    if (projectId) params.set("projectId", projectId);
    const [summaryResponse, traceResponse, projectResponse] = await Promise.all([
      apiFetch("/api/agent-monitor/summary", { cache: "no-store" }),
      apiFetch(`/api/agent-monitor/traces?${params}`, { cache: "no-store" }),
      apiFetch("/api/projects", { cache: "no-store" }),
    ]);
    if (!summaryResponse.ok || !traceResponse.ok) throw new Error("Agent 실행 로그를 불러오지 못했습니다");
    setSummary((await summaryResponse.json()) as MonitorSummary);
    setTraces((await traceResponse.json()) as Trace[]);
    if (projectResponse.ok) setProjects((await projectResponse.json()) as Project[]);
  }, [projectId, status]);

  useEffect(() => {
    setLoading(true);
    load().catch((error: Error) => setMessage(error.message)).finally(() => setLoading(false));
  }, [load]);

  useEffect(() => {
    if (!traces.some((trace) => trace.status === "running")) return;
    const timer = window.setInterval(() => void load(), 1500);
    return () => window.clearInterval(timer);
  }, [traces, load]);

  const projectName = useMemo(() => new Map(projects.map((project) => [project.id, project.name])), [projects]);
  const visible = useMemo(
    () => traces.filter((trace) => matchesQuery(query, trace.traceId, trace.workflowId, trace.projectId, projectName.get(trace.projectId || ""), trace.selectedModel, trace.decisionSummary)),
    [traces, query, projectName],
  );

  async function openDetail(traceId: string) {
    setDetailLoading(true);
    try {
      const response = await apiFetch(`/api/agent-monitor/traces/${traceId}`, { cache: "no-store" });
      if (!response.ok) throw new Error("Trace 상세를 불러오지 못했습니다");
      setDetail((await response.json()) as TraceDetail);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Trace 상세 조회 실패");
    } finally {
      setDetailLoading(false);
    }
  }

  async function rejectImport(_: CsvRow[]) {
    throw new Error("Agent 감사 로그는 무결성 보호를 위해 가져오기·수정·삭제할 수 없습니다");
  }

  return (
    <PageShell
      testId="agent-monitor-page"
      header={
        <div className="content-header">
          <div>
            <Breadcrumbs trail={[{ label: "콘솔" }, { label: "관리" }, { label: "Agent 모니터링" }]} />
            <h2>Agent 모니터링</h2>
            <p className="muted" style={{ marginTop: 6 }}>
              어떤 작업이 어떤 모델을 골랐고, 실제 추론까지 이어졌는지 한눈에 확인합니다.
            </p>
          </div>
        </div>
      }
    >
      <div className="agent-privacy-banner"><strong>선택과 사용을 따로 기록합니다</strong><span>모델을 고른 기록만으로 사용했다고 표시하지 않습니다. 실제 요청 ID·처리 시간·토큰 사용량이 확인된 호출만 집계합니다.</span></div>
      {message && <div className="agent-notice">{message}</div>}
      <div className="agent-summary-grid">
        <article><span>전체 Trace</span><strong>{summary.traces}</strong></article>
        <article><span>진행 중</span><strong>{summary.running}</strong></article>
        <article><span>완료</span><strong>{summary.complete}</strong></article>
        <article><span>오류</span><strong>{summary.errors}</strong></article>
        <article><span>모델 후보 선택</span><strong>{summary.modelDecisions}</strong></article>
        <article><span>실제 모델 호출</span><strong>{summary.modelInvocations}</strong></article>
        <article><span>선택 후 미호출</span><strong>{summary.selectedWithoutInvocation}</strong></article>
      </div>
      <CommonDataTable
        rows={visible}
        totalCount={traces.length}
        filters={
          <>
            <label><select aria-label="프로젝트" value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">전체 프로젝트</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
            <label><select aria-label="상태" value={status} onChange={(event) => setStatus(event.target.value)}><option value="">전체 상태</option><option value="running">진행 중</option><option value="complete">완료</option><option value="error">오류</option></select></label>
          </>
        }
        toolbar={
          <>
            <ScreenSearch value={query} onChange={setQuery} placeholder="프로젝트 · Workflow · Plan · 모델" />
            <TableBulkDeleteForm
              embedded
              noun="Agent Trace"
              totalCount={visible.length}
              selectedCount={0}
              onDelete={() => undefined}
              onImportCsv={rejectImport}
              testId="agent-trace-table-bulk-form"
              extraActions={<Button variant="secondary" size="sm" onClick={() => void load()}>새로고침</Button>}
            />
          </>
        }
        rowKey={(trace) => trace.traceId}
        testId="agent-trace-table"
        loading={loading}
        emptyText="아직 Agent 실행 Trace가 없습니다"
        loadingText="Agent 실행 로그를 불러오는 중입니다"
        timestamps={{
          createdAt: (trace) => trace.startedAt,
          updatedAt: (trace) => trace.finishedAt,
        }}
        columns={[
          {
            key: "project",
            label: "프로젝트",
            sortValue: (trace) => projectName.get(trace.projectId || "") || trace.projectId || "",
            cell: (trace) => <span className="cell-stack"><strong>{projectName.get(trace.projectId || "") || "공통 시스템"}</strong><small>{trace.projectId || "—"}</small></span>,
          },
          {
            key: "workflow",
            label: "Workflow / Plan",
            sortValue: (trace) => `${trace.workflowId || ""} ${trace.traceId}`,
            cell: (trace) => <button className="link-btn agent-trace-link" onClick={() => void openDetail(trace.traceId)}><strong>{trace.workflowId || "—"}</strong><small>{trace.traceId}</small></button>,
          },
          {
            key: "status",
            label: "상태",
            sortValue: (trace) => trace.status,
            cell: (trace) => <span className={`status-badge status-${trace.status === "complete" ? "ok" : trace.status === "error" ? "bad" : "warn"}`}>{statusLabel(trace.status)}</span>,
          },
          {
            key: "model",
            label: "모델 사용",
            sortValue: (trace) => trace.selectedModel || trace.selectedRoute || "",
            cell: (trace) => <span className="cell-stack"><strong>{trace.selectedModel || (trace.selectedRoute === "deterministic_fallback" ? "규칙 기반" : "모델 미사용")}</strong><small className={`model-usage-state is-${modelUsageTone(trace.modelExecutionStatus)}`}>{modelUsageLabel(trace.modelExecutionStatus)}{trace.modelCallCount ? ` · ${trace.modelCallCount}회 · ${trace.modelTotalTokens} token` : ""}</small></span>,
          },
          {
            key: "steps",
            label: "단계",
            sortValue: (trace) => trace.stepCount,
            cell: (trace) => `${trace.stepCount} step · ${trace.eventCount} event`,
          },
          {
            key: "duration",
            label: "시간",
            sortValue: (trace) => trace.durationMs ?? -1,
            cell: (trace) => durationLabel(trace.durationMs),
          },
        ]}
        actions={(trace) => <Button variant="secondary" size="sm" busy={detailLoading} onClick={() => void openDetail(trace.traceId)}>선택 근거</Button>}
      />
      {detail && (
        <div className="schedule-drawer-layer" data-testid="agent-trace-drawer">
          <button className="schedule-drawer-scrim" aria-label="Trace 상세 닫기" onClick={() => setDetail(null)} />
          <aside className="schedule-drawer agent-trace-drawer">
            <header className="schedule-drawer-head"><div><span className="eyebrow">AGENT TRACE</span><h2>{detail.trace.workflowId}</h2><p>{detail.trace.traceId} · {projectName.get(detail.trace.projectId || "") || detail.trace.projectId || "공통 시스템"}</p></div><Button variant="secondary" onClick={() => setDetail(null)}>닫기</Button></header>
            <div className="schedule-drawer-body">
              <div className="agent-privacy-banner compact"><strong>공개 범위</strong><span>{detail.privacyNotice}</span></div>
              <section className="agent-decision-card">
                <div><span>모델 후보</span><strong>{detail.trace.selectedModel || "규칙 기반"}</strong></div>
                <div className="agent-model-use-row"><span>실제 추론</span><b className={`model-usage-state is-${modelUsageTone(detail.trace.modelExecutionStatus)}`}>{modelUsageLabel(detail.trace.modelExecutionStatus)}</b></div>
                <p>{detail.trace.modelExecutionStatus === "used" ? `Provider 호출 ${detail.trace.modelCallCount}회 · 총 ${detail.trace.modelTotalTokens} token을 확인했습니다.` : detail.trace.decisionSummary || "이 작업은 모델 호출이 필요하지 않았습니다."}</p>
              </section>
              <ol className="agent-event-timeline">
                {detail.events.map((event) => {
                  const candidates = Array.isArray(event.details.candidates) ? (event.details.candidates as Array<Record<string, unknown>>) : [];
                  const steps = Array.isArray(event.details.steps) ? (event.details.steps as Array<Record<string, unknown>>) : [];
                  const toolHistory = Array.isArray(event.details.toolHistory) ? event.details.toolHistory.map(String) : [];
                  const isModelReceipt = ["model_invocation_completed", "model_invocation_failed", "model_not_invoked"].includes(event.eventType);
                  const correlation = event.details.correlation && typeof event.details.correlation === "object" ? event.details.correlation as Record<string, unknown> : {};
                  return <li key={event.eventId} className={`is-${event.status}`}><span className="agent-event-dot" /><article><header><div><small>{formatDateTime(event.occurredAt)}</small><h3>{EVENT_LABEL[event.eventType] || event.eventType}</h3></div><span className={`status-badge status-${event.status === "complete" ? "ok" : event.status === "error" ? "bad" : "warn"}`}>{statusLabel(event.status)}</span></header><p>{event.summary}</p>{event.skill && <div className="agent-event-path"><span>{event.agent}</span><b>→</b><span>{event.skill}</span><b>→</b><span>{event.tool}</span></div>}
                    {Object.keys(correlation).length > 0 && <div className="agent-event-path" aria-label="실행 연결 정보">{Object.entries(correlation).map(([key, value]) => <span key={key}>{key}: {String(value)}</span>)}</div>}
                    {toolHistory.length > 0 && <div className="agent-tool-receipt"><strong>브라우저 도구 사용 이력</strong><div>{toolHistory.map((tool) => <span key={tool}>{tool}</span>)}</div><small>{String(event.details.browserRunner || "browser runner 미기록")} · {String(event.details.toolCallCount || toolHistory.length)}회 호출 · Network {String(event.details.networkRequestCount || 0)}건 / 매칭 {String(event.details.matchedNetworkRequestCount || 0)}건</small></div>}
                    {isModelReceipt && <div className="agent-tool-receipt model-receipt"><strong>모델 호출 영수증</strong><div><span>{String(event.details.displayName || event.details.model || "선택 모델")}</span><span>{String(event.details.operation || "호출 없음")}</span></div><small>{event.details.providerRequestId ? `응답 ID ${String(event.details.providerRequestId)} · ` : ""}{event.details.durationMs != null ? `${String(event.details.durationMs)}ms · ` : ""}입력 {String(event.details.promptTokens ?? "—")} / 출력 {String(event.details.completionTokens ?? "—")} / 전체 {String(event.details.totalTokens ?? "—")} token</small></div>}
                    {steps.length > 0 && <div className="agent-plan-steps">{steps.map((step, index) => <div key={String(step.stepId || index)}><strong>{String(step.stepId || index + 1)} · {String(step.skill || "")}</strong><span>{String(step.capability || "")}</span><small>{String(step.selectionReason || "")}</small></div>)}</div>}
                    {candidates.length > 0 && <div className="agent-candidate-list">{candidates.map((candidate) => <div key={String(candidate.modelProfileId)} className={candidate.eligible ? "is-eligible" : "is-excluded"}><strong>{String(candidate.displayName || candidate.modelId)}</strong><span>{candidate.eligible ? `점수 ${String(candidate.score ?? "—")}` : "제외"}</span><small>{Array.isArray(candidate.reasons) ? candidate.reasons.join(" · ") || "필수 조건 충족" : "필수 조건 충족"}</small></div>)}</div>}
                  </article></li>;
                })}
              </ol>
            </div>
            <footer className="schedule-drawer-foot"><span className="muted">Trace는 변경 불가능한 운영 감사 자료입니다.</span><Button onClick={() => setDetail(null)}>확인</Button></footer>
          </aside>
        </div>
      )}
    </PageShell>
  );
}

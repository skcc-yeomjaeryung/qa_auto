"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { BindingAssertionsTable } from "../../../components/BindingAssertionsTable";
import { EvidenceGallery } from "../../../components/EvidenceGallery";
import { EvidencePackageViewer } from "../../../components/EvidencePackageViewer";
import { PageShell, PageStickyFooter } from "../../../components/PageShell";
import { RunTraceTimeline } from "../../../components/RunTraceTimeline";
import { narrateRunSteps } from "../../../lib/scenarioNarration";
import { Breadcrumbs } from "../../../components/Breadcrumbs";
import { formatDateTime } from "../../../lib/datetime";
import { BIND_SOURCE_LABEL } from "../../../lib/evidenceLabels";
import { apiFetch } from "../../../lib/apiClient";

export default function RunDetailPage() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId;
  const [run, setRun] = useState<Record<string, any> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch(`/api/runs/${runId}`, { cache: "no-store" })
      .then(async (res) => {
        if (!res.ok) throw new Error("실행 이력을 찾을 수 없습니다");
        setRun(await res.json());
      })
      .catch((e: Error) => setError(e.message));
  }, [runId]);

  const narrative = useMemo(() => narrateRunSteps(run?.steps || []), [run]);

  return (
    <PageShell
      header={
        <div className="content-header">
          <div>
            <Breadcrumbs trail={[{ label: "콘솔", href: "/" }, { label: "실행 이력", href: "/runs" }, { label: "실행 상세" }]} />
            <h2>{runId}</h2>
            <p className="muted" style={{ marginTop: 6 }}>
              시나리오 {run?.scenarioId || "—"} · 화면 DOM·스크린샷 기준 관측
            </p>
          </div>
        </div>
      }
      footer={
        <PageStickyFooter
          testId="run-detail-footer"
          note="관측 요약만 제공합니다. Pass/Fail·배포는 HITL입니다."
          actions={
            <>
              {run?.scenarioId && (
                <Link className="ghost-btn" href={`/scenarios/${run.scenarioId}`}>
                  시나리오
                </Link>
              )}
              <Link className="primary-btn" href="/runs">
                목록으로
              </Link>
            </>
          }
        />
      }
    >
        {error && <div className="connect-banner is-warn">{error}</div>}

        {run && (
          <>
            <div className="run-summary-bar">
              <span className={`outcome-pill outcome-${run.outcomeKind || "unknown"}`}>
                {statusKo(run.status)}
              </span>
              <span className="muted">{run.outcomeSummary || run.observationSummary || "관측 요약 없음"}</span>
              <span className="muted">실행 {formatDateTime(run.createdAt)}</span>
            </div>

            {run.result?.runNarrative && (
              <section className="run-narrative-card" data-testid="run-narrative">
                <h3 className="section-title" style={{ marginTop: 0 }}>
                  실행 결과 요약
                  <span className="muted" style={{ marginLeft: 8, fontWeight: 400 }}>
                    {run.result.runNarrativeMode === "llm" ? "LLM 요약" : "규칙 기반 요약"}
                  </span>
                </h3>
                <p>{run.result.runNarrative}</p>
              </section>
            )}

            {run.result?.runDiagnosis && (
              <section
                className={`run-diagnosis-card is-${run.result.runDiagnosis.outcome || "undetermined"}`}
                data-testid="run-diagnosis"
              >
                <div className="section-heading-row">
                  <div>
                    <span className="panel-kicker">결과 원인·조치</span>
                    <h3 className="section-title">{run.result.runDiagnosis.headline || "실행 결과 분석"}</h3>
                  </div>
                  <span className="status-badge status-info">
                    {run.result.runDiagnosis.mode === "llm" ? "AI 보강 · 근거 제한" : "관측 규칙 기반"}
                  </span>
                </div>
                <div className="run-diagnosis-cause">
                  <strong>왜 이런 결과가 나왔나요?</strong>
                  <p>{run.result.runDiagnosis.causeSummary || "관측된 원인 요약이 없습니다"}</p>
                </div>
                {Array.isArray(run.result.runDiagnosis.evidence) && run.result.runDiagnosis.evidence.length > 0 && (
                  <div className="run-diagnosis-evidence">
                    <strong>개발자에게 제시할 근거</strong>
                    <ul>
                      {run.result.runDiagnosis.evidence.map((item: string, index: number) => (
                        <li key={`${item}-${index}`}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {Array.isArray(run.result.runDiagnosis.actions) && run.result.runDiagnosis.actions.length > 0 && (
                  <ol className="run-action-list">
                    {run.result.runDiagnosis.actions.map((item: Record<string, string>, index: number) => (
                      <li key={`${item.owner}-${index}`}>
                        <span>{index + 1}</span>
                        <div>
                          <strong>{item.owner || "개발·QA 담당"}</strong>
                          <p>{item.action || "조치 내용을 확인하세요"}</p>
                          {item.reason && <small>근거: {item.reason}</small>}
                        </div>
                      </li>
                    ))}
                  </ol>
                )}
                {run.result.runDiagnosis.retestCondition && (
                  <p className="run-retest-condition">
                    <strong>재검증 조건</strong>{run.result.runDiagnosis.retestCondition}
                  </p>
                )}
                {run.result.runDiagnosis.handoffMessage && (
                  <blockquote className="run-handoff-message">
                    <strong>담당자 전달문</strong>
                    <p>{run.result.runDiagnosis.handoffMessage}</p>
                  </blockquote>
                )}
              </section>
            )}

            {Array.isArray(run.result?.inputBindings) && run.result.inputBindings.length > 0 && (
              <section data-testid="run-input-bindings">
                <h3 className="section-title">화면에 넣은 입력값</h3>
                <div className="table-scroll">
                  <table className="data-table enterprise-table">
                    <thead>
                      <tr>
                        <th>입력 항목</th>
                        <th>넣은 값</th>
                        <th style={{ width: 120 }}>출처</th>
                        <th>근거</th>
                        <th style={{ width: 90 }}>입력 여부</th>
                      </tr>
                    </thead>
                    <tbody>
                      {run.result.inputBindings.map(
                        (bind: Record<string, any>, idx: number) => (
                          <tr key={`${bind.field}-${idx}`}>
                            <td>{bind.field}</td>
                            <td className="mono-cell">{bind.value ?? "—"}</td>
                            <td>
                              <span className="type-pill">
                                {BIND_SOURCE_LABEL[bind.source] || bind.source}
                              </span>
                            </td>
                            <td className="muted">{bind.rationale}</td>
                            <td>{bind.filled ? "입력됨" : "미입력"}</td>
                          </tr>
                        ),
                      )}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            <h3 className="section-title">테스트 진행 흐름 (화면 → 서버 → 화면)</h3>
            <RunTraceTimeline runId={runId} />

            <BindingAssertionsTable runId={runId} />

            <EvidencePackageViewer runId={runId} />

            <h3 className="section-title">시나리오 실행 단계</h3>
            <ol className="narrative-timeline">
              {narrative.map((step) => (
                <li key={step.order} className={`narrative-item is-${step.status}`}>
                  <div className="narrative-order">{step.order}</div>
                  <div className="narrative-body">
                    <strong>
                      {step.title}{" "}
                      <span className={`outcome-pill outcome-${step.status === "success" ? "success" : step.status === "failure" ? "be_error" : "unknown"}`}>
                        {step.status === "success"
                          ? "성공"
                          : step.status === "failure"
                            ? "실패"
                            : step.status === "pending"
                              ? "진행중"
                              : "확인필요"}
                      </span>
                    </strong>
                    <p>{step.detail}</p>
                    <small>사유: {step.reason}</small>
                  </div>
                </li>
              ))}
            </ol>

            <EvidenceGallery runId={runId} scenarioId={run.scenarioId} />

            <details className="tech-details">
              <summary>기술 로그 (참고)</summary>
              <pre className="rr-pre">{JSON.stringify(run.steps || [], null, 2)}</pre>
            </details>
          </>
        )}
    </PageShell>
  );
}

function statusKo(status: string) {
  const map: Record<string, string> = {
    WAITING_FOR_REVIEW: "검토 대기",
    AUTO_FAILED: "자동 실패",
    CANCELLED: "취소됨",
    RUNNING: "실행 중",
  };
  return map[status] || status;
}

"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../lib/apiClient";
import { formatDateTime } from "../lib/datetime";
import { missingEvidenceDetail, type MissingEvidenceDetail } from "../lib/evidenceLabels";
import { CommonDialogTabs } from "./CommonDialogTabs";
import { EvidenceGallery } from "./EvidenceGallery";
import { EvidencePackageViewer } from "./EvidencePackageViewer";
import { actionToastId, showActionToast } from "../lib/actionToast";
import { AssistantGuide } from "./AssistantGuide";
import { getDiagnosisCopy } from "../lib/diagnosisCopy";

type ReportAssertion = {
  assertionId: string;
  field: string;
  result: string;
  expected: string;
  actual: string;
  businessReviewRequired: boolean;
  missingData: string[];
};

type RunReport = {
  schemaVersion: "run-report/v1";
  reportId: string;
  runId: string;
  title: string;
  project: { id: string; name: string };
  scenario: {
    id: string;
    name: string;
    version: string;
    serviceId: string;
    businessPath: string[];
    sourceRoute: string;
    destinationRoute: string;
    request: { method: string; path: string };
  };
  execution: {
    technicalStatus: string;
    startedAt: string;
    endedAt: string;
    durationMs?: number | null;
    environmentName: string;
    outcomeKind: string;
    outcomeSummary: string;
  };
  observations: Array<{
    stepId: string;
    action: string;
    status: string;
    observation: string;
    missingData: string[];
  }>;
  verification: {
    technicalStatus: string;
    businessReviewRequired: boolean;
    totalCount: number;
    matchedCount: number;
    mismatchCount: number;
    missingCount: number;
    reviewRequiredCount: number;
    assertions: ReportAssertion[];
  };
  evidence: {
    evidenceId: string;
    integrityStatus: string;
    storageStatus: string;
    screenshotCount: number;
    snapshotCount: number;
    artifactCount: number;
    maskedArtifactCount: number;
    retentionUntil: string;
    downloadReady: boolean;
    missingData: string[];
    artifacts: Array<{
      artifactId: string;
      type: string;
      label: string;
      path: string;
      mimeType: string;
      size: number;
      sha256: string;
      masked: boolean;
      stage?: string | null;
    }>;
  };
  diagnosis: {
    outcome: string;
    headline: string;
    problemSummary: string;
    causeCategory: string;
    causeSummary: string;
    evidence: string[];
    actions: Array<{ owner: string; action: string; reason: string }>;
    retestCondition: string;
    handoffMessage: string;
    mode: string;
    humanDecisionRequired: true;
  };
  review: {
    finalDecision: "PENDING_HUMAN_REVIEW";
    hitlRequired: true;
    checklist: string[];
    attentionItems: string[];
    guardrail: string;
  };
  generatedBy: { agentName: string; workflowId: string; traceId: string; generatedAt: string };
  missingData: string[];
  missingDataDetails?: MissingEvidenceDetail[];
};

export function RunReportDrawer({
  runId,
  open,
  onClose,
  context,
}: {
  runId: string | null;
  open: boolean;
  onClose: () => void;
  context?: { projectName?: string; groupName?: string; scenarioName?: string } | null;
}) {
  const [report, setReport] = useState<RunReport | null>(null);
  const [activeTab, setActiveTab] = useState("report");
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    try {
      let response = await apiFetch(`/api/runs/${encodeURIComponent(runId)}/report`, { cache: "no-store" });
      if (response.status === 404) {
        response = await apiFetch(`/api/runs/${encodeURIComponent(runId)}/report`, {
          method: "POST",
          body: JSON.stringify({ force: false }),
        });
      }
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as { detail?: string } | null;
        throw new Error(payload?.detail || "실행 리포트를 생성하지 못했습니다");
      }
      setReport((await response.json()) as RunReport);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "REPORT AGENT 실행에 실패했습니다");
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    if (!open) return;
    setActiveTab("report");
    setReport(null);
    void load();
  }, [open, load]);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [open, onClose]);

  async function download(format: "html" | "json") {
    if (!runId) return;
    const toastId = actionToastId("report-download", `${runId}-${format}`);
    const formatLabel = format === "html" ? "통합 리포트" : "리포트 JSON";
    showActionToast({
      id: toastId,
      title: "리포트 다운로드",
      message: `${report?.scenario.name || runId} ${formatLabel} 다운로드를 시작했습니다.`,
      tone: "progress",
    });
    setDownloading(format);
    setError(null);
    try {
      const response = await apiFetch(`/api/runs/${encodeURIComponent(runId)}/report/download?format=${format}`);
      if (!response.ok) throw new Error("리포트 다운로드에 실패했습니다");
      const blob = await response.blob();
      const href = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = href;
      link.download = `${runId}-review-report.${format}`;
      link.click();
      URL.revokeObjectURL(href);
      showActionToast({ id: toastId, title: "리포트 다운로드 완료", message: `${formatLabel} 파일을 내려받았습니다.`, tone: "success" });
    } catch (reason) {
      const errorMessage = reason instanceof Error ? reason.message : "다운로드에 실패했습니다";
      setError(errorMessage);
      showActionToast({ id: toastId, title: "리포트 다운로드 실패", message: errorMessage, tone: "error" });
    } finally {
      setDownloading(null);
    }
  }

  if (!open) return null;

  const contextLine = report?.project.name || context?.projectName || context?.groupName;
  const diagnosisText = getDiagnosisCopy(report?.diagnosis.outcome);

  return (
    <div className="run-drawer-layer" data-testid="run-report-drawer-layer">
      <button className="run-drawer-scrim" type="button" aria-label="증적·리포트 검토 닫기" onClick={onClose} />
      <aside
        className="run-evidence-drawer run-report-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="run-report-drawer-title"
        data-testid="run-report-drawer"
      >
        <header className="run-drawer-head">
          <div>
            <span className="panel-kicker">REPORT AGENT · HITL REVIEW</span>
            <h2 id="run-report-drawer-title">{context?.scenarioName || report?.scenario.name || "실행 검토 리포트"}</h2>
            <p className="run-drawer-context-name">{contextLine || "프로젝트·시나리오 그룹 확인 중"}</p>
            <p>{runId} · 자동 관측과 증적을 담당자 검토용으로 정리합니다.</p>
          </div>
          <button type="button" className="ghost-btn" onClick={onClose}>닫기</button>
        </header>

        <div className="run-drawer-body">
          <AssistantGuide compact title="보고서 전체 흐름부터 증적까지 준비했어요" message="도넛 요약과 실행 결과를 먼저 확인한 뒤, 단계별 증적까지 이어서 검토하고 다운로드할 수 있습니다." />
          {loading && (
            <div className="report-agent-loading" role="status">
              <span className="report-agent-orbit" aria-hidden="true">✦</span>
              <div><strong>REPORT AGENT가 리포트를 구성하고 있어요</strong><p>실행 단계·기술 검증·증적 무결성을 고정 계약에 맞춰 확인합니다.</p></div>
            </div>
          )}
          {error && <div className="connect-banner is-warn" role="alert">{error} <button type="button" onClick={() => void load()}>다시 시도</button></div>}
          {report && (
            <CommonDialogTabs
              value={activeTab}
              onChange={setActiveTab}
              label="HITL 증적·리포트 검토"
              tabs={[
                { id: "report", label: "실행 리포트", count: report.review.attentionItems.length },
                { id: "verification", label: "기술 검증", count: report.verification.totalCount },
                { id: "evidence", label: "증적 패키지", count: report.evidence.artifactCount },
              ]}
            />
          )}

          {report && activeTab === "report" && (
            <div className="run-report-content">
              <section className="report-human-guard">
                <span>담당자 검토 대기</span>
                <div><strong>자동 실행 완료는 최종 Pass가 아닙니다.</strong><p>{report.review.guardrail}</p></div>
              </section>

              <section className="report-overview-grid" aria-label="리포트 핵심 상태">
                <div><span>기술 실행</span><strong>{technicalLabel(report.execution.technicalStatus)}</strong></div>
                <div className={`is-${report.diagnosis.outcome}`}><span>AI 관측 판정</span><strong>{diagnosisLabel(report.diagnosis.outcome)}</strong></div>
                <div><span>기술 검증</span><strong>{verificationLabel(report.verification.technicalStatus)}</strong></div>
                <div><span>증적 무결성</span><strong>{integrityLabel(report.evidence.integrityStatus)}</strong></div>
              </section>

              <section className="report-route-card">
                <span className="panel-kicker">A → API → B 관통 경로</span>
                <div>
                  <strong>{report.scenario.sourceRoute}</strong><i>→</i>
                  <em>{report.scenario.request.method} {report.scenario.request.path}</em><i>→</i>
                  <strong>{report.scenario.destinationRoute}</strong>
                </div>
                <p>{report.execution.outcomeSummary}</p>
              </section>

              <section className={`report-diagnosis is-${report.diagnosis.outcome}`} data-testid="report-diagnosis">
                <div className="section-heading-row">
                  <div><span className="panel-kicker">REPORT AGENT · 관측 근거 기반</span><h3 className="section-title">{report.diagnosis.headline}</h3></div>
                  <span className={`status-badge ${report.diagnosis.outcome === "failure" ? "status-danger" : report.diagnosis.outcome === "success" ? "status-success" : "status-warning"}`}>
                    {diagnosisLabel(report.diagnosis.outcome)}
                  </span>
                </div>
                <div className="report-diagnosis-grid">
                  <div><strong>{diagnosisText.primaryQuestion}</strong><p>{report.diagnosis.problemSummary}</p></div>
                  <div><strong>{diagnosisText.causeQuestion}</strong><p>{report.diagnosis.causeSummary}</p></div>
                </div>
                <div className="report-diagnosis-actions">
                  <strong>{diagnosisText.actionTitle}</strong>
                  {report.diagnosis.actions.length ? report.diagnosis.actions.map((item, index) => (
                    <article key={`${item.owner}-${index}`}><span>{item.owner}</span><p>{item.action}</p><small>{item.reason}</small></article>
                  )) : <p>{diagnosisText.emptyAction}</p>}
                </div>
                <p className="report-retest"><strong>{diagnosisText.retestLabel}</strong>{report.diagnosis.retestCondition}</p>
              </section>

              <section className="report-review-section">
                <div className="section-heading-row"><h3 className="section-title">먼저 확인할 내용</h3><span className="status-badge status-info">{report.review.attentionItems.length}건</span></div>
                <ul className="report-attention-list">
                  {report.review.attentionItems.map((item, index) => <li key={`${item}-${index}`}><span>{index + 1}</span><strong>{item}</strong></li>)}
                </ul>
              </section>

              <section className="report-review-section">
                <h3 className="section-title">승인 전 체크리스트</h3>
                <ul className="report-checklist">
                  {report.review.checklist.map((item) => <li key={item}><span aria-hidden="true">□</span>{item}</li>)}
                </ul>
              </section>

              {report.missingData.length > 0 ? (
                <section className="report-missing-section" aria-label="추가 확인이 필요한 자료">
                  <h3 className="section-title">추가 확인이 필요한 자료</h3>
                  <div className="report-missing-grid">
                    {(report.missingDataDetails?.length
                      ? report.missingDataDetails
                      : report.missingData.map(missingEvidenceDetail)
                    ).map((item) => (
                      <article className="report-missing-card" key={item.code}>
                        <span>{item.section}</span>
                        <strong>{item.label}</strong>
                        <p>{item.guidance}</p>
                      </article>
                    ))}
                  </div>
                </section>
              ) : null}
              <p className="report-trace-note">{report.schemaVersion} · {report.generatedBy.workflowId} · {report.generatedBy.traceId}</p>
            </div>
          )}

          {report && activeTab === "verification" && (
            <div className="run-report-content">
              <section className="report-verification-summary">
                <div><span>전체</span><strong>{report.verification.totalCount}</strong></div>
                <div className="is-good"><span>일치</span><strong>{report.verification.matchedCount}</strong></div>
                <div className="is-bad"><span>불일치</span><strong>{report.verification.mismatchCount}</strong></div>
                <div className="is-warn"><span>누락·검토</span><strong>{report.verification.missingCount + report.verification.reviewRequiredCount}</strong></div>
              </section>
              <section>
                <h3 className="section-title">기대값과 실제 관측값</h3>
                <div className="report-assertion-table">
                  <table><thead><tr><th>검증 항목</th><th>결과</th><th>기대값</th><th>관측값</th></tr></thead>
                    <tbody>{report.verification.assertions.length ? report.verification.assertions.map((row) => (
                      <tr key={row.assertionId}><td><strong>{fieldLabel(row.field)}</strong>{row.businessReviewRequired && <small>담당자 확인</small>}</td><td><span className={`report-result-tag is-${row.result.toLowerCase()}`}>{assertionLabel(row.result)}</span></td><td>{displayEvidenceValue(row.expected)}</td><td>{displayEvidenceValue(row.actual)}</td></tr>
                    )) : <tr><td colSpan={4} className="muted">등록된 기술 검증 항목이 없습니다.</td></tr>}</tbody>
                  </table>
                </div>
              </section>
              <section className="run-drawer-steps">
                <h3 className="section-title">리포트에 포함된 실행 단계</h3>
                <ol>{report.observations.map((step) => <li key={step.stepId}><span className={`run-step-dot is-${step.status}`} /><div><strong>{step.stepId} · {actionLabel(step.action)}</strong><p>{step.observation}</p></div></li>)}</ol>
              </section>
            </div>
          )}

          {report && activeTab === "evidence" && (
            <div className="run-drawer-evidence-tab">
              <EvidencePackageViewer runId={report.runId} />
              <EvidenceGallery runId={report.runId} scenarioId={report.scenario.id} />
            </div>
          )}
        </div>

        <footer className="run-drawer-foot run-report-footer">
          <span>REPORT AGENT 결과는 동일 JSON 계약에서 HTML로 렌더링됩니다.</span>
          <button className="ghost-btn" type="button" disabled={!report || Boolean(downloading)} onClick={() => void download("json")}>{downloading === "json" ? "준비 중…" : "JSON 다운로드"}</button>
          <button className="primary-btn" type="button" disabled={!report || Boolean(downloading)} onClick={() => void download("html")}>{downloading === "html" ? "준비 중…" : "리포트 다운로드"}</button>
        </footer>
      </aside>
    </div>
  );
}

const technicalLabel = (value: string) => ({ WAITING_FOR_REVIEW: "실행 완료", AUTO_FAILED: "자동 실행 오류", CANCELLED: "실행 취소" }[value] || value);
const verificationLabel = (value: string) => ({ TECHNICALLY_MATCHED: "기술 일치", TECHNICAL_MISMATCH: "기술 불일치", PARTIAL: "근거 일부 누락", BLOCKED: "검증 차단" }[value] || value);
const integrityLabel = (value: string) => ({ complete: "해시 검증 완료", partial: "일부 누락", corrupted: "무결성 확인 필요" }[value] || value);
const assertionLabel = (value: string) => ({ MATCH: "일치", MISMATCH: "불일치", MISSING_DATA: "근거 누락", REVIEW_REQUIRED: "담당자 확인" }[value] || value);
const diagnosisLabel = (value: string) => ({ success: "성공 기준 관측", failure: "기대 결과 불일치", undetermined: "담당자 확인 필요" }[value] || value);
const fieldLabel = (value: string) => ({ httpStatus: "서버 응답 상태", route: "결과 화면 경로" }[value] || value);
const displayEvidenceValue = (value: string) => value === "missing_data" ? "확인 자료 없음" : value;
const actionLabel = (value: string) => ({ navigate: "화면 이동", click: "클릭", fill: "값 입력", assert_visible: "표시 확인", assert_text: "문구 확인", wait_for_response: "응답 확인", set_headers: "추적 준비", select: "항목 선택", verify_response: "응답 검증" }[value] || value || "실행 단계");

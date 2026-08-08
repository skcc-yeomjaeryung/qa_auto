"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { formatDateTime } from "../lib/datetime";
import { humanizeObservation, outcomeLabel } from "../lib/scenarios";
import { EvidenceGallery } from "./EvidenceGallery";
import { EvidencePackageViewer } from "./EvidencePackageViewer";
import { CommonDialogTabs } from "./CommonDialogTabs";
import { ProgressGlyph } from "./ProgressBar";
import { apiFetch } from "../lib/apiClient";
import { humanizeMissingEvidence } from "../lib/evidenceLabels";
import { AssistantGuide } from "./AssistantGuide";
import { getDiagnosisCopy } from "../lib/diagnosisCopy";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";

type VerdictCriterion = {
  id?: string;
  check?: string;
  expected?: string;
  result?: "met" | "not_met" | "undetermined" | string;
  observed?: string;
};

type BlockingIssue = { kind?: string; detail?: string; suggestedFix?: string };
type RunDiagnosis = {
  outcome?: "success" | "failure" | "undetermined" | string;
  headline?: string;
  problemSummary?: string;
  causeCategory?: string;
  causeSummary?: string;
  evidence?: string[];
  actions?: Array<{ owner?: string; action?: string; reason?: string }>;
  retestCondition?: string;
  handoffMessage?: string;
  mode?: string;
};

type RunDetail = {
  runId: string;
  scenarioId: string;
  status: string;
  outcomeKind?: string | null;
  outcomeSummary?: string | null;
  observationSummary?: string | null;
  screenshotCount: number;
  snapshotCount: number;
  partialEvidence?: boolean;
  backendTraceStatus?: string | null;
  backendTraceConstraint?: string | null;
  missingData?: string[];
  createdAt?: string | null;
  steps?: Array<{
    stepId: string;
    action?: string;
    status?: string;
    observationSummary?: string | null;
  }>;
  result?: {
    runDiagnosis?: RunDiagnosis;
    verdict?: {
      verdict?: string;
      reason?: string;
      criteria?: VerdictCriterion[];
      criteriaResults?: VerdictCriterion[];
      blockingIssues?: BlockingIssue[];
      coverageNote?: string;
    };
  };
};

export function RunEvidenceDrawer({
  runId,
  open,
  onClose,
  reviewMode = false,
  context,
}: {
  runId: string | null;
  open: boolean;
  onClose: () => void;
  reviewMode?: boolean;
  context?: {
    projectName?: string;
    groupName?: string;
    scenarioName?: string;
    scenarioId?: string;
  } | null;
}) {
  const [run, setRun] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState("summary");

  useEffect(() => {
    if (!open || !runId) return;
    setActiveTab("summary");
    let active = true;
    setLoading(true);
    setError(null);
    apiFetch(`${API}/api/runs/${encodeURIComponent(runId)}`, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("실행 상세를 불러오지 못했습니다");
        const payload = (await response.json()) as RunDetail;
        if (active) setRun(payload);
      })
      .catch((reason: Error) => active && setError(reason.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [open, runId]);

  useEffect(() => {
    if (!open) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [open, onClose]);

  const verdict = run?.result?.verdict;
  const diagnosis = run?.result?.runDiagnosis;
  const diagnosisText = getDiagnosisCopy(diagnosis?.outcome);
  const criteria = verdict?.criteriaResults ?? verdict?.criteria ?? [];
  const blockers = verdict?.blockingIssues ?? [];
  const reviewItems = useMemo(() => {
    if (!run) return [];
    const items: Array<{ tone: "error" | "warning" | "complete"; title: string; detail: string }> = [];
    for (const issue of blockers) {
      items.push({
        tone: "error",
        title: issueLabel(issue.kind),
        detail: [issue.detail, issue.suggestedFix].filter(Boolean).join(" · ") || "원인 확인 필요",
      });
    }
    for (const item of criteria.filter((candidate) => candidate.result !== "met")) {
      items.push({
        tone: item.result === "not_met" ? "error" : "warning",
        title: item.expected || item.check || "기대 결과 확인",
        detail: item.observed || "관측 자료가 부족합니다",
      });
    }
    const externalNetworkOnly = run.backendTraceStatus === "external_network_only";
    for (const missing of (run.missingData ?? []).filter((item) => item !== "backend_instrumentation")) {
      items.push({ tone: "warning", title: "추가 확인 자료", detail: humanizeMissingEvidence(missing) });
    }
    if (externalNetworkOnly) {
      items.push({
        tone: "warning",
        title: "외부 대상 관측 범위",
        detail: "agent-browser 요청·응답과 화면은 수집됐습니다. 외부 공개 서버이므로 내부 Controller·Service 로그는 제공되지 않습니다.",
      });
    } else if (run.partialEvidence) {
      items.push({ tone: "warning", title: "증적 일부 누락", detail: "패키지 무결성과 누락 항목을 확인하세요." });
    }
    if (items.length === 0) {
      items.push({
        tone: "complete",
        title: "자동 관측 기준 확인 완료",
        detail: "자동 관측 결과일 뿐이며 최종 Pass/Fail은 담당자가 증적을 보고 확정합니다.",
      });
    }
    return items;
  }, [blockers, criteria, run]);

  if (!open) return null;

  const kind = run?.outcomeKind || "unknown";
  const isError = kind !== "success" && kind !== "unknown";
  return (
    <div className="run-drawer-layer" data-testid="run-evidence-drawer-layer">
      <button className="run-drawer-scrim" type="button" aria-label="실행 상세 닫기" onClick={onClose} />
      <aside
        className="run-evidence-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="run-evidence-drawer-title"
        data-testid="run-evidence-drawer"
      >
        <header className="run-drawer-head">
          <div>
            <span className="panel-kicker">{reviewMode ? "HITL 증적 검토" : "실행·증적 통합 상세"}</span>
            <h2 id="run-evidence-drawer-title">{context?.groupName || "테스트 시나리오 실행"}</h2>
            <p className="run-drawer-context-name">{context?.scenarioName || "시나리오 정보를 확인하는 중입니다"}</p>
            <p>{context?.scenarioId || run?.scenarioId || "시나리오 확인 중"} · {runId}</p>
          </div>
          <button type="button" className="ghost-btn" onClick={onClose} data-testid="run-drawer-close">
            닫기
          </button>
        </header>

        <div className="run-drawer-body">
          <AssistantGuide compact title="관측 결과를 단계별로 정리했어요" message="AI 요약, 실제 실행 단계, 화면·DOM·Network 증적을 함께 보고 최종 판단해 주세요." />
          {loading && <div className="empty-state compact">실행 증적을 불러오는 중입니다…</div>}
          {error && <div className="connect-banner is-warn" role="alert">{error}</div>}
          {run && (
            <CommonDialogTabs
              value={activeTab}
              onChange={setActiveTab}
              tabs={[
                { id: "summary", label: "AI 관측 요약", count: reviewItems.length },
                { id: "steps", label: "실행 단계", count: run.steps?.length ?? 0 },
                { id: "evidence", label: "증적", count: run.screenshotCount + run.snapshotCount },
              ]}
            />
          )}
          {run && activeTab === "summary" && (
            <>
              <section className={`run-drawer-verdict is-${isError ? "error" : kind === "success" ? "complete" : "warning"}`}>
                <ProgressGlyph status={isError ? "error" : kind === "success" ? "complete" : "warning"} size={22} />
                <div>
                  <strong>{outcomeLabel[kind] ?? kind}</strong>
                  <p>{humanizeObservation(run.outcomeSummary || run.observationSummary) || "관측 요약 없음"}</p>
                  <small>실행 {formatDateTime(run.createdAt)} · 화면 {run.screenshotCount} · 스냅샷 {run.snapshotCount}</small>
                </div>
              </section>

              {diagnosis && (
                <section className={`run-diagnosis-card is-${diagnosis.outcome || "undetermined"}`} data-testid="run-diagnosis">
                  <div className="section-heading-row">
                    <div>
                      <span className="panel-kicker">{diagnosisText.sectionKicker}</span>
                      <h3 className="section-title">{diagnosis.headline || "실행 결과 분석"}</h3>
                    </div>
                    <span className="status-badge status-info">
                      {diagnosis.mode === "llm" ? "AI 보강 · 근거 제한" : "관측 규칙 기반"}
                    </span>
                  </div>
                  <div className="run-troubleshoot-grid">
                    <article>
                      <span>1</span>
                      <div><strong>{diagnosisText.primaryQuestion}</strong><p>{diagnosis.problemSummary || diagnosis.headline || "관측된 결과 요약이 없습니다"}</p></div>
                    </article>
                    <article>
                      <span>2</span>
                      <div><strong>{diagnosisText.causeQuestion}</strong><p>{diagnosis.causeSummary || "관측된 근거 요약이 없습니다"}</p></div>
                    </article>
                    <article>
                      <span>3</span>
                      <div>
                        <strong>{diagnosisText.actionTitle}</strong>
                        {(diagnosis.actions ?? []).length > 0 ? (
                          <ol className="run-action-list">
                            {(diagnosis.actions ?? []).map((item, index) => (
                              <li key={`${item.owner}-${index}`}>
                                <div>
                                  <strong>{item.owner || "개발·QA 담당"}</strong>
                                  <p>{item.action || "조치 내용을 확인하세요"}</p>
                                  {item.reason ? <small>근거: {item.reason}</small> : null}
                                </div>
                              </li>
                            ))}
                          </ol>
                        ) : <p>{diagnosisText.emptyAction}</p>}
                      </div>
                    </article>
                  </div>
                  {diagnosis.retestCondition && (
                    <p className="run-retest-condition"><strong>{diagnosisText.retestLabel}</strong>{diagnosis.retestCondition}</p>
                  )}
                  {diagnosis.handoffMessage && (
                    <blockquote className="run-handoff-message">
                      <strong>{diagnosisText.handoffLabel}</strong>
                      <p>{diagnosis.handoffMessage}</p>
                    </blockquote>
                  )}
                </section>
              )}

              <section className="run-review-targets" data-testid="run-review-targets">
                <div className="section-heading-row">
                  <div>
                    <h3 className="section-title">{diagnosisText.reviewTitle}</h3>
                    <p className="muted">{diagnosisText.reviewHint}</p>
                  </div>
                  <span className="status-badge status-info">{reviewItems.length}건</span>
                </div>
                <ul>
                  {reviewItems.map((item, index) => (
                    <li className={`is-${item.tone}`} key={`${item.title}-${index}`}>
                      <ProgressGlyph status={item.tone} size={16} />
                      <div><strong>{item.title}</strong><p>{item.detail}</p></div>
                    </li>
                  ))}
                </ul>
              </section>
            </>
          )}
          {run && activeTab === "steps" && (
              <section className="run-drawer-steps">
                <h3 className="section-title">실행 단계</h3>
                <ol>
                  {(run.steps ?? []).map((step, index) => (
                    <li key={`${step.stepId}-${index}`}>
                      <span className={`run-step-dot is-${step.status || "queued"}`} />
                      <div>
                        <strong>{step.stepId || index + 1} · {actionLabel(step.action)}</strong>
                        <p>{step.observationSummary || step.status || "관측 대기"}</p>
                      </div>
                    </li>
                  ))}
                </ol>
              </section>
          )}
          {run && activeTab === "evidence" && (
            <div className="run-drawer-evidence-tab">
              <EvidencePackageViewer runId={run.runId} />
              <EvidenceGallery runId={run.runId} scenarioId={run.scenarioId} />
            </div>
          )}
        </div>

        <footer className="run-drawer-foot">
          {run?.scenarioId && <Link className="ghost-btn" href={`/scenarios/${encodeURIComponent(run.scenarioId)}`}>시나리오 원문</Link>}
          {run && <Link className="primary-btn" href={`/runs/${encodeURIComponent(run.runId)}`}>전체 화면으로 보기</Link>}
        </footer>
      </aside>
    </div>
  );
}

function issueLabel(kind?: string) {
  const labels: Record<string, string> = {
    not_found: "화면 경로 오류",
    server_error: "서버 오류",
    method_not_allowed: "요청 방식 오류",
    session_missing: "로그인 세션 누락",
    no_state_change: "화면 상태 변화 없음",
    destructive_policy_blocked: "실행 정책으로 제출 차단",
    input_precondition_invalid: "테스트 데이터 선행조건 부족",
  };
  return labels[kind || ""] || "차단 원인 확인";
}

function actionLabel(action?: string) {
  const labels: Record<string, string> = {
    navigate: "화면 이동",
    click: "버튼 클릭",
    fill: "값 입력",
    assert_visible: "화면 표시 확인",
    assert_absent: "화면 제거 확인",
    wait_for_response: "서버 응답 확인",
    set_headers: "추적 준비",
    select: "항목 선택",
    assert_text: "결과 문구 확인",
    capture_value: "실행 전 값 기록",
    capture_collection: "실행 전 목록 기록",
    verify_numeric_delta: "전후 값 변화 확인",
    verify_collection_change: "결과 행 추가 확인",
  };
  return labels[action || ""] || action || "실행 단계";
}

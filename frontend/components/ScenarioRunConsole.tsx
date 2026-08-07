"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { EvidenceGallery } from "./EvidenceGallery";
import { Icon } from "./Icon";
import { BusyIndicator, ProgressBarType4, ProgressGlyph, type ProgressStatus } from "./ProgressBar";
import { apiFetch } from "../lib/apiClient";
import { lsGet, lsSet } from "../lib/localStore";
import { formatDateTime } from "../lib/datetime";
import { ButtonLink } from "./ui/ButtonLink";
import {
  cancelRun,
  fetchRun,
  fetchRunPreview,
  isRunActive,
  retestRun,
  startInteractiveRun,
  StaleVersionError,
  type RunPreview,
  type RunPreviewField,
  type RunStep,
  type RunSummary,
} from "../lib/interactiveRun";

const POLL_MS = 1200;

const STAGE_LABEL: Record<string, string> = {
  a_input: "A 화면 입력",
  request: "Backend 요청",
  b_ui: "B 화면 관측",
};

const CONFIDENCE_LABEL: Record<string, string> = {
  confirmed: "코드 근거",
  inferred: "자동 생성값",
  review_required: "확인 필요",
  unresolved: "값 없음",
};

function stepStatusToProgress(status: string): ProgressStatus {
  if (status === "ok") return "complete";
  if (status === "error") return "error";
  if (status === "running") return "progressing";
  return "empty";
}

function runStatusToProgress(status: string): ProgressStatus {
  if (status === "AUTO_FAILED") return "error";
  if (status === "CANCELLED") return "warning";
  if (status === "WAITING_FOR_REVIEW") return "complete";
  if (isRunActive(status)) return "progressing";
  return "empty";
}

/** 실행 상태를 담당자가 읽는 문장으로 — 「기술 실행 완료」 같은 내부 용어를 화면에 쓰지 않는다 */
const RUN_STATE_KO: Record<string, string> = {
  WAITING_FOR_REVIEW: "실행은 끝났어요 · 이제 결과를 확인해 주세요",
  AUTO_FAILED: "진행 중 멈춘 지점이 있어요",
  CANCELLED: "실행을 중단했습니다",
  RUNNING: "실행 중",
  PREPARING: "실행 준비 중",
  QUEUED: "실행 대기 중",
};

/** 단계 동작 이름을 한글로 — 없으면 원문을 그대로 둔다 */
const STEP_ACTION_KO: Record<string, string> = {
  navigate: "화면 열기",
  open: "화면 열기",
  fill: "값 입력",
  type: "값 입력",
  select: "항목 선택",
  check: "선택 표시",
  click: "버튼 클릭",
  press: "키 입력",
  submit: "입력 제출",
  dom_bind: "화면 입력 자동 채움",
  wait_for_response: "서버 응답 대기",
  verify_binding: "결과 값 대조",
  assert_visible: "화면 요소 확인",
  assert_text: "화면 문구 확인",
  capture_value: "실행 전 값 기록",
  capture_collection: "실행 전 목록 기록",
  verify_numeric_delta: "전후 값 변화 확인",
  verify_collection_change: "결과 행 추가 확인",
  screenshot: "화면 캡쳐",
};

function stepActionKo(action: string | null | undefined): string {
  const key = String(action || "").toLowerCase();
  return STEP_ACTION_KO[key] || action || "—";
}

export function ScenarioRunConsole({
  scenarioId,
  detailMode = "full",
}: {
  scenarioId: string;
  /** Scenario detail keeps setup/launch only; execution facts live in Run History. */
  detailMode?: "full" | "preflight";
}) {
  const [preview, setPreview] = useState<RunPreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [overrides, setOverrides] = useState<Record<string, unknown>>({});
  const [reusePrevious, setReusePrevious] = useState(false);
  const [run, setRun] = useState<RunSummary | null>(null);
  const [busy, setBusy] = useState<null | "run" | "cancel" | "save">(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [destructiveConfirmOpen, setDestructiveConfirmOpen] = useState(false);
  const tempCaseKey = `interactive.tempCase.${scenarioId}`;
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadPreview = useCallback(
    async (opts: { reuseFromRunId?: string | null } = {}) => {
      setLoading(true);
      setError(null);
      try {
        const next = await fetchRunPreview(scenarioId, {
          reuseFromRunId: opts.reuseFromRunId ?? null,
        });
        setPreview(next);
        setStale(false);
      } catch (e) {
        setError(e instanceof Error ? e.message : "실행 요약을 불러오지 못했습니다");
      } finally {
        setLoading(false);
      }
    },
    [scenarioId],
  );

  useEffect(() => {
    void loadPreview();
    const saved = lsGet<Record<string, unknown>>(tempCaseKey, {});
    if (saved && Object.keys(saved).length > 0) setOverrides(saved);
  }, [loadPreview, tempCaseKey]);

  // 이미 실행한 시나리오면 직전 실행 결과·증적을 먼저 보여준다 (다시 실행 강요 금지).
  useEffect(() => {
    const previousId = preview?.previousRun?.runId;
    if (!previousId || run) return;
    let alive = true;
    void (async () => {
      try {
        const last = await fetchRun(previousId);
        if (alive) setRun(last);
      } catch {
        /* 직전 실행을 못 읽어도 실행 준비 화면은 그대로 쓴다 */
      }
    })();
    return () => {
      alive = false;
    };
  }, [preview?.previousRun?.runId, run]);

  // 실행 중에는 step 진행을 폴링해 Type 4 진행과 현재 Evidence를 갱신한다.
  useEffect(() => {
    if (!run || !isRunActive(run.status)) return;
    let cancelled = false;
    async function tick() {
      try {
        const next = await fetchRun(run!.runId);
        if (!cancelled) setRun(next);
      } catch {
        /* 폴링 실패는 다음 주기에 재시도 */
      }
      if (!cancelled) pollRef.current = setTimeout(() => void tick(), POLL_MS);
    }
    pollRef.current = setTimeout(() => void tick(), POLL_MS);
    return () => {
      cancelled = true;
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [run]);

  const effectiveInputs = useMemo(() => {
    const base: Record<string, unknown> = {};
    for (const field of preview?.fields || []) base[field.field] = field.value;
    return { ...base, ...overrides };
  }, [preview, overrides]);

  // 사람이 손으로 채워야 하는 것만 「확인 필요」로 남긴다.
  // 자동 생성값(inferred)은 그대로 실행할 수 있으므로 채워진 입력 쪽에 둔다.
  const reviewFields = (preview?.fields || []).filter(
    (f) => f.confidence === "review_required" || f.confidence === "unresolved"
  );
  const confirmedFields = (preview?.fields || []).filter(
    (f) => f.confidence === "confirmed" || f.confidence === "inferred"
  );
  const inferredCount = (preview?.fields || []).filter((f) => f.confidence === "inferred").length;
  // 화면 구성 확인처럼 값을 채우지 않는 시나리오 — 확인 숙제를 만들지 않는다.
  const noInputNeeded = (preview?.fields.length || 0) === 0;
  // 같은 필드가 fields·missingData 양쪽에 잡혀 「확인 필요」가 두 배로 세지지 않게 한다.
  const reviewFieldNames = new Set(reviewFields.map((f) => f.field));
  const otherMissing = (preview?.missingData || []).filter((entry) => {
    if (!entry.startsWith("input:")) return true;
    const name = entry.slice("input:".length).split("—")[0].trim();
    return !reviewFieldNames.has(name);
  });
  const uncertainCount =
    reviewFields.length + (preview?.unresolved.length || 0) + otherMissing.length;

  function setOverride(field: string, value: unknown) {
    setOverrides((prev) => ({ ...prev, [field]: value }));
  }

  function clearOverrides() {
    setOverrides({});
    lsSet(tempCaseKey, {});
    setNotice("추천값으로 되돌렸습니다.");
  }

  async function launch(destructiveApproved = false) {
    if (!preview) return;
    if (preview.destructive && !destructiveApproved) {
      setDestructiveConfirmOpen(true);
      return;
    }
    setDestructiveConfirmOpen(false);
    setBusy("run");
    setError(null);
    setNotice(null);
    try {
      const started = await startInteractiveRun(scenarioId, {
        environmentId: preview.environmentId,
        inputProfileId: preview.inputProfileId,
        inputProfileVersion: preview.inputProfileVersion,
        scenarioVersion: preview.scenarioVersion,
        // 화면에서 확인한 추천값과 사용자 수정값을 함께 고정한다.
        // overrides만 보내면 추천값이 실행 이력·증적 입력 묶음에서 빠질 수 있다.
        inputs: effectiveInputs,
        overrides,
        reuseFromRunId: reusePrevious ? preview.previousRun?.runId ?? null : null,
        allowDestructive: preview.destructive && destructiveApproved,
      });
      setRun(started);
    } catch (e) {
      if (e instanceof StaleVersionError) {
        setStale(true);
        setError(e.message);
      } else {
        setError(e instanceof Error ? e.message : "실행을 시작하지 못했습니다");
      }
    } finally {
      setBusy(null);
    }
  }

  async function stop() {
    if (!run) return;
    setBusy("cancel");
    try {
      setRun(await cancelRun(run.runId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "취소하지 못했습니다");
    } finally {
      setBusy(null);
    }
  }

  async function again(reuse: boolean) {
    if (!run) return;
    setBusy("run");
    setError(null);
    try {
      const next = await retestRun(run.runId, {
        reuseFromRunId: reuse ? run.runId : null,
        overrides: reuse ? {} : overrides,
      });
      setRun(next);
    } catch (e) {
      if (e instanceof StaleVersionError) {
        setStale(true);
        setError(e.message);
      } else {
        setError(e instanceof Error ? e.message : "재실행하지 못했습니다");
      }
    } finally {
      setBusy(null);
    }
  }

  function saveTempCase() {
    lsSet(tempCaseKey, overrides);
    setNotice("임시 Case로 저장했습니다 (이 브라우저에만 보관).");
  }

  async function saveAsProfileVersion() {
    if (!preview) return;
    setBusy("save");
    setError(null);
    try {
      const res = await apiFetch(`/api/scenarios/${scenarioId}/input-profiles`, {
        method: "POST",
        body: JSON.stringify({
          name: `${preview.scenarioName || scenarioId} 건별 수정본`,
          overrides,
        }),
      });
      if (!res.ok) throw new Error("Input Profile 저장 실패");
      const created = (await res.json()) as { profileId: string };
      const approved = await apiFetch(`/api/input-profiles/${created.profileId}/approve`, {
        method: "POST",
        body: JSON.stringify({ approvedBy: "console-interactive" }),
      });
      if (!approved.ok) throw new Error("Input Profile 승인 실패");
      await loadPreview();
      setNotice("새 Input Profile 버전으로 저장했습니다. 승인 확정은 HITL에서 진행합니다.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Input Profile 저장 실패");
    } finally {
      setBusy(null);
    }
  }

  const failedStep = useMemo(() => {
    if (!run?.failedStepId) return null;
    return run.steps.find((s) => s.stepId === run.failedStepId) || null;
  }, [run]);

  const runActive = isRunActive(run?.status);
  const percent = runActive
    ? run?.progressPercent ?? 0
    : run
      ? 100
      : 0;
  const currentStepLabel = (() => {
    const current = run?.steps.find((s) => s.stepId === run?.currentStepId);
    if (current) return stepActionKo(current.action);
    if (runActive) return "실행 준비";
    return RUN_STATE_KO[String(run?.status)] || "대기";
  })();

  if (loading && !preview) {
    return (
      <section className="run-console" data-testid="scenario-run-console">
        <p className="muted">실행 요약을 불러오는 중입니다…</p>
      </section>
    );
  }

  return (
    <section id="scenario-run-console" className="run-console anim-fade-in" data-testid="scenario-run-console">
      {destructiveConfirmOpen && preview && (
        <div className="modal-backdrop" role="presentation" data-testid="destructive-run-dialog">
          <section
            className="generation-modal destructive-run-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="destructive-run-title"
          >
            <header>
              <div>
                <p className="panel-kicker">DATA CHANGE CONFIRMATION</p>
                <h3 id="destructive-run-title">현재 입력값으로 이 1회 테스트를 실행할까요?</h3>
              </div>
              <button
                type="button"
                className="modal-close"
                onClick={() => setDestructiveConfirmOpen(false)}
                aria-label="실행 확인 닫기"
              >
                ×
              </button>
            </header>
            <div className="destructive-run-body">
              <div className="connect-banner is-warn">
                이 시나리오는 등록된 파일럿 환경의 데이터를 변경할 수 있습니다. 승인은 이번 실행에만 적용됩니다.
              </div>
              <dl>
                <div>
                  <dt>실행 대상</dt>
                  <dd>{preview.environmentName || preview.baseUrl || "등록된 실행환경"}</dd>
                </div>
                {Object.entries(effectiveInputs).map(([field, value]) => (
                  <div key={field}>
                    <dt>{field}</dt>
                    <dd>{String(value ?? "—")}</dd>
                  </div>
                ))}
              </dl>
              <strong>데이터 변경 근거</strong>
              <ul>
                {preview.destructiveReasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </div>
            <footer>
              <p>계정과 입력값을 다시 확인하세요. 실행 결과와 변경 전후 증적은 실행 이력에 남습니다.</p>
              <div>
                <button type="button" className="ghost-btn" onClick={() => setDestructiveConfirmOpen(false)}>
                  취소
                </button>
                <button
                  type="button"
                  className="primary-btn"
                  onClick={() => void launch(true)}
                  data-testid="confirm-destructive-run"
                >
                  이 값으로 1회 실행
                </button>
              </div>
            </footer>
          </section>
        </div>
      )}
      {error && (
        <div className="connect-banner is-warn" role="alert" data-testid="run-console-error">
          <span>{error}</span>
          {stale && (
            <button type="button" className="ghost-btn" onClick={() => void loadPreview()}>
              최신 버전 다시 불러오기
            </button>
          )}
        </div>
      )}
      {notice && (
        <div className="connect-banner" role="status" data-testid="run-console-notice">
          {notice}
        </div>
      )}

      {preview && (
        <>
          <FlowStrip preview={preview} screenOnly={noInputNeeded} />

          <div className="run-console-grid">
            <RequiredInputs
              fields={confirmedFields}
              noInputNeeded={noInputNeeded}
              overrides={overrides}
              editing={editing}
              onEdit={setOverride}
            />
            <RecommendedSetup preview={preview} inputs={effectiveInputs} />
          </div>

          <UncertainItems
            fields={reviewFields}
            unresolved={preview.unresolved}
            missingData={preview.missingData}
            overrides={overrides}
            onEdit={setOverride}
          />

          <div className="run-console-launch">
            <div className="run-console-launch-main">
              <button
                type="button"
                className="primary-btn"
                onClick={() => void launch()}
                disabled={busy !== null || runActive}
                aria-busy={busy === "run" || undefined}
                data-testid="run-with-recommended"
              >
                {busy === "run" ? <BusyIndicator size={14} /> : <Icon name="plus" size={14} />}
                {busy === "run"
                  ? "실행 시작 중…"
                  : noInputNeeded
                    ? "테스트 실행"
                    : confirmedFields.length > 0
                      ? "추천값으로 실행"
                      : "입력한 값으로 실행"}
              </button>
              <button
                type="button"
                className="ghost-btn"
                aria-expanded={editing}
                aria-controls="run-console-inputs"
                disabled={noInputNeeded}
                title={noInputNeeded ? "이 테스트는 입력값을 쓰지 않습니다" : undefined}
                onClick={() => setEditing((v) => !v)}
                data-testid="toggle-input-edit"
              >
                {editing ? "값 수정 닫기" : "값 수정"}
              </button>
              {Object.keys(overrides).length > 0 && (
                <>
                  <button type="button" className="ghost-btn" onClick={saveTempCase}>
                    임시 Case 저장
                  </button>
                  <button
                    type="button"
                    className="ghost-btn"
                    disabled={busy !== null}
                    onClick={() => void saveAsProfileVersion()}
                  >
                    {busy === "save" ? "저장 중…" : "새 Input Profile 버전"}
                  </button>
                  <button type="button" className="ghost-btn" onClick={clearOverrides}>
                    추천값 복원
                  </button>
                </>
              )}
            </div>
            <div className="run-console-launch-meta">
              {inferredCount > 0 && (
                <span className="run-inferred-chip" data-testid="inferred-chip">
                  <ProgressGlyph status="progressing" size={12} />
                  자동 생성값 {inferredCount}건 · 수정 가능
                </span>
              )}
              {uncertainCount > 0 && (
                <button
                  type="button"
                  className="run-uncertain-jump"
                  data-testid="uncertain-jump"
                  onClick={() =>
                    document
                      .querySelector('[data-testid="uncertain-items"]')
                      ?.scrollIntoView({ behavior: "smooth", block: "center" })
                  }
                >
                  <ProgressGlyph status="warning" size={12} />
                  직접 확인 필요 {uncertainCount}건
                </button>
              )}
              {preview.previousRun && (
                <label className="run-reuse">
                  <input
                    type="checkbox"
                    checked={reusePrevious}
                    onChange={(e) => {
                      setReusePrevious(e.target.checked);
                      void loadPreview({
                        reuseFromRunId: e.target.checked ? preview.previousRun?.runId : null,
                      });
                    }}
                    data-testid="reuse-previous-inputs"
                  />
                  직전 실행과 같은 값으로 실행
                </label>
              )}
            </div>
          </div>

          {editing && (
            <InputEditor
              id="run-console-inputs"
              fields={preview.fields}
              overrides={overrides}
              onEdit={setOverride}
            />
          )}
        </>
      )}

      {run && detailMode === "preflight" && (
        <section className="run-console-handoff" data-testid="run-history-handoff">
          <div>
            <span className="panel-kicker">다음 확인</span>
            <strong>{runActive ? "테스트가 시작됐어요" : RUN_STATE_KO[run.status] || run.status}</strong>
            <p>
              단계별 기록과 화면 캡처를 한곳에 모아 두었어요. 결과를 열어 확인을 이어가세요.
            </p>
          </div>
          <ButtonLink href={`/runs/${run.runId}`}>실행 결과 열기</ButtonLink>
        </section>
      )}

      {run && detailMode === "full" && (
        <>
          <section className="run-console-block" aria-labelledby="run-timeline-heading">
            <div className="section-heading-row">
              <h3 id="run-timeline-heading">실행 진행</h3>
              <div className="inline-actions">
                {runActive && (
                  <button
                    type="button"
                    className="ghost-btn"
                    onClick={() => void stop()}
                    disabled={busy !== null}
                    data-testid="cancel-run"
                  >
                    {busy === "cancel" ? "취소 중…" : "실행 취소"}
                  </button>
                )}
                <Link className="ghost-btn" href={`/runs/${run.runId}`}>
                  실행 상세
                </Link>
              </div>
            </div>
            <ProgressBarType4
              title={runActive ? "테스트 실행 중" : "실행한 단계"}
              stepLabel={currentStepLabel}
              percent={percent}
              status={runStatusToProgress(run.status)}
              testId="run-progress-type4"
            />
            <ol className="run-step-list" data-testid="run-step-list" aria-live="polite">
              {run.steps.map((step, index) => (
                <li
                  key={step.stepId}
                  className={`run-step is-${stepStatusToProgress(step.status)}`}
                  aria-current={step.stepId === run.currentStepId ? "step" : undefined}
                >
                  <span className="run-step-glyph">
                    <ProgressGlyph status={stepStatusToProgress(step.status)} size={14} />
                  </span>
                  <span className="run-step-id">{index + 1}단계</span>
                  <span className="run-step-action">{stepActionKo(step.action)}</span>
                  <span className="run-step-obs">{step.observationSummary || ""}</span>
                </li>
              ))}
            </ol>
          </section>

          {failedStep && <FailurePanel step={failedStep} run={run} onRetest={again} busy={busy !== null} />}

          {!runActive && (
            <section className="run-console-block" aria-labelledby="run-result-heading">
              <h3 id="run-result-heading">이번 실행에서 관측한 것</h3>
              <div className="run-result-split">
                <article className="run-result-card">
                  <p className="panel-kicker">실행 관측</p>
                  <strong data-testid="run-technical-status">
                    {RUN_STATE_KO[run.status] || run.status}
                  </strong>
                  <p className="muted">
                    {run.observationSummary || run.outcomeSummary || "관측 요약이 없습니다"}
                  </p>
                  {run.result?.runNarrative ? (
                    <p className="run-narrative-inline" data-testid="run-narrative-inline">
                      {run.result.runNarrative}
                    </p>
                  ) : null}
                  <dl className="run-result-facts">
                    <div>
                      <dt>실행 시각</dt>
                      <dd>{formatDateTime(run.createdAt)}</dd>
                    </div>
                    <div>
                      <dt>남은 화면 캡쳐</dt>
                      <dd>{run.screenshotCount}장</dd>
                    </div>
                    <div>
                      <dt>확인이 필요한 항목</dt>
                      <dd>{run.missingData.length}건</dd>
                    </div>
                  </dl>
                </article>
                <article className="run-result-card is-hitl">
                  <p className="panel-kicker">최종 판정</p>
                  <strong data-testid="run-hitl-status">담당자 확인 대기</strong>
                  <p className="muted">
                    실행을 마친 것과 합격은 다릅니다. 화면이 열렸다는 사실만으로 성공이 되지 않으며,
                    합격·불합격과 배포는 개발PL·QA·고객이 확정합니다.
                  </p>
                  <div className="inline-actions">
                    <Link
                      className="primary-btn"
                      href={`/hitl?runId=${encodeURIComponent(run.runId)}`}
                      data-testid="go-hitl"
                    >
                      승인 검토로 이동
                    </Link>
                    <button
                      type="button"
                      className="ghost-btn"
                      disabled={busy !== null}
                      onClick={() => void again(true)}
                      data-testid="retest-same-inputs"
                    >
                      같은 값으로 다시 실행
                    </button>
                    <button
                      type="button"
                      className="ghost-btn"
                      disabled={busy !== null}
                      onClick={() => void again(false)}
                    >
                      현재 화면 값으로 다시 실행
                    </button>
                  </div>
                </article>
              </div>
              <details className="run-technical-more" data-testid="run-technical-more">
                <summary>기술 상세 (실행 ID · 버전 · 근거 없는 항목)</summary>
                <dl className="run-result-facts">
                  <div>
                    <dt>실행 ID</dt>
                    <dd>
                      <Link href={`/runs/${run.runId}`}>{run.runId}</Link>
                    </dd>
                  </div>
                  <div>
                    <dt>실행 상태 코드</dt>
                    <dd>{run.status}</dd>
                  </div>
                  <div>
                    <dt>DOM snapshot</dt>
                    <dd>{run.snapshotCount}</dd>
                  </div>
                  <div>
                    <dt>Backend 추적</dt>
                    <dd>{run.backendTraceStatus || "missing_data"}</dd>
                  </div>
                  <div>
                    <dt>시나리오 버전</dt>
                    <dd>
                      v{run.scenarioVersion || preview?.scenarioVersion || "—"}
                      {preview && Object.keys(preview.commitRefs).length > 0
                        ? ` · commit ${Object.values(preview.commitRefs)[0]?.slice(0, 8)}`
                        : ""}
                    </dd>
                  </div>
                  <div>
                    <dt>INPUT 출처</dt>
                    <dd>
                      {preview?.inputProfileId
                        ? `${preview.inputProfileId} (v${preview.inputProfileVersion})`
                        : preview?.recommendationId || "missing_data"}
                    </dd>
                  </div>
                </dl>
                {run.missingData.length > 0 && (
                  <p className="missing-data-tag">missing_data: {run.missingData.join(" · ")}</p>
                )}
              </details>
            </section>
          )}

          <section className="run-console-block" aria-labelledby="run-evidence-heading">
            <h3 id="run-evidence-heading">남은 증적 (화면 캡쳐 · 화면 구성 기록)</h3>
            <EvidenceGallery runId={run.runId} reloadToken={`${run.status}:${run.steps.length}`} />
          </section>
        </>
      )}
    </section>
  );
}

function FlowStrip({ preview, screenOnly }: { preview: RunPreview; screenOnly: boolean }) {
  const bScreen = preview.bScreen.screen;
  const hasBScreen = Boolean(bScreen) && bScreen !== "missing_data" && bScreen !== "n/a";
  // 서버 호출 목록은 담당자에게 건수로 보여주고, 실제 method/path는 tooltip에만 둔다
  const apiTip = preview.expectedApis
    .map((api) => `${api.method} ${api.path}`)
    .join("\n");
  return (
    <div className="run-flow-strip" data-testid="run-flow-strip">
      <div className="run-flow-node">
        <span className="panel-kicker">여는 화면</span>
        <strong title={preview.aScreen.route || undefined}>{preview.aScreen.screen}</strong>
      </div>
      <span className="run-flow-arrow" aria-hidden>
        →
      </span>
      <div className="run-flow-node">
        <span className="panel-kicker">서버 호출</span>
        {preview.expectedApis.length === 0 ? (
          screenOnly ? (
            <span className="muted">화면만 확인 · 서버 호출 없음</span>
          ) : (
            <span className="muted">분석 근거 없음</span>
          )
        ) : (
          <strong title={apiTip}>{preview.expectedApis.length}건 호출</strong>
        )}
      </div>
      <span className="run-flow-arrow" aria-hidden>
        →
      </span>
      <div className="run-flow-node">
        <span className="panel-kicker">다음 화면</span>
        {hasBScreen ? (
          <strong title={preview.bScreen.routePattern || preview.bScreen.route || undefined}>
            {bScreen}
          </strong>
        ) : (
          <span className="muted">이동 없음 · 같은 화면에서 확인</span>
        )}
      </div>
    </div>
  );
}

function RequiredInputs({
  fields,
  noInputNeeded,
  overrides,
  editing,
  onEdit,
}: {
  fields: RunPreviewField[];
  noInputNeeded: boolean;
  overrides: Record<string, unknown>;
  editing: boolean;
  onEdit: (field: string, value: unknown) => void;
}) {
  return (
    <article className="run-console-block" aria-labelledby="run-inputs-heading">
      <h3 id="run-inputs-heading">{noInputNeeded ? "입력값" : "자동으로 채운 테스트 입력"}</h3>
      {noInputNeeded ? (
        <p className="muted" data-testid="no-input-needed">
          이 테스트는 값을 입력하지 않습니다. 화면을 열어 필요한 요소가 보이는지만 확인합니다.
        </p>
      ) : fields.length === 0 ? (
        <p className="muted">자동으로 채운 입력이 없습니다. 아래 확인 항목을 먼저 채워주세요.</p>
      ) : (
        <>
        {fields.some((f) => f.confidence === "inferred") && (
          <p className="muted" data-testid="inferred-note">
            「자동 생성값」은 분석된 필드 이름·타입에서 만든 테스트값입니다. 그대로 실행해도 되고,
            「값 수정」으로 바꾸면 바꾼 값으로 실행합니다.
          </p>
        )}
        <ul className="run-input-summary" data-testid="confirmed-inputs">
          {fields.map((field, index) => {
            const value = field.field in overrides ? overrides[field.field] : field.value;
            const changed = field.field in overrides;
            return (
              <li key={`${field.field}-${index}`}>
                <span className="run-input-name">
                  {field.field}
                  {field.required && <em aria-label="필수">*</em>}
                </span>
                {editing && field.editable ? (
                  <input
                    className="run-input-inline"
                    value={String(value ?? "")}
                    aria-label={`${field.field} 값`}
                    onChange={(e) => onEdit(field.field, e.target.value)}
                  />
                ) : (
                  <code>{field.masked ? field.displayValue || "***" : String(value ?? "—")}</code>
                )}
                {changed && <span className="run-tag is-changed">수정</span>}
                {field.confidence === "inferred" ? (
                  <span
                    className="run-tag is-inferred"
                    title={field.rationale || "필드 정의에서 자동 생성한 테스트값입니다"}
                  >
                    자동 생성값
                  </span>
                ) : (
                  field.category && <span className="run-tag">{field.category}</span>
                )}
              </li>
            );
          })}
        </ul>
        </>
      )}
    </article>
  );
}

function RecommendedSetup({
  preview,
  inputs,
}: {
  preview: RunPreview;
  inputs: Record<string, unknown>;
}) {
  return (
    <article className="run-console-block" aria-labelledby="run-setup-heading">
      <h3 id="run-setup-heading">어디에서 실행하나요</h3>
      <dl className="run-setup-facts">
        <div>
          <dt>실행 대상</dt>
          <dd>
            {preview.environmentName ||
              (preview.baseUrl ? "파일럿 샌드박스 (등록된 환경 없음 · 기본값)" : "등록된 환경 없음")}
            {preview.baseUrl && <code className="run-target-url">{preview.baseUrl}</code>}
          </dd>
        </div>
        <div>
          <dt>여는 화면</dt>
          <dd>{preview.aScreen.screen}</dd>
        </div>
        <div>
          <dt>실행 입력값</dt>
          <dd>
            {Object.keys(inputs).length === 0 ? (
              <span className="muted">입력값 없이 화면을 열어 확인합니다</span>
            ) : (
              <span>{Object.keys(inputs).length}개 항목을 채워 실행합니다</span>
            )}
          </dd>
        </div>
      </dl>
      <div className={`run-destructive ${preview.destructive ? "is-on" : ""}`} data-testid="destructive-flag">
        <ProgressGlyph status={preview.destructive ? "warning" : "complete"} size={14} />
        {preview.destructive ? (
          <span>
            데이터를 바꿀 수 있는 동작이 있습니다 — {preview.destructiveReasons.join(" · ")} · 파일럿
            환경에서만 실행하세요.
          </span>
        ) : (
          <span>조회 성격 동작으로 관측됩니다 (데이터를 바꾸는 신호 없음).</span>
        )}
      </div>
    </article>
  );
}

function UncertainItems({
  fields,
  unresolved,
  missingData,
  overrides,
  onEdit,
}: {
  fields: RunPreviewField[];
  unresolved: Array<Record<string, unknown>>;
  missingData: string[];
  overrides: Record<string, unknown>;
  onEdit: (field: string, value: unknown) => void;
}) {
  // 필드로 이미 보여주는 input:* 항목은 목록에서 다시 늘어놓지 않는다.
  const fieldNames = new Set(fields.map((f) => f.field));
  const otherMissing = missingData.filter((entry) => {
    if (!entry.startsWith("input:")) return true;
    return !fieldNames.has(entry.slice("input:".length).split("—")[0].trim());
  });
  if (fields.length === 0 && unresolved.length === 0 && otherMissing.length === 0) {
    return (
      <div className="run-uncertain is-clear" data-testid="uncertain-items">
        <ProgressGlyph status="complete" size={14} />
        <span>확인이 필요한 항목이 없습니다. 추천값으로 바로 실행할 수 있습니다.</span>
      </div>
    );
  }
  return (
    <section className="run-console-block is-warn" data-testid="uncertain-items" aria-labelledby="run-uncertain-heading">
      <h3 id="run-uncertain-heading">
        {fields.length > 0 ? "직접 확인이 필요한 입력" : "실행 전에 알아둘 점"}
      </h3>
      <p className="muted">
        {fields.length > 0
          ? "분석한 코드에 이 값의 근거가 없어 자동으로 채우지 않았습니다. 테스트에 쓸 값을 직접 넣으면 그 값으로 실행합니다."
          : "코드 분석에서 근거를 찾지 못해 비워 둔 항목입니다. 실행은 가능하며, 아래 항목은 관측으로 확인해야 합니다."}
      </p>
      {fields.length > 0 && (
        <ul className="run-uncertain-list">
          {fields.map((field, index) => {
            const inputId = `uncertain-${field.field}-${index}`;
            const hintId = `${inputId}-hint`;
            const value = field.field in overrides ? overrides[field.field] : field.value;
            return (
              <li key={inputId}>
                <label htmlFor={inputId}>
                  {field.field}
                  <span className="run-tag is-warn">{CONFIDENCE_LABEL[field.confidence]}</span>
                </label>
                <input
                  id={inputId}
                  className="run-input-inline"
                  value={String(value ?? "")}
                  aria-describedby={hintId}
                  aria-invalid={field.confidence === "unresolved"}
                  onChange={(e) => onEdit(field.field, e.target.value)}
                />
                <p className="muted" id={hintId}>
                  {field.rationale || "코드 분석에서 이 값을 찾지 못했습니다. 쓸 값을 넣어주세요."}
                  {field.source ? ` · 근거 ${field.source}` : ""}
                </p>
              </li>
            );
          })}
        </ul>
      )}
      {unresolved.length > 0 && (
        <p className="missing-data-tag">
          시나리오 unresolved {unresolved.length}건 — 코드 근거 없이 확정하지 않습니다.
        </p>
      )}
      {otherMissing.length > 0 && (
        <p className="missing-data-tag">
          근거가 없어 비워 둔 항목: {otherMissing.join(" · ")}
        </p>
      )}
    </section>
  );
}

function InputEditor({
  id,
  fields,
  overrides,
  onEdit,
}: {
  id: string;
  fields: RunPreviewField[];
  overrides: Record<string, unknown>;
  onEdit: (field: string, value: unknown) => void;
}) {
  return (
    <fieldset className="run-input-editor anim-slide-down" id={id}>
      <legend>값 · 카테고리 · 예상 분기 수정</legend>
      {fields.map((field, index) => {
        const valueId = `edit-value-${field.field}-${index}`;
        const catId = `edit-cat-${field.field}-${index}`;
        const pathId = `edit-path-${field.field}-${index}`;
        const value = field.field in overrides ? overrides[field.field] : field.value;
        return (
          <div className="run-input-editor-row" key={valueId}>
            <label htmlFor={valueId}>{field.field} 값</label>
            <input
              id={valueId}
              value={String(value ?? "")}
              onChange={(e) => onEdit(field.field, e.target.value)}
            />
            <label htmlFor={catId}>category</label>
            <select
              id={catId}
              defaultValue={field.category || ""}
              onChange={(e) => {
                const picked = field.candidates.find((c) => c.category === e.target.value);
                if (picked && picked.value !== undefined) onEdit(field.field, picked.value);
              }}
            >
              <option value="">{field.category || "미지정"}</option>
              {field.candidates.map((c, idx) => (
                <option key={`${field.field}-${idx}`} value={String(c.category || "")}>
                  {c.category || "미지정"} · {String(c.displayValue ?? c.value ?? "")}
                </option>
              ))}
            </select>
            <label htmlFor={pathId}>expected branch</label>
            <input
              id={pathId}
              defaultValue={field.expectedPath || ""}
              onChange={(e) => onEdit(`${field.field}__expectedPath`, e.target.value)}
            />
          </div>
        );
      })}
      <p className="muted">
        수정값은 임시 Case 또는 새 Input Profile 버전으로 저장할 수 있습니다. 저장·승인 확정은 HITL입니다.
      </p>
    </fieldset>
  );
}

function FailurePanel({
  step,
  run,
  onRetest,
  busy,
}: {
  step: RunStep;
  run: RunSummary;
  onRetest: (reuse: boolean) => void;
  busy: boolean;
}) {
  const shotName = step.screenshotPath?.split("/").pop();
  const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";
  return (
    <section
      className="run-console-block is-error"
      data-testid="run-failure-panel"
      aria-labelledby="run-failure-heading"
    >
      <h3 id="run-failure-heading">어디에서 막혔는지 먼저 보기</h3>
      <dl className="run-setup-facts">
        <div>
          <dt>막힌 단계</dt>
          <dd>
            <strong>{stepActionKo(step.action)}</strong>
          </dd>
        </div>
        <div>
          <dt>관측된 원인</dt>
          <dd>{step.observationSummary || run.outcomeSummary || "관측 요약이 없습니다"}</dd>
        </div>
        <div>
          <dt>기대와 다른 점</dt>
          <dd>
            {step.missingData && step.missingData.length > 0
              ? `${step.missingData.slice(0, 3).join(" · ")} 확인 필요`
              : "화면 캡쳐와 관측 요약으로 확인하세요"}
          </dd>
        </div>
      </dl>
      {shotName && (
        <figure className="run-failure-shot">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={`${API}/api/runs/${run.runId}/evidence/file?path=${encodeURIComponent(shotName)}`}
            alt={`${step.stepId} 실패 시점 화면`}
            loading="lazy"
          />
          <figcaption>{shotName}</figcaption>
        </figure>
      )}
      <div className="inline-actions">
        <button
          type="button"
          className="primary-btn"
          disabled={busy}
          aria-busy={busy || undefined}
          onClick={() => onRetest(true)}
        >
          {busy && <BusyIndicator size={14} />}
          {busy ? "재실행 준비 중…" : "같은 입력으로 재실행"}
        </button>
        <button type="button" className="ghost-btn" disabled={busy} onClick={() => onRetest(false)}>
          값 수정 후 재실행
        </button>
        <Link className="ghost-btn" href={`/runs/${run.runId}`}>
          전체 증적 보기
        </Link>
      </div>
    </section>
  );
}

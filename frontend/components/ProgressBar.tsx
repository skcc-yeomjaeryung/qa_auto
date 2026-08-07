"use client";

import { Icon } from "./Icon";

export type ProgressStatus =
  | "empty"
  | "progressing"
  | "complete"
  | "error"
  | "warning"
  | "disable";

export type JourneyStepState = {
  label: string;
  status: ProgressStatus;
};

/**
 * Figma Data Table `row-cell / barchart`를 제품 테이블 밀도에 맞춘 공통 진행 셀.
 * 성공·오류·판정대기 구간을 한 트랙에서 구분하고, 화면별로 별도 막대를 만들지 않는다.
 */
export function TableProgressCell({
  total,
  completed,
  success = 0,
  failed = 0,
  running = 0,
  successLabel = "성공 관측",
  failureLabel = "실패 관측",
  emptyLabel = "미실행",
  status,
  testId,
}: {
  total: number;
  completed: number;
  success?: number;
  failed?: number;
  running?: number;
  successLabel?: string;
  failureLabel?: string;
  emptyLabel?: string;
  status?: ProgressStatus;
  testId?: string;
}) {
  const safeTotal = Math.max(0, total);
  const safeCompleted = Math.max(0, Math.min(safeTotal || completed, completed));
  const safeSuccess = Math.max(0, Math.min(safeCompleted, success));
  const safeFailed = Math.max(0, Math.min(safeCompleted - safeSuccess, failed));
  const neutral = Math.max(0, safeCompleted - safeSuccess - safeFailed);
  const percent = safeTotal ? Math.round((safeCompleted / safeTotal) * 100) : 0;
  const resolvedStatus = status ?? (
    running > 0
      ? "progressing"
      : safeFailed > 0
        ? "warning"
        : safeTotal > 0 && safeCompleted >= safeTotal
          ? "complete"
          : "empty"
  );
  const widthOf = (value: number) => safeTotal ? `${(value / safeTotal) * 100}%` : "0%";
  const summary = safeCompleted === 0 && running === 0
    ? emptyLabel
    : [
        safeSuccess > 0 ? `${successLabel} ${safeSuccess}` : null,
        safeFailed > 0 ? `${failureLabel} ${safeFailed}` : null,
        neutral > 0 ? `검토 ${neutral}` : null,
        running > 0 ? `진행 ${running}` : null,
      ].filter(Boolean).join(" · ");

  return (
    <div
      className={`table-progress-cell is-${resolvedStatus}`}
      data-testid={testId ?? "table-progress-cell"}
      aria-label={`완료 ${safeCompleted}/${safeTotal}건. ${summary}`}
    >
      <div className="table-progress-meta">
        <strong>{safeCompleted}/{safeTotal}건</strong>
        <span>{summary}</span>
      </div>
      <div
        className="table-progress-track"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <i className="is-success" style={{ width: widthOf(safeSuccess) }} />
        <i className="is-neutral" style={{ width: widthOf(neutral) }} />
        <i className="is-failure" style={{ width: widthOf(safeFailed) }} />
      </div>
    </div>
  );
}

/** Figma Progress Bar Type 1 — % + label + track (D-009) */
export function ProgressBarType1({
  percent,
  label,
  status = "progressing",
  testId,
}: {
  percent: number;
  label: string;
  status?: ProgressStatus;
  testId?: string;
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(percent)));
  return (
    <div className={`pb-type1 is-${status}`} data-testid={testId ?? "progress-type1"}>
      <div className={`pb-type1-icon is-${status}`}>
        <ProgressGlyph status={status} size={18} />
      </div>
      <div className="pb-type1-body">
        <div className="pb-type1-meta">
          <strong>{clamped}%</strong>
          <span>{label}</span>
        </div>
        <div className="pb-type1-track" role="progressbar" aria-valuenow={clamped} aria-valuemin={0} aria-valuemax={100}>
          <div className="pb-type1-fill" style={{ width: `${clamped}%` }} />
        </div>
      </div>
    </div>
  );
}

/** Figma Progress Bar Type 2 — stepper with connectors (D-009) */
export function ProgressBarType2({
  steps,
  testId,
  /** When true, the last progressing step pulses (최종 등록 확인). */
  pulseFinal = false,
  onStepClick,
}: {
  steps: JourneyStepState[];
  testId?: string;
  pulseFinal?: boolean;
  /** 수정 화면에서는 저장된 각 STEP을 바로 열 수 있다. */
  onStepClick?: (stepIndex: number) => void;
}) {
  const lastIdx = steps.length - 1;
  return (
    <div className="pb-type2" data-testid={testId ?? "progress-type2"}>
      <div className="pb-type2-line" aria-hidden>
        {steps.slice(0, -1).map((step, i) => (
          <span
            key={`seg-${step.label}`}
            className={`pb-type2-seg is-${lineStatus(step.status, steps[i + 1]?.status)}`}
          />
        ))}
      </div>
      {steps.map((step, i) => {
        const isFinalPulse =
          pulseFinal && i === lastIdx && (step.status === "progressing" || step.status === "complete");
        const content = (
          <>
            <span className={`pb-type2-dot is-${step.status}`}>
              <ProgressGlyph status={step.status} size={12} />
            </span>
            <em>{step.label}</em>
          </>
        );
        const className = `pb-type2-step is-${step.status}${isFinalPulse ? " is-final-blink" : ""}`;
        return onStepClick ? (
          <button
            key={step.label}
            type="button"
            className={`${className} is-clickable`}
            onClick={() => onStepClick(i)}
            aria-current={step.status === "progressing" ? "step" : undefined}
            title={`${step.label} 수정`}
          >
            {content}
          </button>
        ) : (
          <div key={step.label} className={className}>{content}</div>
        );
      })}
    </div>
  );
}

/** Figma Progress Bar Type 4 — step detail + ETA (run / upload) */
export function ProgressBarType4({
  title,
  stepLabel,
  percent,
  eta,
  status = "progressing",
  testId,
}: {
  title: string;
  stepLabel: string;
  percent: number;
  eta?: string;
  status?: ProgressStatus;
  testId?: string;
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(percent)));
  return (
    <div className={`pb-type4 is-${status}`} data-testid={testId ?? "progress-type4"}>
      <div className="pb-type4-head">
        <strong>{title}</strong>
        <span>
          {stepLabel}
          {eta ? ` · ${eta}` : ""}
        </span>
      </div>
      <div className="pb-type4-track" role="progressbar" aria-valuenow={clamped}>
        <div className="pb-type4-fill" style={{ width: `${clamped}%` }} />
      </div>
      <div className="pb-type4-foot">
        <ProgressGlyph status={status} size={14} />
        <span>{clamped}%</span>
        <span className="muted">Complete ≠ HITL Pass</span>
      </div>
    </div>
  );
}

export function ProgressGlyph({ status, size }: { status: ProgressStatus; size: number }) {
  if (status === "complete") return <Icon name="progress-check" size={size} />;
  if (status === "error") return <Icon name="progress-error" size={size} />;
  if (status === "warning") return <Icon name="progress-warning" size={size} />;
  if (status === "progressing") return <Icon name="progress-progressing" size={size} />;
  if (status === "disable") return <Icon name="progress-disable" size={size} />;
  return <Icon name="progress-empty" size={size} />;
}

/** Figma Progress Icons · Progressing — button/inline busy (D-009) */
export function BusyIndicator({
  size = 14,
  label = "처리 중",
  className = "",
}: {
  size?: number;
  label?: string;
  className?: string;
}) {
  return (
    <span className={`ui-busy ${className}`.trim()} role="status" aria-live="polite" aria-label={label}>
      <span className="ui-busy-spin">
        <ProgressGlyph status="progressing" size={size} />
      </span>
    </span>
  );
}

function lineStatus(left: ProgressStatus, right?: ProgressStatus): ProgressStatus {
  if (left === "error" || right === "error") return "error";
  if (left === "warning" || right === "warning") return "warning";
  // Figma Type 2: filled connector only after a completed step (not while current is progressing)
  if (left === "complete") return "complete";
  return "empty";
}

export function mapDomainToProgress(status: string | undefined): ProgressStatus {
  const s = (status || "pending").toLowerCase();
  if (s === "complete" || s === "cached" || s === "success" || s === "ready") return "complete";
  if (s === "progressing" || s === "running" || s === "syncing") return "progressing";
  if (s === "error" || s === "failed") return "error";
  if (s === "warning" || s === "review" || s === "review_required") return "warning";
  if (s === "disable" || s === "disabled") return "disable";
  return "empty";
}

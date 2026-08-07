"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { formatDateTime } from "../../lib/datetime";
import { retestRun, startInteractiveRun } from "../../lib/interactiveRun";
import {
  buildScenarioFlowNodes,
  buildScenarioGuide,
  type ScenarioFlowNode,
} from "../../lib/scenarioGuide";
import { scenarioTitleKo } from "../../lib/scenarioLabels";
import { humanizeObservation } from "../../lib/scenarios";
import { ImageLightbox, type LightboxImage } from "../ImageLightbox";
import { PanelLoading } from "../LoadingStates";
import { ProgressGlyph } from "../ProgressBar";

/** 재처리 아이콘 — 컴포넌트 1시 방향 모서리에 놓는다 */
function RefreshIcon({ spinning }: { spinning: boolean }) {
  return (
    <svg
      className={spinning ? "is-spinning" : undefined}
      width="13"
      height="13"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      aria-hidden
    >
      <path d="M21 12a9 9 0 1 1-3.2-6.9" />
      <path d="M21 3v6h-6" />
    </svg>
  );
}

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";

type StepStatus = "complete" | "error" | "warning" | "progressing" | "empty";

type ScenarioDetail = {
  scenarioId: string;
  serviceId?: string | null;
  name?: string | null;
  unresolvedCount?: number;
  result?: Record<string, any> | null;
};

type RunStep = {
  stepId: string;
  action?: string;
  status?: string;
  observationSummary?: string | null;
  missingData?: string[];
  screenshotPath?: string | null;
};

type RunDetail = {
  runId: string;
  status?: string;
  outcomeKind?: string | null;
  outcomeSummary?: string | null;
  createdAt?: string | null;
  inputs?: Record<string, unknown>;
  steps?: RunStep[];
  result?: {
    runNarrative?: string | null;
    verdict?: {
      verdict?: string;
      reason?: string;
      verdictReason?: string;
      blockedCause?: string | null;
    } | null;
    inputBindings?: Array<{
      stepId?: string;
      field?: string;
      value?: string | null;
      source?: string;
      rationale?: string;
      filled?: boolean;
    }>;
  } | null;
};

/** 실행에서만 생기는 단계(화면 관측 바인딩·섬밋)의 한글 이름 */
const RUN_ONLY_STEP: Record<string, { label: string; kind: ScenarioFlowNode["kind"]; text: string }> = {
  dom_bind: {
    label: "화면 입력 자동 바인딩",
    kind: "input",
    text: "화면에서 입력 칸을 찾아 연결 계정·코드 근거로 값을 넣습니다",
  },
  submit: {
    label: "입력 섬밋",
    kind: "action",
    text: "입력한 값을 제출하고 다음 화면을 관측합니다",
  },
};

type FlowNodeView = {
  key: string;
  order: number;
  label: string;
  text: string;
  kind: ScenarioFlowNode["kind"];
  inputs: Array<[string, string]>;
  status: StepStatus;
  note: string | null;
  missing: string[];
  shot: string | null;
  /** 이 캡쳐가 단계에 직접 붙은 것이 아니라 실행 전체 증적에서 온 경우 */
  shotUnassigned?: boolean;
};

/** 단계 증적 스크린샷 경로를 조회 URL로 — 절대 경로는 파일명만 쓴다 */
function shotUrl(runId: string | undefined, path: string | null | undefined): string | null {
  if (!runId || !path) return null;
  const name = String(path).split("/").pop();
  if (!name) return null;
  return `${API}/api/runs/${runId}/evidence/file?path=${encodeURIComponent(name)}`;
}

const KIND_KO: Record<ScenarioFlowNode["kind"], string> = {
  screen: "화면",
  input: "입력",
  action: "동작",
  server: "서버 호출",
  check: "확인",
};

/** 실행 상태를 진행 표시 아이콘 상태로 */
function toStepStatus(raw: string | undefined): StepStatus {
  const key = (raw || "").toLowerCase();
  if (["complete", "completed", "success", "passed", "ok"].includes(key)) return "complete";
  if (["error", "failed", "failure", "timeout"].includes(key)) return "error";
  if (["warning", "warn", "partial"].includes(key)) return "warning";
  if (["running", "in_progress", "active", "started"].includes(key)) return "progressing";
  return "empty";
}

const STEP_STATUS_KO: Record<StepStatus, string> = {
  complete: "정상 수행",
  error: "실패 관측",
  warning: "확인 필요",
  progressing: "수행 중",
  empty: "미수행",
};

/**
 * 시나리오 한 건의 실행 흐름을 한글 문장 체인으로 보여준다.
 *
 * 개발자용 노드 그래프가 아니라 "무엇을 → 무엇을 → 종료" 흐름과
 * 각 단계가 성공·실패로 관측됐는지를 읽는 화면이다.
 */
export function ScenarioFlowBoard({
  scenarioId,
  showRunLink = true,
}: {
  scenarioId: string;
  /**
   * 상세 패널 안에 들어갈 때는 `false`.
   * 실행 콘솔이 같은 화면에 있어 이동 링크가 필요 없고,
   * 제목·케이스 ID·실행 ID도 상세 헤더와 겹치므로 접는다.
   */
  showRunLink?: boolean;
}) {
  const [scenario, setScenario] = useState<ScenarioDetail | null>(null);
  const [run, setRun] = useState<RunDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [open, setOpen] = useState<Record<string, "input" | "output" | null>>({});
  const [zoom, setZoom] = useState<LightboxImage | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  /** 단계에 붙지 않은 실행 캡쳐 — 단계 캡쳐가 없을 때만 보조로 보여준다 */
  const [runShots, setRunShots] = useState<string[]>([]);

  function togglePane(key: string, pane: "input" | "output") {
    setOpen((prev) => ({ ...prev, [key]: prev[key] === pane ? null : pane }));
  }

  useEffect(() => {
    let alive = true;
    async function load() {
      setLoading(true);
      setMessage(null);
      try {
        const sRes = await fetch(`${API}/api/scenarios/${scenarioId}`, { cache: "no-store" });
        if (!sRes.ok) throw new Error("시나리오를 찾을 수 없습니다");
        const detail = (await sRes.json()) as ScenarioDetail;
        if (!alive) return;
        setScenario(detail);

        const rRes = await fetch(`${API}/api/scenarios/${scenarioId}/runs`, { cache: "no-store" });
        if (!rRes.ok) {
          setRun(null);
          return;
        }
        const runs = (await rRes.json()) as RunDetail[];
        const latest = runs[0];
        if (!latest) {
          setRun(null);
          return;
        }
        const dRes = await fetch(`${API}/api/runs/${latest.runId}`, { cache: "no-store" });
        if (alive) setRun(dRes.ok ? ((await dRes.json()) as RunDetail) : latest);
        const eRes = await fetch(`${API}/api/runs/${latest.runId}/evidence`, { cache: "no-store" });
        if (alive && eRes.ok) {
          const ev = (await eRes.json()) as { screenshots?: Array<{ url: string }> };
          setRunShots((ev.screenshots || []).map((s) => `${API}${s.url}`));
        }
      } catch (err) {
        if (alive) setMessage(err instanceof Error ? err.message : "불러오지 못했습니다");
      } finally {
        if (alive) setLoading(false);
      }
    }
    void load();
    return () => {
      alive = false;
    };
  }, [scenarioId, reloadKey]);

  /** 재처리 — 같은 시나리오를 직전 실행 입력으로 다시 실행하고 결과를 다시 읽는다 */
  async function retry() {
    setRetrying(true);
    setMessage(null);
    try {
      const target = run?.runId;
      if (target) await retestRun(target, { reuseFromRunId: target });
      else await startInteractiveRun(scenarioId, {});
      setReloadKey((v) => v + 1);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "재처리 실패");
    } finally {
      setRetrying(false);
    }
  }

  const guide = useMemo(
    () =>
      scenario
        ? buildScenarioGuide({
            scenarioId: scenario.scenarioId,
            serviceId: scenario.serviceId,
            name: scenario.name,
            unresolvedCount: scenario.unresolvedCount,
            result: scenario.result as never,
          })
        : null,
    [scenario],
  );

  const title = scenario
    ? scenarioTitleKo({
        name: scenario.name,
        serviceId: scenario.serviceId,
        result: scenario.result as never,
      })
    : "";

  /** 시나리오 단계 + 실행 결과(상태·캡쳐·관측)를 노드 카드 재료로 합친다 */
  const chain = useMemo<FlowNodeView[]>(() => {
    if (!guide || !scenario) return [];
    const nodes = buildScenarioFlowNodes(
      {
        scenarioId: scenario.scenarioId,
        serviceId: scenario.serviceId,
        name: scenario.name,
        result: scenario.result as never,
      },
      run?.inputs || {}
    );
    const runSteps = run?.steps || [];
    const byId = new Map(runSteps.map((s) => [s.stepId, s]));
    const base: FlowNodeView[] =
      nodes.length > 0
        ? nodes.map((node, index) => {
            const runStep = byId.get(node.key) ?? runSteps[index];
            return {
              key: node.key,
              order: index + 1,
              label: node.label,
              text: node.text,
              kind: node.kind,
              inputs: node.inputs,
              status: toStepStatus(runStep?.status),
              note: runStep?.observationSummary || null,
              missing: runStep?.missingData ?? [],
              shot: shotUrl(run?.runId, runStep?.screenshotPath),
            };
          })
        : guide.whatWeDo.map((text, index) => ({
            key: `step-${index}`,
            order: index + 1,
            label: `${index + 1}단계`,
            text,
            kind: "check" as const,
            inputs: [],
            status: "empty" as StepStatus,
            note: null,
            missing: [],
            shot: null,
          }));

    // 실행에서만 생긴 단계(화면 관측 바인딩·섬밋)도 흐름에 이어 붙인다 — 실제로 한 일이다.
    const usedIds = new Set(base.map((n) => n.key));
    const bindings = run?.result?.inputBindings || [];
    for (const rs of runSteps) {
      const action = String(rs.action || "").toLowerCase();
      const meta = RUN_ONLY_STEP[action];
      if (!meta || usedIds.has(rs.stepId)) continue;
      base.push({
        key: rs.stepId,
        order: base.length + 1,
        label: meta.label,
        text: meta.text,
        kind: meta.kind,
        inputs: bindings
          .filter((b) => !b.stepId || b.stepId === rs.stepId)
          .map((b) => [b.field || "입력", `${b.value ?? "값 없음"} · ${b.rationale || b.source || ""}`] as [string, string]),
        status: toStepStatus(rs.status),
        note: rs.observationSummary || null,
        missing: rs.missingData ?? [],
        shot: shotUrl(run?.runId, rs.screenshotPath),
      });
    }

    // 결과 전체가 기대 불충족인데 개별 step이 모두 ok인 과거 실행도 전부
    // 초록으로 보이면 안 된다. 구조화 verdict를 최종 안전장치로 사용해
    // 오류와 가장 가까운 단계(서버/클릭/마지막 단계)를 보수적으로 내린다.
    const verdict = run?.result?.verdict;
    const blockingOutcome = ["be_error", "fe_error", "business_error"].includes(String(run?.outcomeKind || ""));
    if ((verdict?.verdict === "expected_not_met" || blockingOutcome) && base.length > 0) {
      const cause = String(verdict?.blockedCause || "");
      const explicitBlockingNodes = base.filter((node) =>
        /error=server_error|\/none#error=|not found|요청된 url을 찾을 수 없/i.test(String(node.note || "")),
      );
      for (const node of explicitBlockingNodes) {
        node.status = "error";
        node.note = run?.outcomeSummary || node.note;
      }
      const target = [...base].reverse().find((node) =>
        cause === "server_error" || cause === "not_found" || cause === "method_not_allowed" || run?.outcomeKind === "be_error"
          ? node.kind === "server" || node.kind === "action"
          : node.kind === "check" || node.kind === "action",
      ) ?? base[base.length - 1];
      target.status = "error";
      target.note = run?.outcomeSummary || verdict?.verdictReason || verdict?.reason || target.note || "기대 결과와 다르게 관측됐습니다";
    } else if (verdict?.verdict === "undetermined" && base.length > 0 && base.every((node) => node.status === "complete")) {
      const target = base[base.length - 1];
      target.status = "warning";
      target.note = verdict.verdictReason || verdict.reason || "판정할 관측 근거가 부족합니다";
    }

    // 단계에 붙은 캡쳐가 하나도 없으면(구 실행) 실행 캡쳐를 화면 노드에 보조로 붙인다.
    if (base.every((n) => !n.shot) && runShots.length > 0) {
      const first = base.find((n) => n.kind === "screen") ?? base[0];
      if (first) {
        first.shot = runShots[0];
        first.shotUnassigned = true;
      }
    }

    // 마지막에 종료 노드 — 사용자가 흐름의 끝을 알 수 있게 한다
    const allDone = base.length > 0 && base.every((i) => i.status === "complete");
    const anyFail = base.some((i) => i.status === "error")
      || run?.result?.verdict?.verdict === "expected_not_met"
      || ["be_error", "fe_error", "business_error"].includes(String(run?.outcomeKind || ""));
    const anyWarning = base.some((i) => i.status === "warning") || run?.result?.verdict?.verdict === "undetermined";
    base.push({
      key: "end",
      order: base.length + 1,
      label: "종료",
      text: anyFail
        ? "실패한 단계가 있어 여기서 확인이 필요합니다"
        : anyWarning
          ? "관측 근거가 부족한 단계가 있어 담당자 확인이 필요합니다"
          : allDone
          ? "여기까지 정상 수행되어 종료했습니다"
          : "테스트를 실행하면 이 흐름대로 진행됩니다",
      kind: "check",
      inputs: [],
      status: anyFail ? "error" : anyWarning ? "warning" : allDone ? "complete" : "empty",
      note: null,
      missing: [],
      shot: null,
    });
    return base;
  }, [guide, scenario, run, runShots]);

  if (loading) return <PanelLoading label="시나리오 실행 흐름을 불러오는 중입니다" />;
  if (message) {
    return (
      <div className="connect-banner is-warn" role="alert">
        {message}
      </div>
    );
  }
  if (!scenario || !guide) return null;

  const caseId = scenario.result?.caseId || scenario.scenarioId;
  const executed = Boolean(run);
  const blockingOutcome = ["be_error", "fe_error", "business_error"].includes(String(run?.outcomeKind || ""));
  const displayedOutcome = blockingOutcome
    ? run?.outcomeSummary
    : run?.result?.runNarrative || run?.outcomeSummary;

  return (
    <section className="sflow anim-fade-in" data-testid="scenario-flow-board">
      <header className="sflow-head">
        <div>
          <p className="sflow-kicker">
            {showRunLink ? `{${title}} 실행 흐름` : "단계별 실행 흐름"}
          </p>
          {showRunLink && <h3>{guide.headline}</h3>}
          <p className="sflow-sub">
            {showRunLink && (
              <>
                테스트 케이스 <strong>{caseId}</strong> · {guide.kindLabel}
              </>
            )}
            {executed
              ? `${showRunLink ? " · " : ""}최근 실행 ${formatDateTime(run?.createdAt)}`
              : `${showRunLink ? " · " : ""}아직 실행하지 않았습니다 — 아래 흐름대로 진행됩니다`}
          </p>
        </div>
        {showRunLink && (
          <Link className="primary-btn" href={`/scenarios/${scenarioId}`}>
            이 시나리오 실행하기
          </Link>
        )}
      </header>

      <ol className="sflow-chain" data-testid="scenario-flow-chain">
        {chain.map((step, index) => {
          const pane = open[step.key];
          return (
            <li className={`sflow-node is-${step.status}`} key={step.key}>
              <div className="sflow-card">
                <div className="sflow-card-head">
                  <span className="sflow-kind">
                    {step.key === "end" ? "종료" : `${step.order}. ${KIND_KO[step.kind]}`}
                  </span>
                  {step.key !== "end" && (
                    <button
                      type="button"
                      className="sflow-refresh"
                      title="이 시나리오를 같은 값으로 다시 실행합니다 (재처리)"
                      aria-label="재처리"
                      disabled={retrying}
                      onClick={() => void retry()}
                      data-testid={`sflow-retry-${step.key}`}
                    >
                      <RefreshIcon spinning={retrying} />
                    </button>
                  )}
                </div>
                <strong className="sflow-label">{step.label}</strong>
                {step.shot ? (
                  <button
                    type="button"
                    className="sflow-shot"
                    onClick={() => setZoom({ src: step.shot!, caption: `${step.label} 캡쳐` })}
                    aria-label={`${step.label} 캡쳐 확대`}
                    data-testid="sflow-capture"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={step.shot} alt={`${step.label} 캡쳐`} loading="lazy" />
                    {step.shotUnassigned && (
                      <span className="sflow-shot-tag">단계 미지정 실행 캡쳐</span>
                    )}
                  </button>
                ) : (
                  step.key !== "end" && (
                    <div className="sflow-shot is-empty">
                      <span className="muted">
                        {executed ? "이 단계 캡쳐 없음" : "실행하면 캡쳐가 남습니다"}
                      </span>
                    </div>
                  )
                )}
                <p className="sflow-text">{step.text}</p>
                <div className="sflow-io-btns">
                  {step.key !== "end" && (
                    <>
                      <button
                        type="button"
                        className={`sflow-io-btn${pane === "input" ? " is-on" : ""}`}
                        aria-pressed={pane === "input"}
                        onClick={() => togglePane(step.key, "input")}
                      >
                        입력값
                      </button>
                      <button
                        type="button"
                        className={`sflow-io-btn${pane === "output" ? " is-on" : ""}`}
                        aria-pressed={pane === "output"}
                        onClick={() => togglePane(step.key, "output")}
                      >
                        결과
                      </button>
                    </>
                  )}
                  <span className="sflow-status">
                    <ProgressGlyph status={step.status} size={12} />
                    {STEP_STATUS_KO[step.status]}
                  </span>
                </div>
                {pane === "input" && (
                  <dl className="sflow-io anim-slide-down">
                    {step.inputs.length === 0 ? (
                      <p className="muted">이 단계는 값을 넣지 않습니다.</p>
                    ) : (
                      step.inputs.map(([k, v]) => (
                        <div key={k}>
                          <dt>{k}</dt>
                          <dd>{v}</dd>
                        </div>
                      ))
                    )}
                  </dl>
                )}
                {pane === "output" && (
                  <div className="sflow-io anim-slide-down">
                    <p>{step.note || (executed ? "관측 요약이 없습니다" : "아직 실행하지 않았습니다")}</p>
                    {step.missing.length > 0 && (
                      <p className="sflow-missing">확인 필요: {step.missing.slice(0, 3).join(", ")}</p>
                    )}
                  </div>
                )}
              </div>
              {index < chain.length - 1 && (
                <span className="sflow-arrow" aria-hidden="true">
                  →
                </span>
              )}
            </li>
          );
        })}
      </ol>
      {zoom && (
        <ImageLightbox images={[zoom]} index={0} onClose={() => setZoom(null)} />
      )}

      {showRunLink && (
        <div className="sflow-legend">
          <span>
            성공으로 보이면 — <em>{guide.successLooksLike}</em>
          </span>
          <span>
            실패로 보이면 — <em>{guide.failureLooksLike}</em>
          </span>
        </div>
      )}

      {humanizeObservation(displayedOutcome) && (
        <p className="sflow-outcome">
          최근 실행 관측 요약 —{" "}
          {humanizeObservation(displayedOutcome)}
        </p>
      )}
      {showRunLink && (
        <p className="sflow-guard">
          흐름과 상태는 실행에서 관측한 자료입니다. 최종 합격·불합격 판정은 담당자가 승인 검토에서
          확정합니다.
        </p>
      )}
    </section>
  );
}

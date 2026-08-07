"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { formatDateTime } from "../../lib/datetime";
import { buildScenarioGuide, screenLabelKo } from "../../lib/scenarioGuide";
import { narrateScenarioSteps, scenarioTitleKo } from "../../lib/scenarioLabels";
import { humanizeObservation } from "../../lib/scenarios";
import { ScenarioFlowBoard } from "../flow/ScenarioFlowBoard";
import { PanelLoading } from "../LoadingStates";
import { ScenarioRunConsole } from "../ScenarioRunConsole";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";

type CaseAnalysis = {
  caseId?: string;
  testType?: string;
  targetScreen?: string;
  targetFile?: string;
  usernameSelector?: string;
  passwordSelector?: string;
  submitSelector?: string;
  connectedApi?: string;
  requestValues?: string;
  expectedResult?: string;
};

type VerdictCriterion = {
  id: string;
  check?: string;
  expected?: string;
  result?: string;
  observed?: string;
};

type RunVerdict = {
  verdict?: string;
  verdictReason?: string;
  reason?: string;
  coverageNote?: string;
  criteriaResults?: VerdictCriterion[];
  criteria?: VerdictCriterion[];
  blockingIssues?: Array<{ kind?: string; detail?: string; suggestedFix?: string }>;
  remediation?: string[];
};

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
};

type LatestRun = {
  runId: string;
  outcomeKind?: string | null;
  outcomeSummary?: string | null;
  observationSummary?: string | null;
  createdAt?: string | null;
  result?: { verdict?: RunVerdict | null; runDiagnosis?: RunDiagnosis | null } | null;
};

type TabKey = "composition" | "flow" | "result";

/** 관측 결과 표기 — 「성공 확정」이 아니라 무엇으로 관측됐는지만 말한다 */
const OUTCOME_KO: Record<string, string> = {
  success: "정상 관측",
  be_error: "서버 오류 관측",
  business_error: "업무 오류 관측",
  fe_error: "화면 오류 관측",
  unknown: "판정 불가",
  policy: "실행 정책 확인",
};

const CRITERION_KO: Record<string, string> = {
  met: "관측됨",
  not_met: "관측 안 됨",
  undetermined: "확인 못 함",
};

function KeyIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <circle cx="8" cy="12" r="4" />
      <path d="M12 12h9M17.5 12v3M20.5 12v2.5" strokeLinecap="round" />
    </svg>
  );
}

function ScreenIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <rect x="3" y="4" width="18" height="12" rx="2" />
      <path d="M8 20h8M12 16v4" strokeLinecap="round" />
      <path d="M6.5 8h6" strokeLinecap="round" />
    </svg>
  );
}

function FlowIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <rect x="3" y="3.5" width="7" height="6" rx="1.6" />
      <rect x="14" y="14.5" width="7" height="6" rx="1.6" />
      <path d="M6.5 9.5v5a3 3 0 0 0 3 3H14" strokeLinecap="round" />
    </svg>
  );
}

function ResultIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <path d="M9 3.5h6a1.5 1.5 0 0 1 1.5 1.5v0A1.5 1.5 0 0 1 15 6.5H9A1.5 1.5 0 0 1 7.5 5v0A1.5 1.5 0 0 1 9 3.5Z" />
      <path d="M6.5 5H5.5A1.5 1.5 0 0 0 4 6.5v13A1.5 1.5 0 0 0 5.5 21h13a1.5 1.5 0 0 0 1.5-1.5v-13A1.5 1.5 0 0 0 18.5 5h-1" />
      <path d="M8.5 13.5l2.5 2.5 4.5-5" strokeLinecap="round" />
    </svg>
  );
}

const TABS: Array<{ key: TabKey; label: string; hint: string; icon: () => React.ReactElement }> = [
  {
    key: "composition",
    label: "화면 구성 확인",
    hint: "어떤 화면에서 무엇을 보는지",
    icon: ScreenIcon,
  },
  { key: "flow", label: "실행 흐름", hint: "단계 순서와 화면 캡쳐", icon: FlowIcon },
  { key: "result", label: "예상 테스트 결과", hint: "판단 기준 · 입력 · 결과 요약", icon: ResultIcon },
];

/** 분석이 만든 기대 결과 문장을 확인 항목 칩으로 — 없으면 빈 배열 */
function expectedItems(expected: string | undefined): string[] {
  const text = String(expected || "").trim();
  if (!text) return [];
  const listPart = text.replace(/\s*이\(가\)\s*표시되어야 함.*$/, "");
  const items = listPart
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return Array.from(new Set(items));
}

/**
 * 시나리오 한 건의 상세.
 *
 * 「화면 구성 확인 · 실행 흐름 · 예상 테스트 결과」 3개 탭으로 나눠
 * 담당자가 한 번에 읽을 양을 줄인다. 실행 ID·버전·selector 같은 기술 정보는
 * 각 탭의 「기술 상세」 접이식에만 둔다 (데이터는 그대로 유지한다).
 */
export function ScenarioDetailPanel({
  scenarioId,
  graphHref,
}: {
  scenarioId: string;
  /** 이 시나리오의 의존관계 그래프 화면 경로 (없으면 버튼을 숨긴다) */
  graphHref?: string | null;
}) {
  const [row, setRow] = useState<Record<string, any> | null>(null);
  const [latestRun, setLatestRun] = useState<LatestRun | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<TabKey>("composition");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setMessage(null);
    setRow(null);
    setLatestRun(null);
    setTab("composition");
    void (async () => {
      try {
        const res = await fetch(`${API}/api/scenarios/${scenarioId}`, { cache: "no-store" });
        if (!res.ok) throw new Error("시나리오를 찾을 수 없습니다");
        const data = (await res.json()) as Record<string, any>;
        if (!alive) return;
        setRow(data);
      } catch (err) {
        if (alive) setMessage(err instanceof Error ? err.message : "불러오지 못했습니다");
      } finally {
        if (alive) setLoading(false);
      }
      try {
        const res = await fetch(`${API}/api/scenarios/${scenarioId}/runs`, { cache: "no-store" });
        if (!res.ok) return;
        const runs = (await res.json()) as LatestRun[];
        if (alive) setLatestRun(runs[0] ?? null);
      } catch {
        // 최근 실행이 없어도 상세는 읽을 수 있다
      }
    })();
    return () => {
      alive = false;
    };
  }, [scenarioId]);

  const result = row?.result || {};
  const caseAnalysis = (result.caseAnalysis || row?.caseAnalysis) as CaseAnalysis | undefined;
  const steps = (result.steps as Array<Record<string, unknown>>) || [];
  const narratives = useMemo(() => narrateScenarioSteps(steps), [steps]);

  /** 개발자용 식별자·selector — 화면 기본 흐름에서는 접어 둔다 */
  const technicalRows = useMemo(
    () => [
      { label: "케이스 ID", value: caseAnalysis?.caseId || result.caseId || "—" },
      { label: "시나리오 ID", value: scenarioId },
      { label: "테스트 유형", value: caseAnalysis?.testType || "—" },
      { label: "대상 화면", value: caseAnalysis?.targetScreen || "—" },
      { label: "대상 파일", value: caseAnalysis?.targetFile || "—" },
      { label: "아이디 입력", value: caseAnalysis?.usernameSelector || "—" },
      { label: "비밀번호 입력", value: caseAnalysis?.passwordSelector || "—" },
      { label: "제출 버튼", value: caseAnalysis?.submitSelector || "—" },
      { label: "연결 API", value: caseAnalysis?.connectedApi || "—" },
      { label: "요청값", value: caseAnalysis?.requestValues || "—" },
      { label: "기대 결과", value: caseAnalysis?.expectedResult || "—" },
    ],
    [caseAnalysis, result.caseId, scenarioId],
  );

  const guide = useMemo(() => {
    if (!row) return null;
    return buildScenarioGuide({
      scenarioId,
      serviceId: row.serviceId,
      name: row.name,
      unresolvedCount: row.unresolvedCount,
      result: row.result,
    });
  }, [row, scenarioId]);

  if (loading) return <PanelLoading label="시나리오 상세를 불러오는 중입니다" />;
  if (message) {
    return (
      <div className="connect-banner is-warn" role="alert">
        {message}
      </div>
    );
  }
  if (!row || !guide) return null;

  const title = scenarioTitleKo({
    name: row.name || result.name,
    serviceId: row.serviceId,
    result: row.result,
  });
  // 선행 로그인 단계 — 분석이 확인한 세션 선행조건만 보여준다 (D-015)
  const preconditionIds = new Set(
    ((result.preconditionStepIds as string[]) || []).map((id) => String(id)),
  );
  const preconditionSteps = steps.filter((s) => preconditionIds.has(String(s.id ?? "")));
  const authRequired = Boolean(result.authRequired);
  const adjustments = (result.mainStepAdjustments as Array<Record<string, string>>) || [];
  const criteria = (result.verdictCriteria as VerdictCriterion[]) || [];
  const runVerdict = latestRun?.result?.verdict || null;
  const runDiagnosis = latestRun?.result?.runDiagnosis || null;
  const policyBlocked = runDiagnosis?.causeCategory === "destructive_policy_blocked";
  const outcomeKind = policyBlocked
    ? "policy"
    : latestRun?.outcomeKind || (latestRun ? "unknown" : null);
  const observedById = new Map(
    (runVerdict?.criteriaResults || runVerdict?.criteria || []).map(
      (c) => [String(c.id), c] as const,
    ),
  );
  const sessionMissing = (result.sessionMissingData as string[]) || [];
  const screen = screenLabelKo(caseAnalysis?.targetScreen, "대상 화면");
  const checkItems = expectedItems(caseAnalysis?.expectedResult);
  // 실행 전 확인 사항 — 마지막 HITL 안내 문장은 화면 하단에서 한 번만 말한다
  const cautions = guide.cautions.filter((line) => !line.includes("최종 합격"));

  return (
    <div className="scn-detail-body" data-testid="scenario-detail-panel">
      <header className="sd-head">
        <div className="sd-head-main">
          <span className="sd-kind">{guide.kindLabel}</span>
          <h3 className="sd-title">{title}</h3>
          <p className="sd-lead">{guide.headline}</p>
        </div>
        <div className="sd-head-side">
          {outcomeKind ? (
            <span className={`outcome-pill outcome-${outcomeKind}`} data-testid="sd-outcome-pill">
              {OUTCOME_KO[outcomeKind] || outcomeKind}
            </span>
          ) : (
            <span className="sd-head-note">아직 실행하지 않았습니다</span>
          )}
          {latestRun?.createdAt && (
            <span className="sd-head-note">최근 실행 {formatDateTime(latestRun.createdAt)}</span>
          )}
          {graphHref && (
            <Link className="proc-btn proc-btn-primary" href={graphHref} data-testid="scenario-detail-graph">
              의존관계 그래프
            </Link>
          )}
        </div>
      </header>

      <div className="sd-tabs" role="tablist" aria-label="시나리오 상세 보기 방식">
        {TABS.map((item) => {
          const IconTag = item.icon;
          const on = tab === item.key;
          return (
            <button
              key={item.key}
              type="button"
              role="tab"
              aria-selected={on}
              aria-controls={`sd-panel-${item.key}`}
              className={on ? "sd-tab is-on" : "sd-tab"}
              onClick={() => setTab(item.key)}
              data-testid={`scenario-tab-${item.key}`}
            >
              <span className="sd-tab-ic">
                <IconTag />
              </span>
              <span className="sd-tab-text">
                <strong>{item.label}</strong>
                <em>{item.hint}</em>
              </span>
            </button>
          );
        })}
      </div>

      <div
        className="sd-panel anim-fade-in"
        role="tabpanel"
        id={`sd-panel-${tab}`}
        key={tab}
        data-testid={`scenario-panel-${tab}`}
      >
        {tab === "composition" && (
          <div className="sd-cards">
            <article className="sd-card">
              <h4>
                <span className="sd-card-ic">
                  <ScreenIcon />
                </span>
                이 테스트가 확인하는 것
              </h4>
              <ol className="sd-steps">
                {guide.whatWeDo.map((line, i) => (
                  <li key={i}>
                    <span className="sd-step-no">{i + 1}</span>
                    <span>{line}</span>
                  </li>
                ))}
              </ol>
            </article>

            <article className="sd-card">
              <h4>
                <span className="sd-card-ic">
                  <ResultIcon />
                </span>
                확인 대상
              </h4>
              <dl className="sd-facts">
                <div>
                  <dt>대상 화면</dt>
                  <dd>{screen}</dd>
                </div>
                <div>
                  <dt>확인 방식</dt>
                  <dd>{guide.kindLabel}</dd>
                </div>
                <div>
                  <dt>수행 단계</dt>
                  <dd>{steps.length > 0 ? `${steps.length}단계` : "실행 시 결정"}</dd>
                </div>
              </dl>
              {checkItems.length > 0 ? (
                <>
                  <p className="sd-card-note">화면에서 보여야 하는 항목 {checkItems.length}개</p>
                  <ul className="sd-chips">
                    {checkItems.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="sd-card-note">
                  분석에 확정된 확인 항목이 없습니다. 실행 관측으로 담당자가 확인합니다.
                </p>
              )}
            </article>

            {(authRequired || adjustments.length > 0) && (
              <article className="sd-card sd-precond" data-testid="sd-precondition">
                <h4>
                  <span className="sd-card-ic">
                    <KeyIcon />
                  </span>
                  본 단계 전에 먼저 하는 일
                </h4>
                {authRequired ? (
                  <p className="sd-card-note">
                    이 화면은 로그인 뒤에 있습니다. 연결 정보에 등록된 계정으로 먼저 로그인하고,
                    세션이 생긴 것을 화면에서 확인한 다음 본 단계를 진행합니다.
                  </p>
                ) : null}
                {preconditionSteps.length > 0 && (
                  <ol className="sd-steps">
                    {preconditionSteps.map((s, i) => (
                      <li key={String(s.id ?? i)}>
                        <span className="sd-step-no">{i + 1}</span>
                        <span>
                          {String(s.title || s.action || "")}
                          {s.reason ? <em className="sd-step-why">{String(s.reason)}</em> : null}
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
                {adjustments.length > 0 && (
                  <ul className="sd-notes">
                    {adjustments.map((a, i) => (
                      <li key={i}>{a.detail || `${a.route} ${a.change}`}</li>
                    ))}
                  </ul>
                )}
                {sessionMissing.length > 0 && (
                  <p className="sd-card-note is-warn">
                    선행조건 근거가 분석 산출물에 없는 항목 {sessionMissing.length}건 — 추정하지 않고
                    담당자 확인이 필요합니다.
                  </p>
                )}
              </article>
            )}

            {cautions.length > 0 && (
              <article className="sd-card is-note">
                <h4>실행 전에 알아둘 점</h4>
                <ul className="sd-notes">
                  {cautions.map((line, i) => (
                    <li key={i}>{line}</li>
                  ))}
                </ul>
              </article>
            )}
          </div>
        )}

        {tab === "flow" && <ScenarioFlowBoard scenarioId={scenarioId} showRunLink={false} />}

        {tab === "result" && (
          <div className="sd-cards">
            <article className="sd-card sd-verdict">
              <h4>
                <span className="sd-card-ic">
                  <ResultIcon />
                </span>
                성공·실패를 가르는 기준
              </h4>
              <dl className="sd-outcome">
                <div className="is-pass">
                  <dt>성공으로 보려면</dt>
                  <dd>{guide.successLooksLike}</dd>
                </div>
                <div className="is-fail">
                  <dt>실패로 봐야 하면</dt>
                  <dd>{guide.failureLooksLike}</dd>
                </div>
              </dl>
              {criteria.length > 0 && (
                <ul className="sd-criteria" data-testid="sd-verdict-criteria">
                  {criteria.map((c) => {
                    const seen = observedById.get(String(c.id));
                    const state = seen?.result || "pending";
                    return (
                      <li key={c.id} className={`sd-criterion is-${state}`}>
                        <span className="sd-criterion-state">
                          {seen ? CRITERION_KO[state] || state : "실행 전"}
                        </span>
                        <span className="sd-criterion-text">
                          <strong>{c.expected || c.check || c.id}</strong>
                          {seen?.observed ? <em>{seen.observed}</em> : null}
                        </span>
                      </li>
                    );
                  })}
                </ul>
              )}
              <p className="sd-card-note">
                화면이 열렸다는 것만으로 성공이 되지 않습니다. 위 기준과 실제 관측이 같은지 확인한 뒤
                담당자가 판정합니다.
              </p>
            </article>

            <article
              className={`sd-card sd-test-result is-${
                policyBlocked
                  ? "policy"
                  : runVerdict?.verdict === "expected_met"
                  ? "success"
                  : runVerdict?.verdict === "expected_not_met"
                    ? "failure"
                    : "unknown"
              }`}
              data-testid="sd-test-result"
            >
              <div className="sd-test-result-head">
                <div>
                  <span className="panel-kicker">테스트 결과</span>
                  <h4>
                    {policyBlocked
                      ? "실행 정책으로 제출하지 않음"
                      : runVerdict?.verdict === "expected_met"
                      ? "성공 기준 충족"
                      : runVerdict?.verdict === "expected_not_met"
                        ? "실패 기준 관측"
                        : latestRun
                          ? "판정 근거 부족"
                          : "아직 실행하지 않았습니다"}
                  </h4>
                </div>
                {latestRun && (
                  <span className="sd-test-result-time">{formatDateTime(latestRun.createdAt)}</span>
                )}
              </div>
              {latestRun && policyBlocked ? (
                <div className="sd-policy-guide" data-testid="sd-policy-guide">
                  <div>
                    <span>1</span>
                    <strong>무슨 일이 있었나요?</strong>
                    <p>{runDiagnosis?.problemSummary || "데이터 변경 단계가 실행되지 않아 결과를 관측하지 못했습니다."}</p>
                  </div>
                  <div>
                    <span>2</span>
                    <strong>왜 차단됐나요?</strong>
                    <p>{runDiagnosis?.causeSummary || "배치·자동 실행은 데이터 변경 동작을 기본 차단합니다."}</p>
                  </div>
                  <div>
                    <span>3</span>
                    <strong>무엇을 확인해야 하나요?</strong>
                    <p>{runDiagnosis?.retestCondition || "테스트 계정과 입력값을 확인한 뒤 이번 1회 실행을 명시적으로 승인해 주세요."}</p>
                  </div>
                </div>
              ) : latestRun ? (
                <div className="sd-test-result-grid">
                  <div>
                    <strong>핵심 요약</strong>
                    <p>
                      {runDiagnosis?.causeSummary ||
                        runVerdict?.verdictReason ||
                        runVerdict?.reason ||
                        humanizeObservation(latestRun.outcomeSummary || latestRun.observationSummary) ||
                        "관측 요약이 없습니다"}
                    </p>
                  </div>
                  <div>
                    <strong>판단 근거</strong>
                    <p>
                      {runDiagnosis?.evidence?.[0] ||
                        (runVerdict?.criteriaResults || runVerdict?.criteria || []).find(
                          (item) => item.observed,
                        )?.observed ||
                        "실행 이력에서 단계별 화면·요청·로그 근거를 확인하세요"}
                    </p>
                  </div>
                </div>
              ) : (
                <p className="sd-card-note">추천 입력과 실행환경을 확인한 뒤 테스트를 실행하세요.</p>
              )}
              {latestRun && (
                <div className="sd-test-result-actions">
                  <p>
                    {policyBlocked
                      ? "서비스 오류로 확정된 결과가 아닙니다. 아래 실행 준비에서 데이터 변경 1회를 승인하면 실제 결과를 다시 관측합니다."
                      : "단계·증적·원인·후속 조치는 실행 이력에서 집중해서 확인합니다."}
                  </p>
                  <div className="sd-test-result-cta">
                    {policyBlocked && <a className="primary-btn" href="#scenario-run-console">1회 실행 준비로 이동</a>}
                    <Link className={policyBlocked ? "ghost-btn" : "primary-btn"} href={`/runs/${encodeURIComponent(latestRun.runId)}`}>
                      실행 이력 상세 보기
                    </Link>
                  </div>
                </div>
              )}
              <small className="sd-guard">자동 관측 요약이며 최종 Pass/Fail은 담당자가 확정합니다.</small>
            </article>

            <ScenarioRunConsole scenarioId={scenarioId} detailMode="preflight" />
          </div>
        )}
      </div>

      <details className="scenario-detail-more" data-testid="scenario-technical-more">
        <summary>기술 상세 — 케이스 분석 · 단계 정의 (개발자용)</summary>
        <div className="scenario-detail-grid">
          <article className="detail-panel">
            <h3>시나리오 단계 정의</h3>
            <ol className="narrative-list">
              {narratives.map((s) => (
                <li key={s.order}>
                  <strong>
                    {s.order}. {s.title}
                  </strong>
                  <span>{s.detail}</span>
                </li>
              ))}
            </ol>
          </article>
          <article className="detail-panel">
            <h3>케이스 분석 · 식별자</h3>
            <table className="case-analysis-table">
              <tbody>
                {technicalRows.map((r) => (
                  <tr key={r.label}>
                    <th scope="row">{r.label}</th>
                    <td>
                      <code>{r.value}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </article>
        </div>
      </details>

      <p className="sd-guard">
        이 화면의 상태·요약은 실행에서 관측한 자료입니다. 최종 합격·불합격과 배포 판단은 담당자가
        승인 검토에서 확정합니다.
      </p>
    </div>
  );
}

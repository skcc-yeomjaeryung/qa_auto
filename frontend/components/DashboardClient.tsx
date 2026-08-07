"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "../lib/apiClient";
import { DEFAULT_GREETING, isDashboardGreeting, pickDashboardGreeting } from "../lib/dashboardGreetings";
import { formatDateTime } from "../lib/datetime";
import { getCurrentUserId, getCurrentUserName } from "../lib/user";

type DashboardProject = {
  projectId: string;
  name: string;
  description?: string | null;
  repositoryCount: number;
  scenarioCount: number;
  runCount: number;
  createdAt?: string | null;
  lastActivityAt?: string | null;
  latestCommitSha?: string | null;
  analysisChangeCount: number;
};

type WeeklyPoint = {
  date: string;
  total: number;
  expectedMet: number;
  rate?: number | null;
};

type RecentRun = {
  runId: string;
  scenarioId: string;
  scenarioName: string;
  projectId: string;
  projectName: string;
  status: string;
  outcomeKind?: string | null;
  outcomeSummary?: string | null;
  createdAt?: string | null;
  screenshotCount: number;
  snapshotCount: number;
  changedFromPrevious: boolean;
};

type DashboardSummary = {
  userId: string;
  projectCount: number;
  repositoryCount: number;
  scenarioCount: number;
  runCount: number;
  reviewCount: number;
  weeklyRate?: number | null;
  previousWeeklyRate?: number | null;
  weeklyDelta?: number | null;
  projects: DashboardProject[];
  weeklySeries: WeeklyPoint[];
  recentRuns: RecentRun[];
};

const ICON_BASE = "/goodfood-dash/icons";
const PROJECT_PAGE_SIZE = 2;

function projectInitial(name: string) {
  return name.trim().slice(0, 1).toUpperCase() || "?";
}

function runTone(run: RecentRun): "success" | "warning" | "failure" | "unknown" {
  const kind = (run.outcomeKind || "").toLowerCase();
  if (kind === "success") return "success";
  if (["be_error", "business_error", "fe_error", "failure"].includes(kind)) return "failure";
  if (run.status === "CANCELLED" || run.status === "AUTO_FAILED") return "warning";
  return "unknown";
}

function runLabel(run: RecentRun) {
  const tone = runTone(run);
  if (tone === "success") return "기대 결과 관측";
  if (tone === "failure") return "기대와 다르게 관측";
  if (tone === "warning") return "확인 필요";
  return "판정 자료 부족";
}

function DashboardSkeleton() {
  return (
    <div className="dash26-skeleton" aria-label="대시보드 데이터를 불러오는 중입니다">
      <div className="dash26-skeleton-line is-wide" />
      <div className="dash26-skeleton-line" />
      <div className="dash26-skeleton-grid">
        <div />
        <div />
      </div>
    </div>
  );
}

function WeeklyChart({ points }: { points: WeeklyPoint[] }) {
  const observed = points.filter((point) => point.rate != null);
  if (observed.length === 0) {
    return (
      <div className="dash26-chart-empty" data-testid="dashboard-weekly-empty">
        <strong>주간 실행 데이터가 없습니다.</strong>
        <span>테스트를 실행하면 일자별 기술 관측률이 표시됩니다.</span>
      </div>
    );
  }
  const width = 520;
  const height = 170;
  const left = 34;
  const right = 12;
  const top = 14;
  const bottom = 30;
  const graphWidth = width - left - right;
  const graphHeight = height - top - bottom;
  const xAt = (index: number) => left + (graphWidth * index) / Math.max(1, points.length - 1);
  const yAt = (rate: number) => top + graphHeight - (Math.max(0, Math.min(100, rate)) / 100) * graphHeight;
  const path = points
    .map((point, index) => (point.rate == null ? null : `${xAt(index)},${yAt(point.rate)}`))
    .filter(Boolean)
    .join(" ");
  return (
    <svg className="dash26-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="최근 7일 테스트 성공률">
      {[0, 25, 50, 75, 100].map((tick) => {
        const y = yAt(tick);
        return (
          <g key={tick}>
            <line x1={left} x2={width - right} y1={y} y2={y} className="dash26-grid-line" />
            <text x={left - 8} y={y + 4} textAnchor="end" className="dash26-axis-label">
              {tick}%
            </text>
          </g>
        );
      })}
      {path && <polyline points={path} className="dash26-chart-line" />}
      {points.map((point, index) => (
        <g key={point.date}>
          {point.rate != null && <circle cx={xAt(index)} cy={yAt(point.rate)} r="4" className="dash26-chart-point" />}
          <text x={xAt(index)} y={height - 7} textAnchor="middle" className="dash26-axis-label">
            {point.date.slice(5)}
          </text>
        </g>
      ))}
    </svg>
  );
}

export function DashboardClient() {
  const userId = getCurrentUserId();
  const userName = getCurrentUserName();
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [projectPage, setProjectPage] = useState(0);
  const [greeting, setGreeting] = useState<string>(DEFAULT_GREETING);

  useEffect(() => {
    const storageKey = `dashboard.greeting.${userId}`;
    const stored = window.sessionStorage.getItem(storageKey);
    if (stored && isDashboardGreeting(stored)) {
      setGreeting(stored);
      return;
    }
    const selected = pickDashboardGreeting();
    window.sessionStorage.setItem(storageKey, selected);
    setGreeting(selected);
  }, [userId]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiFetch(`/api/dashboard/summary?ownerUserId=${encodeURIComponent(userId)}`, {
        cache: "no-store",
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "대시보드 데이터를 불러오지 못했습니다");
      setSummary(body as DashboardSummary);
    } catch (caught) {
      setSummary(null);
      setError(caught instanceof Error ? caught.message : "대시보드 데이터를 불러오지 못했습니다");
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    void load();
  }, [load]);

  const pageCount = Math.max(1, Math.ceil((summary?.projects.length || 0) / PROJECT_PAGE_SIZE));
  const safePage = Math.min(projectPage, pageCount - 1);
  const visibleProjects = useMemo(
    () => summary?.projects.slice(safePage * PROJECT_PAGE_SIZE, safePage * PROJECT_PAGE_SIZE + PROJECT_PAGE_SIZE) || [],
    [summary, safePage],
  );

  const quickActions = [
    { label: "결과 검토", href: "/hitl", icon: "nav-document.svg", count: summary?.reviewCount, review: true },
    { label: "프로젝트 등록", href: "/projects", icon: "nav-buy.svg" },
    { label: "저장소 분석", href: "/analysis", icon: "nav-wallet.svg" },
    { label: "테스트 시나리오", href: "/scenarios", icon: "nav-chat.svg" },
  ];

  const stats = [
    { label: "프로젝트", value: summary?.projectCount, href: "/projects", icon: "nav-wallet.svg" },
    { label: "연결 저장소", value: summary?.repositoryCount, href: "/projects", icon: "nav-chart.svg" },
    { label: "테스트 시나리오", value: summary?.scenarioCount, href: "/scenarios", icon: "nav-document.svg" },
  ];

  return (
    <div className="dash26" data-testid="dashboard">
      <section className="dash26-welcome" data-testid="dashboard-hero">
        <div className="dash26-welcome-copy">
          <h1>{userName}님, {greeting}</h1>
          <p>
            검토를 기다리는 테스트 <Link href="/hitl">{summary?.reviewCount ?? "—"}건</Link>이 있어요.
          </p>
        </div>
        <img className="dash26-mascot" src="/dashboard/qa-robot.png" alt="테스트 자동화 도우미" />
      </section>

      {loading ? (
        <DashboardSkeleton />
      ) : error ? (
        <section className="dash26-state is-error" role="alert" data-testid="dashboard-error">
          <strong>대시보드 데이터를 불러오지 못했습니다.</strong>
          <span>{error}</span>
          <button type="button" onClick={() => void load()}>
            다시 시도
          </button>
        </section>
      ) : summary ? (
        <>
          <section className="dash26-projects" data-testid="dashboard-my-projects">
            <header className="dash26-section-head">
              <div>
                <h2>내 프로젝트</h2>
                <p>할당된 프로젝트를 선택하면 분석·테스트 화면으로 바로 이동합니다.</p>
              </div>
              <div className="dash26-quick" aria-label="빠른 작업">
                <span className="dash26-quick-label">빠른 작업</span>
                {quickActions.map((action) => (
                  <Link
                    href={action.href}
                    key={action.label}
                    className={action.review && (action.count ?? 0) > 0 ? "is-review" : ""}
                    aria-label={action.review ? `결과 검토${action.count ? ` ${action.count}건` : " 대기 없음"}` : action.label}
                  >
                    <img src={`${ICON_BASE}/${action.icon}`} alt="" />
                    {action.label}
                    {action.count != null && action.count > 0 && <em>{action.count}</em>}
                  </Link>
                ))}
              </div>
            </header>

            {summary.projects.length === 0 ? (
              <div className="dash26-state" data-testid="dashboard-empty-projects">
                <strong>할당된 프로젝트가 없습니다.</strong>
                <span>프로젝트를 등록하면 저장소 분석과 테스트 시나리오 생성이 열립니다.</span>
                <Link href="/projects">프로젝트 등록</Link>
              </div>
            ) : (
              <div className="dash26-project-grid">
                {visibleProjects.map((project, index) => {
                  const stages = [true, project.repositoryCount > 0, project.scenarioCount > 0, project.runCount > 0];
                  return (
                    <Link
                      href={`/analysis?projectId=${encodeURIComponent(project.projectId)}`}
                      className="dash26-project-card"
                      key={project.projectId}
                      data-testid={`dashboard-project-${project.projectId}`}
                    >
                      <img className="dash26-project-art" src="/dashboard/project-folder.svg" alt="" aria-hidden="true" />
                      <div className="dash26-project-top">
                        <span className="dash26-project-avatar">{projectInitial(project.name)}</span>
                        {safePage === 0 && index === 0 && <em className="dash26-recent-badge">최근 작업</em>}
                      </div>
                      <h3>{project.name}</h3>
                      <code>{project.projectId}</code>
                      <p>
                        저장소 {project.repositoryCount}곳 · 시나리오 {project.scenarioCount}건 · 실행 {project.runCount}건
                      </p>
                      <span>최근 작업 {formatDateTime(project.lastActivityAt)}</span>
                      {project.analysisChangeCount > 0 && (
                        <span className="dash26-change-badge">분석 변경 {project.analysisChangeCount}건</span>
                      )}
                      <div className="dash26-stage-dots" aria-label="프로젝트 진행 상태">
                        {stages.map((complete, stageIndex) => (
                          <i key={stageIndex} className={complete ? "is-complete" : ""} />
                        ))}
                      </div>
                      <strong className="dash26-project-go">분석·테스트 바로가기 →</strong>
                    </Link>
                  );
                })}
              </div>
            )}

            {summary.projects.length > PROJECT_PAGE_SIZE && (
              <div className="dash26-pager">
                <button type="button" disabled={safePage === 0} onClick={() => setProjectPage((page) => Math.max(0, page - 1))}>
                  이전
                </button>
                <span>{safePage + 1} / {pageCount}</span>
                <button type="button" disabled={safePage >= pageCount - 1} onClick={() => setProjectPage((page) => Math.min(pageCount - 1, page + 1))}>
                  다음
                </button>
              </div>
            )}
          </section>

          <section className="dash26-service" data-testid="dashboard-service-status">
            <h2>서비스 현황</h2>
            {stats.map((stat) => (
              <Link href={stat.href} key={stat.label}>
                <img src={`${ICON_BASE}/${stat.icon}`} alt="" />
                <span>{stat.label}</span>
                <strong>{stat.value ?? "—"}</strong>
              </Link>
            ))}
          </section>

          <div className="dash26-bottom">
            <section className="dash26-rate" data-testid="dashboard-weekly-rate">
              <header>
                <h2>이번 주 테스트 성공률</h2>
                <span>최근 7일 · 기술 관측 기준</span>
              </header>
              <div className="dash26-rate-body">
                <div className="dash26-rate-number">
                  <strong>{summary.weeklyRate == null ? "—" : summary.weeklyRate.toFixed(1)}{summary.weeklyRate == null ? "" : "%"}</strong>
                  <span>기대 결과 관측률</span>
                  {summary.weeklyDelta != null && (
                    <em className={summary.weeklyDelta >= 0 ? "is-up" : "is-down"}>
                      {summary.weeklyDelta >= 0 ? "▲" : "▼"} {Math.abs(summary.weeklyDelta).toFixed(1)}%p
                      <small>지난주 대비</small>
                    </em>
                  )}
                </div>
                <WeeklyChart points={summary.weeklySeries} />
              </div>
            </section>

            <section className="dash26-runs" data-testid="dashboard-recent-runs">
              <header>
                <h2>최근 테스트 실행 결과</h2>
                <Link href="/runs">전체 보기</Link>
              </header>
              {summary.recentRuns.length === 0 ? (
                <div className="dash26-chart-empty">
                  <strong>최근 실행 결과가 없습니다.</strong>
                  <span>테스트 시나리오에서 첫 실행을 시작하세요.</span>
                </div>
              ) : (
                <ul>
                  {summary.recentRuns.map((run) => {
                    const tone = runTone(run);
                    return (
                      <li key={run.runId}>
                        <span className={`dash26-run-status is-${tone}`}>{runLabel(run)}</span>
                        <div>
                          <strong>{run.projectName}</strong>
                          <span>{run.scenarioName}</span>
                        </div>
                        {run.changedFromPrevious && <em className="dash26-change-badge">결과 변경</em>}
                        <time>{formatDateTime(run.createdAt)}</time>
                        <span className="dash26-evidence-count">증적 {run.screenshotCount + run.snapshotCount}건</span>
                        <Link href={`/runs/${run.runId}`} aria-label={`${run.runId} 실행 상세`}>
                          ›
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
          </div>
        </>
      ) : null}

      <p className="dash26-footnote">자동 실행 결과는 기술 관측 자료이며 최종 Pass/Fail·승인은 HITL에서 확정합니다.</p>
    </div>
  );
}

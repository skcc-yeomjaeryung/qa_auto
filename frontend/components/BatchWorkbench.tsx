"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "../lib/apiClient";
import { formatDateTime } from "../lib/datetime";
import { getCurrentUserId } from "../lib/user";
import { Breadcrumbs } from "./Breadcrumbs";
import { PageShell, PageStickyFooter } from "./PageShell";
import { ProgressBarType1, type ProgressStatus } from "./ProgressBar";
import { Button } from "./ui";
import { actionToastId, showActionToast } from "../lib/actionToast";

type Scenario = {
  scenarioId: string;
  projectId?: string | null;
  name?: string;
  version?: string;
};

type Profile = {
  profileId: string;
  scenarioId: string;
  name: string;
  version: string;
  status: string;
  caseCount: number;
};

type BatchCase = {
  caseId: string;
  scenarioId: string;
  category: string;
  status: string;
  flaky: boolean;
  skipReason?: string | null;
  finalRunId?: string | null;
};

type Batch = {
  batchId: string;
  projectId: string;
  name: string;
  status: string;
  totalBudget: number;
  concurrency: number;
  categoryCounts: Record<string, number>;
  cases: BatchCase[];
  createdAt: string;
};

type BatchSummary = {
  batchId: string;
  status: string;
  total: number;
  pending: number;
  running: number;
  completed: number;
  failed: number;
  skipped: number;
  cancelled: number;
  reviewRequired: number;
  flaky: number;
  evidenceReady: number;
  progressPercent: number;
  exceptions: Array<{
    caseId: string;
    scenarioId: string;
    category: string;
    status: string;
    kind: string;
    detail?: string | null;
    runId?: string | null;
    flaky: boolean;
  }>;
};

const ACTIVE = new Set(["RUNNING", "PAUSED"]);

function progressTone(status: string): ProgressStatus {
  if (status === "COMPLETED") return "complete";
  if (status === "COMPLETED_WITH_FAILURES") return "warning";
  if (status === "CANCELLED") return "error";
  if (status === "RUNNING") return "progressing";
  return "empty";
}

function batchStatusKo(status: string): string {
  return (
    {
      DRAFT: "초안",
      READY: "실행 준비",
      RUNNING: "실행 중",
      PAUSED: "일시정지",
      COMPLETED: "기술 실행 완료",
      COMPLETED_WITH_FAILURES: "예외 포함 완료",
      CANCELLED: "취소됨",
    }[status] ?? status
  );
}

export function BatchWorkbench() {
  const userId = useMemo(() => getCurrentUserId(), []);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [profiles, setProfiles] = useState<Record<string, Profile[]>>({});
  const [batches, setBatches] = useState<Batch[]>([]);
  const [selectedScenarios, setSelectedScenarios] = useState<Set<string>>(new Set());
  const [selectedProfiles, setSelectedProfiles] = useState<Record<string, string>>({});
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);
  const [summary, setSummary] = useState<BatchSummary | null>(null);
  const [budget, setBudget] = useState(20);
  const [concurrency, setConcurrency] = useState(2);
  const [rateLimit, setRateLimit] = useState(2);
  const [infraRetries, setInfraRetries] = useState(1);
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [projectRes, scenarioRes, batchRes] = await Promise.all([
      apiFetch(`/api/projects?ownerUserId=${encodeURIComponent(userId)}`, { cache: "no-store" }),
      apiFetch("/api/scenarios", { cache: "no-store" }),
      apiFetch("/api/batches", { cache: "no-store" }),
    ]);
    if (!projectRes.ok || !scenarioRes.ok || !batchRes.ok) {
      throw new Error("배치 실행에 필요한 실데이터를 불러오지 못했습니다");
    }
    const projectIds = new Set(((await projectRes.json()) as Array<{ id: string }>).map((item) => item.id));
    const owned = ((await scenarioRes.json()) as Scenario[]).filter(
      (scenario) => scenario.projectId && projectIds.has(scenario.projectId),
    );
    const nextProfiles: Record<string, Profile[]> = {};
    let failedProfileCount = 0;
    for (const scenario of owned) {
      try {
        const response = await apiFetch(`/api/scenarios/${scenario.scenarioId}/input-profiles`, {
          cache: "no-store",
        });
        if (!response.ok) throw new Error(`${scenario.scenarioId} 입력 Profile 조회 실패`);
        const rows = (await response.json()) as Profile[];
        nextProfiles[scenario.scenarioId] = rows.filter((profile) => profile.status === "APPROVED");
      } catch {
        nextProfiles[scenario.scenarioId] = [];
        failedProfileCount += 1;
      }
    }
    if (failedProfileCount > 0) {
      setMessage(`입력 Profile ${failedProfileCount}건을 불러오지 못했습니다. 새로고침으로 다시 확인하세요.`);
    }
    setScenarios(owned);
    setProfiles(nextProfiles);
    const nextBatches = (await batchRes.json()) as Batch[];
    setBatches(nextBatches);
    setSelectedBatchId((current) => current ?? nextBatches[0]?.batchId ?? null);
  }, [userId]);

  const loadSummary = useCallback(async (batchId: string) => {
    const response = await apiFetch(`/api/batches/${batchId}/summary`, { cache: "no-store" });
    if (!response.ok) throw new Error("배치 요약을 불러오지 못했습니다");
    setSummary((await response.json()) as BatchSummary);
  }, []);

  useEffect(() => {
    load()
      .catch((error: Error) => setMessage(error.message))
      .finally(() => setLoading(false));
  }, [load]);

  useEffect(() => {
    if (!selectedBatchId) {
      setSummary(null);
      return;
    }
    void loadSummary(selectedBatchId).catch((error: Error) => setMessage(error.message));
  }, [selectedBatchId, loadSummary]);

  useEffect(() => {
    if (!selectedBatchId || !summary || !ACTIVE.has(summary.status)) return;
    const timer = window.setInterval(() => {
      void Promise.all([loadSummary(selectedBatchId), load()]).catch((error: Error) =>
        setMessage(error.message),
      );
    }, 1000);
    return () => window.clearInterval(timer);
  }, [selectedBatchId, summary?.status, loadSummary, load]);

  const executableScenarios = scenarios.filter((scenario) => (profiles[scenario.scenarioId] ?? []).length > 0);

  function toggleScenario(scenarioId: string, checked: boolean) {
    setSelectedScenarios((current) => {
      const next = new Set(current);
      if (checked) next.add(scenarioId);
      else next.delete(scenarioId);
      return next;
    });
    if (checked && !selectedProfiles[scenarioId]) {
      const first = profiles[scenarioId]?.[0];
      if (first) setSelectedProfiles((current) => ({ ...current, [scenarioId]: first.profileId }));
    }
  }

  async function createBatch() {
    const pins = Array.from(selectedScenarios)
      .map((scenarioId) => ({ scenarioId, inputProfileId: selectedProfiles[scenarioId] }))
      .filter((pin) => pin.inputProfileId);
    if (pins.length === 0) {
      setMessage("승인된 Input Profile이 있는 시나리오를 선택하세요.");
      return;
    }
    const firstScenario = scenarios.find((scenario) => scenario.scenarioId === pins[0].scenarioId);
    if (!firstScenario?.projectId || pins.some((pin) => scenarios.find((s) => s.scenarioId === pin.scenarioId)?.projectId !== firstScenario.projectId)) {
      setMessage("한 배치에는 같은 프로젝트의 시나리오만 선택할 수 있습니다.");
      return;
    }
    setBusyAction("create");
    try {
      const response = await apiFetch("/api/batches", {
        method: "POST",
        body: JSON.stringify({
          projectId: firstScenario.projectId,
          name: `${firstScenario.name || firstScenario.scenarioId} 자동 배치`,
          scenarioProfiles: pins,
          totalBudget: budget,
          concurrency,
          policy: {
            unresolvedAction: "skip_notify",
            destructiveAction: "exclude",
            lowConfidenceAction: "review_required",
            infraRetryCount: infraRetries,
            productRetryCount: 0,
            projectRateLimit: rateLimit,
            resourceLockFields: ["customerId", "accountId", "resourceId"],
          },
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "배치 생성 실패");
      setSelectedBatchId(body.batchId);
      setMessage(`배치 ${body.batchId}를 생성했습니다. 버전과 정책이 고정되었습니다.`);
      await load();
      await loadSummary(body.batchId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "배치 생성 실패");
    } finally {
      setBusyAction(null);
    }
  }

  async function transition(action: "start" | "pause" | "resume" | "cancel") {
    if (!selectedBatchId) return;
    const actionLabels = { start: "실행", pause: "일시정지", resume: "재개", cancel: "취소" } as const;
    const batchName = batches.find((batch) => batch.batchId === selectedBatchId)?.name || selectedBatchId;
    const toastId = actionToastId(`batch-${action}`, selectedBatchId);
    showActionToast({
      id: toastId,
      title: `배치 ${actionLabels[action]}`,
      message: `${batchName} 배치 ${actionLabels[action]} 요청을 시작했습니다.`,
      tone: "progress",
    });
    setBusyAction(action);
    try {
      const response = await apiFetch(`/api/batches/${selectedBatchId}/${action}`, { method: "POST" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "배치 상태 변경 실패");
      setMessage(`${body.batchId} · ${batchStatusKo(body.status)}`);
      showActionToast({
        id: toastId,
        title: `배치 ${actionLabels[action]} 요청 완료`,
        message: `${batchName} · ${batchStatusKo(body.status)}`,
        tone: "success",
      });
      await load();
      await loadSummary(selectedBatchId);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "배치 상태 변경 실패";
      setMessage(errorMessage);
      showActionToast({ id: toastId, title: `배치 ${actionLabels[action]} 실패`, message: errorMessage, tone: "error" });
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <PageShell
      testId="batch-workbench"
      className="batch-page"
      header={
        <div className="content-header">
          <div>
            <Breadcrumbs trail={[{ label: "콘솔", href: "/" }, { label: "테스트 시나리오", href: "/scenarios" }, { label: "배치 실행" }]} />
            <h2>승인 Profile 기반 배치 실행</h2>
            <p className="muted" style={{ marginTop: 6 }}>
              시나리오·입력 버전을 고정하고 프로젝트별 제한과 리소스 잠금을 적용합니다. 완료는 기술 실행 완료이며 HITL 합격이 아닙니다.
            </p>
          </div>
        </div>
      }
      footer={
        <PageStickyFooter
          note="인프라 오류만 정책 횟수만큼 재시도하며 최초 실패와 flaky 이력을 보존합니다."
          actions={
            <>
              <Link href="/scenarios" className="ghost-btn">시나리오로 돌아가기</Link>
              <Button variant="primary" busy={busyAction === "create"} onClick={() => void createBatch()}>
                배치 정의 생성
              </Button>
            </>
          }
        />
      }
    >
      {message && <div className="connect-banner is-warn">{message}</div>}
      {loading ? (
        <div className="batch-empty">배치 실데이터를 불러오는 중입니다…</div>
      ) : (
        <div className="batch-layout">
          <section className="batch-config-card">
            <div className="batch-card-head">
              <div><p className="panel-kicker">BATCH DEFINITION</p><h3>실행 대상과 안전 정책</h3></div>
              <span className="status-badge status-info">{userId}</span>
            </div>
            {executableScenarios.length === 0 ? (
              <div className="batch-empty">승인된 Input Profile이 없습니다. 시나리오 상세에서 입력 Profile을 먼저 승인하세요.</div>
            ) : (
              <div className="batch-scenario-list">
                {executableScenarios.map((scenario) => (
                  <label key={scenario.scenarioId} className="batch-scenario-row">
                    <input
                      type="checkbox"
                      checked={selectedScenarios.has(scenario.scenarioId)}
                      onChange={(event) => toggleScenario(scenario.scenarioId, event.target.checked)}
                    />
                    <span><strong>{scenario.name || scenario.scenarioId}</strong><em>{scenario.scenarioId} · v{scenario.version || "1"}</em></span>
                    <select
                      value={selectedProfiles[scenario.scenarioId] || profiles[scenario.scenarioId]?.[0]?.profileId || ""}
                      onChange={(event) => setSelectedProfiles((current) => ({ ...current, [scenario.scenarioId]: event.target.value }))}
                      onClick={(event) => event.stopPropagation()}
                    >
                      {(profiles[scenario.scenarioId] ?? []).map((profile) => (
                        <option key={profile.profileId} value={profile.profileId}>{profile.name || profile.profileId} · v{profile.version} · {profile.caseCount} cases</option>
                      ))}
                    </select>
                  </label>
                ))}
              </div>
            )}
            <div className="batch-policy-grid">
              <label><span>총 실행 예산</span><input type="number" min={1} max={200} value={budget} onChange={(e) => setBudget(Number(e.target.value))} /></label>
              <label><span>Worker 동시성</span><input type="number" min={1} max={8} value={concurrency} onChange={(e) => setConcurrency(Number(e.target.value))} /></label>
              <label><span>프로젝트 Rate Limit</span><input type="number" min={1} max={8} value={rateLimit} onChange={(e) => setRateLimit(Number(e.target.value))} /></label>
              <label><span>인프라 재시도</span><input type="number" min={0} max={3} value={infraRetries} onChange={(e) => setInfraRetries(Number(e.target.value))} /></label>
            </div>
            <p className="batch-policy-note">unresolved: skip+notify · destructive: 제외 · low confidence: 검토 필요 · 제품 실패: 자동 재시도 없음</p>
          </section>

          <section className="batch-monitor-card">
            <div className="batch-card-head">
              <div><p className="panel-kicker">BATCH MONITOR</p><h3>실행 상태와 예외 우선 검토</h3></div>
              <select value={selectedBatchId || ""} onChange={(e) => setSelectedBatchId(e.target.value || null)}>
                {batches.length === 0 && <option value="">생성된 배치 없음</option>}
                {batches.map((batch) => <option key={batch.batchId} value={batch.batchId}>{batch.name} · {batchStatusKo(batch.status)}</option>)}
              </select>
            </div>
            {!summary ? (
              <div className="batch-empty">배치를 생성하거나 선택하면 실행 상태가 표시됩니다.</div>
            ) : (
              <>
                <ProgressBarType1 percent={summary.progressPercent} label={`${batchStatusKo(summary.status)} · ${summary.total} cases`} status={progressTone(summary.status)} testId="batch-progress-type1" />
                <div className="batch-metrics">
                  <span><strong>{summary.completed}</strong> 완료</span><span><strong>{summary.failed}</strong> 실패</span><span><strong>{summary.reviewRequired}</strong> 검토</span><span><strong>{summary.flaky}</strong> flaky</span><span><strong>{summary.evidenceReady}</strong> 증적</span>
                </div>
                <div className="batch-actions">
                  {summary.status === "READY" && <Button size="sm" busy={busyAction === "start"} onClick={() => void transition("start")}>실행 시작</Button>}
                  {summary.status === "RUNNING" && <Button size="sm" variant="secondary" busy={busyAction === "pause"} onClick={() => void transition("pause")}>일시정지</Button>}
                  {summary.status === "PAUSED" && <Button size="sm" busy={busyAction === "resume"} onClick={() => void transition("resume")}>재개</Button>}
                  {ACTIVE.has(summary.status) && (
                    <Button size="sm" variant="secondary" busy={busyAction === "cancel"} onClick={() => void transition("cancel")} data-testid="batch-cancel">배치 취소</Button>
                  )}
                </div>
                <div className="batch-exceptions">
                  <h4>예외 우선 목록</h4>
                  {summary.exceptions.length === 0 ? <p className="muted">현재 예외가 없습니다.</p> : summary.exceptions.map((item) => (
                    <div key={item.caseId} className="batch-exception-row">
                      <span className={`status-badge ${item.flaky ? "status-warn" : "status-info"}`}>{item.flaky ? "flaky" : item.kind}</span>
                      <span><strong>{item.scenarioId}</strong><em>{item.category} · {item.detail || item.status}</em></span>
                      {item.runId ? <Link href={`/runs/${item.runId}`}>실행 증적</Link> : <span className="muted">실행 없음</span>}
                    </div>
                  ))}
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </PageShell>
  );
}

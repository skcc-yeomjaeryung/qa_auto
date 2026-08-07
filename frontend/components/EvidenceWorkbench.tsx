"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { lsGet, lsSet } from "../lib/localStore";
import { PageShell, PageStickyFooter } from "./PageShell";
import { Breadcrumbs } from "./Breadcrumbs";
import { ValueSkeleton } from "./LoadingStates";
import { CommonDataTable } from "./CommonDataTable";
import { matchesQuery, ScreenSearch } from "./ScreenSearch";
import {
  TableBulkDeleteForm,
  confirmBulkDelete,
} from "./TableBulkDeleteForm";
import { deleteRuns, useTableSelection } from "../lib/tableSelection";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";

type RunRow = {
  runId: string;
  scenarioId: string;
  status: string;
  screenshotCount?: number;
  snapshotCount?: number;
  outcomeSummary?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
};

export function EvidenceWorkbench() {
  const router = useRouter();
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/runs`, { cache: "no-store" });
      if (!res.ok) throw new Error("실행 이력을 불러오지 못했습니다");
      const list = (await res.json()) as RunRow[];
      setRuns(list);
      lsSet("history.evidence", {
        at: new Date().toISOString(),
        count: list.length,
        screenshots: list.reduce((a, r) => a + (r.screenshotCount || 0), 0),
        snapshots: list.reduce((a, r) => a + (r.snapshotCount || 0), 0),
      });
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "로드 실패");
      const cached = lsGet<{ items?: RunRow[] }>("history.runs", {});
      if (cached.items?.length) setRuns(cached.items as RunRow[]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /** 화면 내 검색 — 실행 ID·시나리오·상태로 좁힌다 */
  const visibleRuns = useMemo(
    () => runs.filter((r) => matchesQuery(query, r.runId, r.scenarioId, statusKo(r.status), r.outcomeSummary)),
    [runs, query],
  );

  const { checked, setChecked, selectedIds, clear } = useTableSelection(
    visibleRuns.map((r) => r.runId),
  );

  async function removeRuns(ids: string[]) {
    if (!confirmBulkDelete("증적 실행", ids.length)) return;
    setBusy(true);
    try {
      setMessage(await deleteRuns(ids));
      clear();
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "삭제 실패");
    } finally {
      setBusy(false);
    }
  }

  const totals = useMemo(() => {
    return {
      runs: runs.length,
      screenshots: runs.reduce((a, r) => a + (r.screenshotCount || 0), 0),
      snapshots: runs.reduce((a, r) => a + (r.snapshotCount || 0), 0),
    };
  }, [runs]);

  return (
    <PageShell
      header={
        <div className="content-header">
          <div>
            <Breadcrumbs trail={[{ label: "콘솔", href: "/" }, { label: "증적" }]} />
            <h2>증적</h2>
            <p className="muted" style={{ marginTop: 6 }}>
              실행별 스크린샷·스냅샷 수량을 정량으로 표시합니다. Pass/Fail는 HITL입니다.
            </p>
          </div>
        </div>
      }
      footer={
        <PageStickyFooter
          note="관측 수량만 제공합니다."
          actions={
            <Link className="ghost-btn" href="/runs">
              실행 이력
            </Link>
          }
        />
      }
    >
      {message && <div className="connect-banner is-warn">{message}</div>}
      <div className="kpi-strip" data-testid="evidence-kpi">
        <div>
          <strong>{loading ? <ValueSkeleton width={40} /> : totals.runs}</strong>
          <span>실행</span>
        </div>
        <div>
          <strong>{loading ? <ValueSkeleton width={40} /> : totals.screenshots}</strong>
          <span>스크린샷</span>
        </div>
        <div>
          <strong>{loading ? <ValueSkeleton width={40} /> : totals.snapshots}</strong>
          <span>스냅샷</span>
        </div>
      </div>
      <CommonDataTable
        rows={visibleRuns}
        totalCount={runs.length}
        toolbar={
          <>
            <ScreenSearch
              value={query}
              onChange={setQuery}
              placeholder="실행 ID · 시나리오 ID · 상태"
              testId="evidence-search"
              hint="증적이 남은 실행을 ID·상태로 찾습니다"
            />
            <TableBulkDeleteForm
              embedded
              noun="증적 실행"
              totalCount={visibleRuns.length}
              selectedCount={selectedIds.length}
              busy={busy}
              onDelete={() => void removeRuns(selectedIds)}
              testId="evidence-bulk-form"
            />
          </>
        }
        rowKey={(row) => row.runId}
        columns={[
          { key: "runId", label: "실행 ID", cell: (row) => <strong className="id-link">{row.runId}</strong>, sortValue: (row) => row.runId },
          { key: "scenarioId", label: "시나리오 ID", cell: (row) => <span className="saas-cell-mono">{row.scenarioId}</span>, sortValue: (row) => row.scenarioId },
          { key: "status", label: "상태", cell: (row) => <span className="status-badge status-info">{statusKo(row.status)}</span>, sortValue: (row) => statusKo(row.status) },
          { key: "screenshots", label: "스크린샷", cell: (row) => row.screenshotCount ?? 0, sortValue: (row) => row.screenshotCount ?? 0 },
          { key: "snapshots", label: "스냅샷", cell: (row) => row.snapshotCount ?? 0, sortValue: (row) => row.snapshotCount ?? 0 },
        ]}
        timestamps={{ createdAt: (row) => row.createdAt, updatedAt: (row) => row.updatedAt }}
        actions={(row) => (
          <>
            <Link className="proc-btn" href={`/runs/${row.runId}`}>증적 보기</Link>
            <button type="button" className="proc-btn proc-btn-danger" onClick={() => void removeRuns([row.runId])}>삭제</button>
          </>
        )}
        selection={{ selected: checked, onChange: setChecked, label: (row) => `${row.runId} 증적 선택` }}
        loading={loading}
        emptyText={query ? `검색어 「${query}」와 맞는 증적이 없습니다.` : "증적으로 남은 실행이 없습니다. 테스트를 실행하면 스크린샷·스냅샷이 쌓입니다."}
        loadingText="증적 목록을 불러오는 중입니다"
        onRowClick={(row) => router.push(`/runs/${row.runId}`)}
        testId="evidence-table"
      />
    </PageShell>
  );
}

const RUN_STATUS_KO: Record<string, string> = {
  WAITING_FOR_REVIEW: "검토 대기",
  AUTO_FAILED: "자동 실패",
  RUNNING: "실행 중",
  QUEUED: "대기",
  CANCELLED: "취소",
  COMPLETED: "실행 완료",
};

function statusKo(status: string) {
  return RUN_STATUS_KO[status] ?? status;
}

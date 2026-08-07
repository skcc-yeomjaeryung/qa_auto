"use client";

import { useCallback, useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";

/**
 * 목록 화면 공통 선택 상태.
 *
 * WORK(분석·시나리오) 테이블과 OTHERS(실행 이력·증적·승인 검토) 테이블이
 * 같은 선택·일괄삭제 UX를 쓰도록 한 곳에서 관리한다.
 */
export function useTableSelection(visibleIds: string[]) {
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const selectedIds = useMemo(
    () => visibleIds.filter((id) => checked.has(id)),
    [visibleIds, checked],
  );
  const toggle = useCallback((id: string, on: boolean) => {
    setChecked((prev) => {
      const next = new Set(prev);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);
  const clear = useCallback(() => setChecked(new Set()), []);
  return { checked, setChecked, selectedIds, toggle, clear };
}

/** 실행 이력 일괄 삭제 — 증적 파일은 보존하고 목록에서만 제거한다 */
export async function deleteRuns(runIds: string[]): Promise<string> {
  const res = await fetch(`${API}/api/runs/bulk-delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ runIds }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || "실행 이력 삭제에 실패했습니다");
  return String(body.message || `실행 이력 ${runIds.length}건을 삭제했습니다.`);
}

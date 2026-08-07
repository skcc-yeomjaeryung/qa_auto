"use client";

import type { ReactNode } from "react";
import { BusyIndicator } from "./ProgressBar";

/**
 * 목록/카드가 불러오는 중임을 사용자가 식별할 수 있게 한다.
 * 빈 결과와 로딩 중을 같은 화면으로 보여주면 사용자는 "없다"로 오해한다.
 */

/** 표 본문 자리를 지키는 스켈레톤 행 */
export function TableSkeletonRows({
  rows = 4,
  cols,
  testId = "table-skeleton",
}: {
  rows?: number;
  cols: number;
  testId?: string;
}) {
  return (
    <>
      {Array.from({ length: rows }).map((_, r) => (
        <tr className="skeleton-row" key={r} data-testid={r === 0 ? testId : undefined} aria-hidden="true">
          {Array.from({ length: cols }).map((_, c) => (
            <td key={c}>
              <span className="skeleton-bar" style={{ width: `${55 + ((r * 7 + c * 13) % 40)}%` }} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

/** 표 로딩/빈 상태를 한 곳에서 판단한다 */
export function TableStateRow({
  loading,
  isEmpty,
  cols,
  emptyText,
  loadingText = "목록을 불러오는 중입니다",
  skeletonRows = 4,
}: {
  loading: boolean;
  isEmpty: boolean;
  cols: number;
  emptyText: ReactNode;
  loadingText?: string;
  skeletonRows?: number;
}) {
  if (loading) {
    return (
      <>
        <tr className="loading-hint-row">
          <td colSpan={cols}>
            <span className="loading-hint">
              <BusyIndicator label={loadingText} />
              {loadingText}
            </span>
          </td>
        </tr>
        <TableSkeletonRows rows={skeletonRows} cols={cols} />
      </>
    );
  }
  if (isEmpty) {
    return (
      <tr>
        <td colSpan={cols} className="muted empty-cell" data-testid="table-empty">
          {emptyText}
        </td>
      </tr>
    );
  }
  return null;
}

/** 카드/패널 로딩 표시 */
export function PanelLoading({
  label = "불러오는 중입니다",
  testId = "panel-loading",
}: {
  label?: string;
  testId?: string;
}) {
  return (
    <div className="panel-loading anim-fade-in" data-testid={testId}>
      <BusyIndicator label={label} size={16} />
      <span>{label}</span>
    </div>
  );
}

/** KPI 숫자 자리 스켈레톤 */
export function ValueSkeleton({ width = 56 }: { width?: number }) {
  return <span className="skeleton-bar is-value" style={{ width }} aria-hidden="true" />;
}

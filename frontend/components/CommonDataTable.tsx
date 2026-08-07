"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { formatDateTime } from "../lib/datetime";
import { TableStateRow } from "./LoadingStates";
import { TableRowCheckbox, TableSelectAllCheckbox } from "./TableBulkDeleteForm";

const PAGE_SIZE = 10;

export type TableSortValue = string | number | boolean | null | undefined;

export type CommonTableColumn<Row> = {
  key: string;
  label: string;
  cell: (row: Row) => ReactNode;
  sortValue?: (row: Row) => TableSortValue;
};

type CommonTableSelection<Row> = {
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  label: (row: Row) => string;
};

type CommonTableTimestamps<Row> = {
  createdAt: (row: Row) => string | number | Date | null | undefined;
  updatedAt: (row: Row) => string | number | Date | null | undefined;
};

type SortState = { key: string; direction: "asc" | "desc" };

function comparable(value: TableSortValue): string | number {
  if (typeof value === "number") return Number.isNaN(value) ? Number.NEGATIVE_INFINITY : value;
  if (typeof value === "boolean") return value ? 1 : 0;
  return String(value ?? "").trim();
}

function compareValues(a: TableSortValue, b: TableSortValue): number {
  const left = comparable(a);
  const right = comparable(b);
  if (typeof left === "number" && typeof right === "number") return left - right;
  return String(left).localeCompare(String(right), "ko", {
    numeric: true,
    sensitivity: "base",
  });
}

function timestampValue(value: string | number | Date | null | undefined): number {
  if (value === null || value === undefined || value === "") return Number.NEGATIVE_INFINITY;
  const time = value instanceof Date ? value.getTime() : new Date(value).getTime();
  return Number.isNaN(time) ? Number.NEGATIVE_INFINITY : time;
}

function visiblePageNumbers(page: number, pageCount: number): number[] {
  const start = Math.max(1, Math.min(page - 2, pageCount - 4));
  const end = Math.min(pageCount, Math.max(page + 2, 5));
  return Array.from({ length: end - start + 1 }, (_, index) => start + index);
}

/**
 * 메뉴 목록 화면의 단일 테이블 계약.
 * 번호·정렬·등록/수정 일시·10건 페이징·선택·프로세스 열을 이 컴포넌트만 소유한다.
 */
export function CommonDataTable<Row>({
  rows,
  rowKey,
  columns,
  timestamps,
  totalCount,
  filters,
  toolbar,
  selection,
  actions,
  loading = false,
  emptyText,
  loadingText,
  testId = "common-data-table",
  onRowClick,
  rowTestId,
  rowClassName,
}: {
  rows: Row[];
  rowKey: (row: Row) => string;
  columns: CommonTableColumn<Row>[];
  timestamps: CommonTableTimestamps<Row>;
  totalCount?: number;
  filters?: ReactNode;
  toolbar?: ReactNode;
  selection?: CommonTableSelection<Row>;
  actions?: (row: Row) => ReactNode;
  loading?: boolean;
  emptyText: string;
  loadingText: string;
  testId?: string;
  onRowClick?: (row: Row) => void;
  rowTestId?: (row: Row) => string;
  rowClassName?: (row: Row) => string;
}) {
  // 공통 목록은 처음부터 등록·수정 시각의 최신순으로 보여준다.
  // ISO timestamp에는 시·분·초가 포함되므로 같은 날짜도 실제 시각으로 정렬된다.
  const [sort, setSort] = useState<SortState>({ key: "__timestamps", direction: "desc" });
  const [page, setPage] = useState(1);
  const [columnWidths, setColumnWidths] = useState<Record<string, number>>({});
  const [tableViewportWidth, setTableViewportWidth] = useState(0);
  const resizeRef = useRef<{ key: string; startX: number; startWidth: number } | null>(null);
  const resizeCleanupRef = useRef<(() => void) | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const rowSignature = rows.map(rowKey).join("\u0000");

  const timestampColumn = useMemo<CommonTableColumn<Row>>(
    () => ({
      key: "__timestamps",
      label: "등록/수정 일시",
      cell: () => null,
      sortValue: (row) =>
        Math.max(
          timestampValue(timestamps.createdAt(row)),
          timestampValue(timestamps.updatedAt(row)),
        ),
    }),
    [timestamps],
  );

  const sortableColumns = useMemo(
    () => new Map([...columns, timestampColumn].map((column) => [column.key, column])),
    [columns, timestampColumn],
  );

  const sortedRows = useMemo(() => {
    const column = sortableColumns.get(sort.key);
    if (!column?.sortValue) return rows;
    return rows
      .map((row, index) => ({ row, index }))
      .sort((left, right) => {
        const compared = compareValues(column.sortValue?.(left.row), column.sortValue?.(right.row));
        return (sort.direction === "asc" ? compared : -compared) || left.index - right.index;
      })
      .map(({ row }) => row);
  }, [rows, sort, sortableColumns]);

  const pageCount = Math.max(1, Math.ceil(sortedRows.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const pageRows = useMemo(
    () => sortedRows.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE),
    [safePage, sortedRows],
  );

  useEffect(() => {
    setPage(1);
  }, [rowSignature, sort.key, sort.direction]);

  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    const updateWidth = () => setTableViewportWidth(node.clientWidth);
    updateWidth();
    const observer = new ResizeObserver(updateWidth);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => () => resizeCleanupRef.current?.(), []);

  function toggleSort(key: string) {
    const column = sortableColumns.get(key);
    if (!column?.sortValue) return;
    setSort((current) =>
      current.key === key
        ? { key, direction: current.direction === "asc" ? "desc" : "asc" }
        : { key, direction: "asc" },
    );
  }

  function onRowKeyDown(event: KeyboardEvent<HTMLTableRowElement>, row: Row) {
    if (!onRowClick || (event.key !== "Enter" && event.key !== " ")) return;
    event.preventDefault();
    onRowClick(row);
  }

  const columnCount = columns.length + 2 + (selection ? 1 : 0) + (actions ? 1 : 0);
  const rangeStart = sortedRows.length === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
  const rangeEnd = Math.min(safePage * PAGE_SIZE, sortedRows.length);
  const sourceCount = totalCount ?? rows.length;
  const semanticColumnWidth = (column: CommonTableColumn<Row>, index: number) => {
    if (index === 0) return 210;
    // Figma table barchart/status cell은 일반 문자열 셀보다 넓은 186px 블록을 쓴다.
    if (/(progress|status|observation)/i.test(column.key)) return 186;
    return 118;
  };
  const dataColumnWidth = (column: CommonTableColumn<Row>, index: number) =>
    columnWidths[column.key] ?? semanticColumnWidth(column, index);
  const tableBaseWidth =
    (selection ? 42 : 0) +
    54 +
    columns.reduce((sum, column, index) => sum + dataColumnWidth(column, index), 0) +
    184 +
    (actions ? 196 : 0);
  const flexibleWidth = Math.max(0, tableViewportWidth - tableBaseWidth);
  const flexibleWeight = columns.reduce(
    (sum, column) => sum + (Object.hasOwn(columnWidths, column.key) ? 0 : 1),
    0,
  );
  const renderedColumnWidth = (column: CommonTableColumn<Row>, index: number) => {
    const weight = Object.hasOwn(columnWidths, column.key) ? 0 : 1;
    return dataColumnWidth(column, index) + (flexibleWeight > 0 ? flexibleWidth * weight / flexibleWeight : 0);
  };
  const tablePixelWidth = Math.max(tableBaseWidth, tableViewportWidth);

  function beginResize(event: ReactPointerEvent<HTMLSpanElement>, key: string) {
    event.preventDefault();
    event.stopPropagation();
    const header = event.currentTarget.parentElement;
    if (!header) return;
    resizeRef.current = { key, startX: event.clientX, startWidth: header.getBoundingClientRect().width };
    resizeCleanupRef.current?.();
    const onMove = (moveEvent: PointerEvent) => {
      const active = resizeRef.current;
      if (!active) return;
      const width = Math.min(900, Math.max(80, active.startWidth + moveEvent.clientX - active.startX));
      setColumnWidths((current) => ({ ...current, [active.key]: Math.round(width) }));
    };
    const onEnd = () => {
      resizeRef.current = null;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onEnd);
      window.removeEventListener("pointercancel", onEnd);
      resizeCleanupRef.current = null;
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onEnd);
    window.addEventListener("pointercancel", onEnd);
    resizeCleanupRef.current = onEnd;
  }

  return (
    <section className="common-table-shell" data-testid={`${testId}-shell`}>
      <div className="common-table-toolbar">
        <div className="common-table-toolbar-meta" aria-label="목록 건수와 현재 페이지">
          <span className="saas-toolbar-chip is-total">전체 {sourceCount.toLocaleString("ko-KR")}건</span>
          {selection && <span className={`saas-toolbar-chip${selection.selected.size > 0 ? " is-selected" : ""}`}>선택 {selection.selected.size}건</span>}
          {sourceCount !== rows.length && <span className="common-table-result-count">조회 {rows.length.toLocaleString("ko-KR")}건</span>}
          <span className="common-table-page-count">{safePage}/{pageCount} 페이지</span>
        </div>
        <div className="common-table-toolbar-controls">
          {filters ? <div className="common-table-filters">{filters}</div> : null}
          {toolbar}
          <div className="common-table-quick-sort" aria-label="목록 빠른 정렬">
          <label>
            <select
              aria-label="빠른 정렬"
              value={sort.key}
              onChange={(event) => {
                const key = event.target.value;
                setSort({ key, direction: sort.direction });
              }}
              data-testid={`${testId}-quick-sort`}
            >
              {[...columns, timestampColumn].filter((column) => column.sortValue).map((column) => (
                <option key={column.key} value={column.key}>{column.label}</option>
              ))}
            </select>
          </label>
          <label>
            <select
              aria-label="정렬 방향"
              value={sort.direction}
              onChange={(event) => setSort((current) => ({ ...current, direction: event.target.value as "asc" | "desc" }))}
              data-testid={`${testId}-quick-sort-direction`}
            >
              <option value="desc">내림차순</option>
              <option value="asc">오름차순</option>
            </select>
          </label>
          </div>
        </div>
      </div>
      <div className="common-table-scroll" ref={scrollRef}>
        <table className="data-table common-data-table" data-testid={testId} style={{ width: tablePixelWidth }}>
          <colgroup>
            {selection && <col style={{ width: 42 }} />}
            <col style={{ width: 54 }} />
            {columns.map((column, index) => <col key={column.key} style={{ width: renderedColumnWidth(column, index) }} />)}
            <col style={{ width: 184 }} />
            {actions && <col style={{ width: 196 }} />}
          </colgroup>
          <thead>
            <tr>
              {selection && (
                <th className="common-col-check" scope="col">
                  <TableSelectAllCheckbox
                    id={`${testId}-select-all`}
                    allIds={rows.map(rowKey)}
                    selected={selection.selected}
                    onChange={selection.onChange}
                  />
                </th>
              )}
              <th className="common-col-index" scope="col">번호</th>
              {columns.map((column, index) => (
                <th
                  key={column.key}
                  className={`common-col-data${index === 0 ? " common-col-key" : ""}`}
                  scope="col"
                  aria-sort={
                    sort.key === column.key
                      ? sort.direction === "asc" ? "ascending" : "descending"
                      : undefined
                  }
                >
                  {column.sortValue ? (
                    <button
                      type="button"
                      className="common-sort-button"
                      onClick={() => toggleSort(column.key)}
                      data-testid={`${testId}-sort-${column.key}`}
                    >
                      <span>{column.label}</span>
                      <span className="common-sort-icon" aria-hidden>
                        {sort.key === column.key ? (sort.direction === "asc" ? "▲" : "▼") : "↕"}
                      </span>
                    </button>
                  ) : column.label}
                  <span
                    className="common-column-resizer"
                    role="separator"
                    aria-orientation="vertical"
                    aria-label={`${column.label} 열 너비 조절`}
                    onPointerDown={(event) => beginResize(event, column.key)}
                    onDoubleClick={() => setColumnWidths((current) => {
                      const next = { ...current };
                      delete next[column.key];
                      return next;
                    })}
                  />
                </th>
              ))}
              <th
                className="common-col-timestamps"
                scope="col"
                aria-sort={
                  sort.key === timestampColumn.key
                    ? sort.direction === "asc" ? "ascending" : "descending"
                    : undefined
                }
              >
                <button
                  type="button"
                  className="common-sort-button"
                  onClick={() => toggleSort(timestampColumn.key)}
                  data-testid={`${testId}-sort-timestamps`}
                >
                  <span>{timestampColumn.label}</span>
                  <span className="common-sort-icon" aria-hidden>
                    {sort.key === timestampColumn.key ? (sort.direction === "asc" ? "▲" : "▼") : "↕"}
                  </span>
                </button>
              </th>
              {actions && <th className="common-col-actions" scope="col">프로세스</th>}
            </tr>
          </thead>
          <tbody>
            <TableStateRow
              loading={loading}
              isEmpty={!loading && rows.length === 0}
              cols={columnCount}
              emptyText={emptyText}
              loadingText={loadingText}
            />
            {!loading && pageRows.map((row, index) => {
              const key = rowKey(row);
              const clickable = Boolean(onRowClick);
              const extraClass = rowClassName?.(row) ?? "";
              return (
                <tr
                  key={key}
                  className={`${clickable ? "is-clickable" : ""}${extraClass ? ` ${extraClass}` : ""}`.trim()}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  onKeyDown={(event) => onRowKeyDown(event, row)}
                  tabIndex={clickable ? 0 : undefined}
                  data-testid={rowTestId?.(row)}
                >
                  {selection && (
                    <td className="common-col-check" onClick={(event) => event.stopPropagation()}>
                      <TableRowCheckbox
                        id={`${testId}-row-${key}`}
                        checked={selection.selected.has(key)}
                        label={selection.label(row)}
                        onCheckedChange={(checked) => {
                          const next = new Set(selection.selected);
                          if (checked) next.add(key);
                          else next.delete(key);
                          selection.onChange(next);
                        }}
                      />
                    </td>
                  )}
                  <td className="common-col-index">{(safePage - 1) * PAGE_SIZE + index + 1}</td>
                  {columns.map((column, columnIndex) => (
                    <td key={column.key} className={`common-col-data${columnIndex === 0 ? " common-col-key" : ""}`}>
                      {column.cell(row)}
                    </td>
                  ))}
                  <td className="common-col-timestamps">
                    <div className="common-timestamp-stack">
                      <span><b>등록</b>{formatDateTime(timestamps.createdAt(row))}</span>
                      <span><b>수정</b>{formatDateTime(timestamps.updatedAt(row) ?? timestamps.createdAt(row))}</span>
                    </div>
                  </td>
                  {actions && (
                    <td className="common-col-actions" onClick={(event) => event.stopPropagation()}>
                      <div className="common-row-actions">{actions(row)}</div>
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {pageCount > 1 && (
        <nav className="common-table-pagination" aria-label="테이블 페이지" data-testid={`${testId}-pagination`}>
          <span>{rangeStart}-{rangeEnd} / 전체 {sortedRows.length}건</span>
          <div>
            <button type="button" onClick={() => setPage(1)} disabled={safePage === 1} aria-label="첫 페이지">«</button>
            <button type="button" onClick={() => setPage(Math.max(1, safePage - 1))} disabled={safePage === 1} aria-label="이전 페이지">‹</button>
            {visiblePageNumbers(safePage, pageCount).map((number) => (
              <button
                key={number}
                type="button"
                className={number === safePage ? "is-current" : ""}
                aria-current={number === safePage ? "page" : undefined}
                onClick={() => setPage(number)}
              >
                {number}
              </button>
            ))}
            <button type="button" onClick={() => setPage(Math.min(pageCount, safePage + 1))} disabled={safePage === pageCount} aria-label="다음 페이지">›</button>
            <button type="button" onClick={() => setPage(pageCount)} disabled={safePage === pageCount} aria-label="마지막 페이지">»</button>
          </div>
        </nav>
      )}
    </section>
  );
}

"use client";

import { useEffect, useRef, useState, type ChangeEvent, type ReactNode } from "react";
import { Checkbox } from "./ui";
import { nearestTableCsv, parseCsv, type CsvRow } from "../lib/csv";
import { actionToastId, showActionToast } from "../lib/actionToast";

/** Analysis 화면과 동일한 선택·일괄삭제 확인 문구 */
export function confirmBulkDelete(noun: string, count: number): boolean {
  if (count <= 0) return false;
  return window.confirm(`선택한 ${noun} ${count}건을 삭제할까요?`);
}

/** 헤더/툴바용 선택 삭제 버튼 (Analysis action-btn-danger 동일) */
export function BulkDeleteButton({
  selectedCount,
  busy,
  onClick,
  label = "선택 삭제",
  testId,
}: {
  selectedCount: number;
  busy?: boolean;
  onClick: () => void;
  label?: string;
  testId?: string;
}) {
  return (
    <button
      type="button"
      className="action-btn action-btn-danger"
      disabled={Boolean(busy) || selectedCount === 0}
      onClick={onClick}
      data-testid={testId ?? "table-bulk-delete"}
    >
      {label}
      {selectedCount > 0 ? ` (${selectedCount})` : ""}
    </button>
  );
}

/**
 * 체크박스 테이블 공통 일괄삭제 폼.
 * Analysis 「선택 삭제」 UX를 프로젝트·시나리오 등에서 공유한다.
 */
export function TableBulkDeleteForm({
  noun,
  totalCount,
  selectedCount,
  busy,
  onDelete,
  extraActions,
  onImportCsv,
  embedded = false,
  testId = "table-bulk-form",
}: {
  noun: string;
  totalCount: number;
  selectedCount: number;
  busy?: boolean;
  onDelete: () => void;
  extraActions?: ReactNode;
  onImportCsv?: (rows: CsvRow[], file: File) => void | Promise<void>;
  embedded?: boolean;
  testId?: string;
}) {
  const importRef = useRef<HTMLInputElement>(null);
  const exportRef = useRef<HTMLFormElement>(null);
  const [csvMessage, setCsvMessage] = useState<string | null>(null);
  const [exportData, setExportData] = useState({ count: 0, csv: "" });

  useEffect(() => {
    if (!exportRef.current) return;
    const exported = nearestTableCsv(exportRef.current);
    setExportData(exported);
  }, [noun, totalCount]);

  async function importCsv(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const toastId = actionToastId("csv-import", testId);
    showActionToast({
      id: toastId,
      title: "CSV 가져오기",
      message: `${noun} CSV 가져오기를 시작했습니다. 파일 내용을 확인하고 있어요.`,
      tone: "progress",
    });
    try {
      const rows = parseCsv(await file.text());
      if (rows.length === 0) throw new Error("헤더와 데이터 행이 있는 CSV가 필요합니다");
      if (onImportCsv) {
        await onImportCsv(rows, file);
        setCsvMessage(`${rows.length}건 적용`);
      } else {
        sessionStorage.setItem(`table.csv.staging.${testId}`, JSON.stringify({ name: file.name, rows }));
        window.dispatchEvent(new CustomEvent("table-csv-import", { detail: { testId, fileName: file.name, rows } }));
        setCsvMessage(`${rows.length}건 검증·임시 저장`);
      }
      showActionToast({
        id: toastId,
        title: "CSV 가져오기 완료",
        message: `${noun} CSV ${rows.length}건을 확인했습니다.`,
        tone: "success",
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "CSV를 읽지 못했습니다";
      setCsvMessage(errorMessage);
      showActionToast({ id: toastId, title: "CSV 가져오기 실패", message: errorMessage, tone: "error" });
    }
  }

  return (
    <div className={`table-bulk-form${embedded ? " is-embedded" : ""}`} data-testid={testId}>
      {!embedded && (
        <div className="table-bulk-form-meta">
          <span className="saas-toolbar-chip">
            전체 {totalCount}건 · {noun}
          </span>
          <span className={`saas-toolbar-chip${selectedCount > 0 ? " is-selected" : ""}`}>
            선택 {selectedCount}건
          </span>
        </div>
      )}
      <div className="table-bulk-form-actions">
        {csvMessage && <span className="saas-toolbar-chip csv-state-chip">{csvMessage}</span>}
        {extraActions}
        <form
          ref={exportRef}
          action="/api/csv-export"
          method="post"
          onSubmit={(event) => {
            const toastId = actionToastId("csv-export", testId);
            if (exportData.count === 0) {
              event.preventDefault();
              setCsvMessage("내보낼 테이블 없음");
              showActionToast({ id: toastId, title: "CSV 내보내기", message: "내보낼 테이블 데이터가 없습니다.", tone: "error" });
              return;
            }
            setCsvMessage(`${exportData.count}건 내보냄`);
            showActionToast({
              id: toastId,
              title: "CSV 내보내기",
              message: `${noun} ${exportData.count}건의 CSV 내보내기를 시작했습니다.`,
              tone: "progress",
            });
          }}
        >
          <input type="hidden" name="csv" value={exportData.csv} />
          <input type="hidden" name="filename" value={`${noun}-${new Date().toISOString().slice(0, 10)}.csv`} />
          <button
            type="submit"
            className="ghost-btn"
            data-testid={`${testId}-csv-export`}
          >
            CSV 내보내기
          </button>
        </form>
        <button
          type="button"
          className="ghost-btn"
          onClick={() => {
            showActionToast({
              id: actionToastId("csv-import", testId),
              title: "CSV 가져오기",
              message: `${noun}에 가져올 CSV 파일을 선택해 주세요.`,
              tone: "info",
            });
            importRef.current?.click();
          }}
          data-testid={`${testId}-csv-import`}
        >
          CSV 가져오기
        </button>
        <input ref={importRef} className="visually-hidden" type="file" accept=".csv,text/csv" onChange={importCsv} />
        <BulkDeleteButton
          selectedCount={selectedCount}
          busy={busy}
          onClick={onDelete}
          testId={`${testId}-delete`}
        />
      </div>
    </div>
  );
}

/** thead 전체 선택 체크박스 (SaaS Checkbox 공용) */
export function TableSelectAllCheckbox({
  allIds,
  selected,
  onChange,
  ariaLabel = "전체 선택",
  id,
}: {
  allIds: string[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
  ariaLabel?: string;
  id?: string;
}) {
  const allChecked = allIds.length > 0 && selected.size === allIds.length;
  return (
    <Checkbox
      id={id}
      checked={allChecked}
      aria-label={ariaLabel}
      onChange={(e) => {
        onChange(e.target.checked ? new Set(allIds) : new Set());
      }}
    />
  );
}

/** 행 단위 선택 체크박스 */
export function TableRowCheckbox({
  id,
  checked,
  label,
  onCheckedChange,
}: {
  id?: string;
  checked: boolean;
  label: string;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <Checkbox
      id={id}
      checked={checked}
      aria-label={label}
      onChange={(e) => onCheckedChange(e.target.checked)}
    />
  );
}

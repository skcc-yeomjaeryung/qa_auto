"use client";

import { useRef, useState, type ChangeEvent } from "react";
import { parseCsv, type CsvRow } from "../lib/csv";
import { Button } from "./ui/Button";
import { AssistantGuide } from "./AssistantGuide";

export type ScenarioTemplateRow = {
  scenarioId: string;
  description: string;
  requestNaturalLanguage: string;
  responseNaturalLanguage: string;
  role?: string;
  businessPath?: string;
};

function pick(row: CsvRow, ...keys: string[]): string {
  for (const key of keys) {
    const value = row[key];
    if (value?.trim()) return value.trim();
  }
  return "";
}

export function ScenarioGenerationDialog({
  open,
  busy,
  onClose,
  onGenerate,
}: {
  open: boolean;
  busy: boolean;
  onClose: () => void;
  onGenerate: (mode: "ai" | "test_data_csv", rows: ScenarioTemplateRow[]) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<"ai" | "test_data_csv">("ai");
  const [rows, setRows] = useState<ScenarioTemplateRow[]>([]);
  const [fileName, setFileName] = useState("");
  const [error, setError] = useState<string | null>(null);
  if (!open) return null;

  async function readFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const parsed = parseCsv(await file.text());
      const normalized = parsed.map((row) => ({
        scenarioId: pick(row, "scenarioId", "테스트 시나리오 아이디", "시나리오ID"),
        description: pick(row, "description", "테스트 시나리오 설명", "설명"),
        requestNaturalLanguage: pick(row, "requestNaturalLanguage", "요청값 (자연어)", "요청값"),
        responseNaturalLanguage: pick(row, "responseNaturalLanguage", "응답값 (자연어)", "응답값"),
        role: pick(row, "role", "권한", "담당 권한") || undefined,
        businessPath: pick(row, "businessPath", "업무 경로", "L1/L2/L3") || undefined,
      }));
      if (
        normalized.length === 0 ||
        normalized.some((row) => !row.scenarioId || !row.description || !row.requestNaturalLanguage || !row.responseNaturalLanguage)
      ) {
        throw new Error("시나리오 ID·설명·요청값·응답값은 모든 행에 필요합니다");
      }
      setRows(normalized);
      setFileName(file.name);
      setError(null);
    } catch (caught) {
      setRows([]);
      setFileName("");
      setError(caught instanceof Error ? caught.message : "CSV를 읽지 못했습니다");
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" data-testid="scenario-generation-dialog">
      <section className="generation-modal" role="dialog" aria-modal="true" aria-labelledby="generation-dialog-title">
        <header>
          <div>
            <p className="panel-kicker">새 시나리오 만들기</p>
            <h3 id="generation-dialog-title">어떤 도움으로 초안을 시작할까요?</h3>
          </div>
          <button type="button" className="modal-close" disabled={busy} onClick={onClose} aria-label="닫기">×</button>
        </header>
        <AssistantGuide compact title="코드 근거와 현업 맥락을 함께 볼게요" message="화면 이벤트, Backend API, 보강 자료를 연결하고 인간이 놓치기 쉬운 경계값도 후보로 확장합니다." />
        <div className="generation-options">
          <label className={mode === "ai" ? "is-selected" : ""}>
            <input type="radio" name="generation-mode" checked={mode === "ai"} onChange={() => setMode("ai")} />
            <span><strong>코드 근거로 자동 만들기</strong><em>화면과 서버 코드를 먼저 연결하고, 실제 모델 호출이 성공하면 문장과 입력 후보를 더 자연스럽게 다듬습니다.</em></span>
          </label>
          <label className={mode === "test_data_csv" ? "is-selected" : ""}>
            <input type="radio" name="generation-mode" checked={mode === "test_data_csv"} onChange={() => setMode("test_data_csv")} />
            <span><strong>내 테스트 데이터 불러오기</strong><em>작성해 둔 요청·응답 CSV를 코드 근거와 연결해 실행 가능한 초안으로 정리합니다.</em></span>
          </label>
        </div>
        {mode === "test_data_csv" && (
          <div className="generation-csv-panel">
            <div>
              <strong>CSV 작성 안내</strong>
              <p>시나리오 ID·설명·요청값·응답값만 채우면 됩니다. 권한과 업무 경로는 선택 항목입니다.</p>
            </div>
            <div className="generation-csv-actions">
              <a
                className="ghost-btn"
                href="/templates/test-scenario-template.csv"
                download="test-scenario-template.csv"
              >
                샘플 CSV 다운로드
              </a>
              <button type="button" className="ghost-btn" onClick={() => inputRef.current?.click()}>작성 CSV 업로드</button>
              <input ref={inputRef} type="file" accept=".csv,text/csv" className="visually-hidden" onChange={readFile} />
            </div>
            {fileName && <p className="generation-file-ok">{fileName} · {rows.length}건 검증 완료</p>}
            {error && <p className="generation-file-error">{error}</p>}
          </div>
        )}
        <footer>
          <p>완료 후 실제 모델 사용 여부와 규칙 기반 전환 사유를 Agent 모니터링에서 확인할 수 있습니다.</p>
          <div>
            <Button variant="secondary" disabled={busy} onClick={onClose}>취소</Button>
            <Button
              busy={busy}
              disabled={mode === "test_data_csv" && rows.length === 0}
              onClick={() => onGenerate(mode, rows)}
              data-testid="scenario-generation-confirm"
            >
              {mode === "ai" ? "초안 만들기" : `${rows.length}건으로 만들기`}
            </Button>
          </div>
        </footer>
      </section>
    </div>
  );
}

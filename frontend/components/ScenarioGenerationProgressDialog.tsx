"use client";

import { useEffect, useState } from "react";
import { ProgressBarType1 } from "./ProgressBar";
import { Button } from "./ui/Button";

export type ScenarioGenerationStatus = "idle" | "running" | "complete" | "error";

/** 장시간 모델 생성 중 반복 노출하는 근거 중심 안내 문구 50개. */
export const SCENARIO_GENERATION_MESSAGES = [
  "연결된 화면 구조를 차분히 읽고 있어요.",
  "사용자가 실제로 누를 수 있는 동작을 찾고 있어요.",
  "화면 이동과 서버 요청의 연결 지점을 확인하고 있어요.",
  "입력 필드와 버튼의 관계를 정리하고 있어요.",
  "코드에서 확인된 경로만 시나리오 후보로 모으고 있어요.",
  "Frontend 이벤트와 Backend API를 서로 맞춰 보고 있어요.",
  "화면 A에서 화면 B로 이어지는 흐름을 살펴보고 있어요.",
  "로그인이 필요한 여정인지 확인하고 있어요.",
  "사용자 권한에 따라 달라지는 동작을 구분하고 있어요.",
  "입력값이 전달되는 위치를 따라가고 있어요.",
  "응답 데이터가 다음 화면에 표시되는지 확인하고 있어요.",
  "중복된 동작은 합치고 의미 있는 흐름을 남기고 있어요.",
  "실행할 수 없는 후보를 조심스럽게 제외하고 있어요.",
  "화면의 선택자와 코드 근거를 함께 정리하고 있어요.",
  "요청과 응답에 필요한 필드를 비교하고 있어요.",
  "테스트 시작 전에 필요한 조건을 찾고 있어요.",
  "정상 흐름과 확인이 필요한 흐름을 나누고 있어요.",
  "사용자 관점에서 읽기 쉬운 이름을 다듬고 있어요.",
  "시나리오 단계가 자연스럽게 이어지는지 확인하고 있어요.",
  "예상 결과를 코드 근거와 다시 대조하고 있어요.",
  "화면에 없는 동작을 만들지 않도록 검토하고 있어요.",
  "서버에 없는 API를 추정하지 않도록 확인하고 있어요.",
  "입력 후보에 민감한 값이 섞이지 않았는지 살펴보고 있어요.",
  "테스트 증적을 남길 지점을 정리하고 있어요.",
  "실행 순서가 실제 사용자 여정과 맞는지 확인하고 있어요.",
  "페이지 이동 전후의 상태 변화를 비교하고 있어요.",
  "버튼 클릭 뒤 발생하는 요청을 따라가고 있어요.",
  "폼 입력과 전송 동작을 한 흐름으로 묶고 있어요.",
  "화면별 역할과 업무 맥락을 정리하고 있어요.",
  "확인이 필요한 데이터는 추정하지 않고 표시하고 있어요.",
  "테스트에 필요한 준비 단계를 앞쪽에 배치하고 있어요.",
  "실패 관측에 도움이 되는 조건을 살펴보고 있어요.",
  "반복되는 단계는 더 간결하게 다듬고 있어요.",
  "긴 기술 이름을 사람이 읽기 쉬운 표현으로 바꾸고 있어요.",
  "화면과 API의 불일치가 없는지 다시 확인하고 있어요.",
  "선택한 분석 범위가 정확히 반영됐는지 확인하고 있어요.",
  "제외한 파일이 후보에서 빠졌는지 점검하고 있어요.",
  "선택한 AI 모델이 코드 근거를 바탕으로 문장을 다듬고 있어요.",
  "생성 결과의 형식이 계약과 맞는지 검사하고 있어요.",
  "각 단계에 필요한 입력과 결과를 연결하고 있어요.",
  "실행 중 관측할 화면과 요청을 표시하고 있어요.",
  "사람의 확인이 필요한 항목을 따로 모으고 있어요.",
  "시나리오 이름이 서로 쉽게 구분되는지 살펴보고 있어요.",
  "업무 흐름의 시작과 끝을 다시 확인하고 있어요.",
  "생성된 단계에 빠진 연결이 없는지 점검하고 있어요.",
  "테스트 데이터 후보를 실행 가능한 형태로 정리하고 있어요.",
  "모델 응답을 저장 계약에 맞게 검증하고 있어요.",
  "최종 초안에 코드 근거를 연결하고 있어요.",
  "테스트 시나리오 목록에 담을 준비를 하고 있어요.",
  "조금만 기다려 주세요. 마지막 정리를 진행하고 있어요.",
] as const;

function formatElapsed(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return minutes > 0 ? `${minutes}분 ${String(remaining).padStart(2, "0")}초` : `${remaining}초`;
}

function phaseLabel(progress: number): string {
  if (progress < 16) return "선택한 분석 범위를 준비하는 중";
  if (progress < 28) return "코드 근거와 제외 항목을 정리하는 중";
  if (progress < 70) return "선택한 AI 모델이 시나리오 초안을 만드는 중";
  if (progress < 93) return "생성 결과의 구조와 근거를 검증하는 중";
  return "테스트 시나리오 목록에 저장하는 중";
}

export function ScenarioGenerationProgressDialog({
  status,
  progress,
  startedAt,
  sourceMode,
  analysisCount,
  resultCount,
  error,
  selectedModel,
  selectionSummary,
  onClose,
  onRetry,
  onNavigate,
}: {
  status: ScenarioGenerationStatus;
  progress: number;
  startedAt: number | null;
  sourceMode: "ai" | "test_data_csv";
  analysisCount: number;
  resultCount: number;
  error: string | null;
  selectedModel: string | null;
  selectionSummary: string | null;
  onClose: () => void;
  onRetry: () => void;
  onNavigate: () => void;
}) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (status !== "running") return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [status, startedAt]);

  if (status === "idle") return null;

  const elapsedSeconds = startedAt ? Math.max(0, Math.floor((now - startedAt) / 1000)) : 0;
  // 현재 API가 세부 진행률을 스트리밍하지 않으므로 시간 기반 표시는 92%에서 멈춘다.
  // 완료 응답을 받은 경우에만 100%로 확정해 실제 상태와 예상값을 구분한다.
  const estimatedProgress = Math.min(
    92,
    Math.round(12 + 80 * (1 - Math.exp(-elapsedSeconds / 70))),
  );
  const displayProgress = status === "complete"
    ? 100
    : status === "running"
      ? Math.max(progress, estimatedProgress)
      : Math.min(92, Math.max(progress, estimatedProgress));
  const message = SCENARIO_GENERATION_MESSAGES[
    Math.floor(elapsedSeconds / 3) % SCENARIO_GENERATION_MESSAGES.length
  ];
  const title = status === "complete"
    ? "테스트 시나리오 생성이 완료됐습니다"
    : status === "error"
      ? "테스트 시나리오 생성을 확인해 주세요"
      : "테스트 시나리오 생성 중입니다";

  return (
    <div className="modal-backdrop" role="presentation" data-testid="scenario-generation-progress-dialog">
      <section
        className={`generation-modal generation-progress-modal is-${status}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="generation-progress-title"
        aria-busy={status === "running"}
      >
        <header>
          <div>
            <p className="panel-kicker">시나리오 생성</p>
            <h3 id="generation-progress-title">{title}</h3>
          </div>
          {status !== "running" && (
            <button type="button" className="modal-close" onClick={onClose} aria-label="닫기">×</button>
          )}
        </header>

        <div className="generation-progress-body">
          <div className={`generation-ai-orb is-${status}`} aria-hidden>
            <span>AI</span>
            {status === "running" && <i><b /><b /><b /></i>}
          </div>

          {status === "running" && (
            <div className="generation-live-copy" role="status" aria-live="polite">
              <strong>AI가 코드 근거를 바탕으로 열심히 만들고 있어요.</strong>
              <p key={message}>{message}</p>
            </div>
          )}
          {status === "complete" && (
            <div className="generation-live-copy is-complete" role="status" aria-live="polite">
              <strong>테스트 시나리오 {resultCount.toLocaleString("ko-KR")}건을 만들었습니다.</strong>
              <p>목록으로 이동해 시나리오 내용을 확인하고 필요한 항목을 실행해 보세요.</p>
            </div>
          )}
          {status === "error" && (
            <div className="generation-live-copy is-error" role="alert">
              <strong>생성을 마치지 못했습니다.</strong>
              <p>{error || "분석 결과와 모델 연결 상태를 확인한 뒤 다시 시도해 주세요."}</p>
            </div>
          )}

          <ProgressBarType1
            percent={displayProgress}
            label={status === "running" ? `예상 진행 · ${phaseLabel(displayProgress)}` : status === "complete" ? "생성 완료" : "생성 중단"}
            status={status === "complete" ? "complete" : status === "error" ? "error" : "progressing"}
            testId="scenario-generation-progress"
          />

          <div className="generation-progress-facts">
            <span><small>경과 시간</small><strong>{formatElapsed(elapsedSeconds)}</strong></span>
            <span><small>분석 범위</small><strong>{analysisCount.toLocaleString("ko-KR")}건</strong></span>
            <span><small>사용 모델</small><strong>{selectedModel || (sourceMode === "ai" ? "선택 확인 중" : "CSV + 선택 모델")}</strong></span>
          </div>

          {selectionSummary && (
            <p className="generation-progress-note" data-testid="scenario-generation-model-selection">
              {selectionSummary}
            </p>
          )}

          {status === "running" && (
            <p className="generation-progress-note">
              정확한 완료율은 서버 응답 후 확정됩니다. 예상 게이지는 92%에서 기다리고, 완료 응답을 받았을 때만 100%가 됩니다.
            </p>
          )}
        </div>

        <footer>
          <p>
            {status === "running"
              ? "선택한 모델 응답이 늦어져도 코드 근거 초안은 보존됩니다. 완료될 때까지 이 상태를 유지합니다."
              : status === "complete"
                ? "실제 모델 사용 여부와 호출 영수증은 Agent 모니터링에서 확인할 수 있습니다."
                : "오류 내용을 확인한 뒤 같은 분석 범위로 다시 시작할 수 있습니다."}
          </p>
          <div>
            {status === "complete" && (
              <>
                <Button variant="secondary" onClick={onClose}>닫기</Button>
                <Button variant="primary" onClick={onNavigate} data-testid="scenario-generation-navigate">
                  테스트 시나리오로 이동
                </Button>
              </>
            )}
            {status === "error" && (
              <>
                <Button variant="secondary" onClick={onClose}>닫기</Button>
                <Button variant="primary" onClick={onRetry}>다시 선택하기</Button>
              </>
            )}
          </div>
        </footer>
      </section>
    </div>
  );
}

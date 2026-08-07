"use client";

import { useEffect, useState } from "react";
import { PanelLoading } from "./LoadingStates";
import { apiFetch } from "../lib/apiClient";

type TimelineEntry = {
  order: number;
  kind: string;
  title: string;
  timestamp?: string | null;
  status?: string | null;
  detail?: string | null;
  maskedFields?: string[];
  truncated?: boolean;
  requestSequence?: number | null;
  source?: string | null;
  constraint?: string | null;
};

type Timeline = {
  runId: string;
  backendTraceStatus: string;
  partialEvidence: boolean;
  constraints: string[];
  entries: TimelineEntry[];
  backendEventCount: number;
};

export function RunTraceTimeline({ runId }: { runId: string }) {
  const [data, setData] = useState<Timeline | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiFetch(`/api/runs/${runId}/timeline`, { cache: "no-store" })
      .then(async (res) => {
        if (!res.ok) throw new Error("타임라인을 불러오지 못했습니다");
        const json = (await res.json()) as Timeline;
        if (!cancelled) setData(json);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (error) {
    return <div className="connect-banner is-warn">{error}</div>;
  }
  if (!data) {
    return <PanelLoading label="관통 타임라인을 불러오는 중입니다" />;
  }
  const externalNetworkOnly = data.backendTraceStatus === "external_network_only";

  return (
    <section data-testid="run-trace-timeline" className="run-trace-timeline">
      <div className="run-summary-bar">
        <span className={`outcome-pill outcome-${data.partialEvidence ? "unknown" : "success"}`}>
          서버 로그 연결 · {statusLabel(data.backendTraceStatus)}
        </span>
        <span className="muted">
          서버 이벤트 {data.backendEventCount}건
          {externalNetworkOnly
            ? " · 외부 공개 대상이라 내부 서버 로그는 관측 범위 밖입니다"
            : data.partialEvidence
              ? " · 증적 일부만 수집됨"
              : ""}
        </span>
      </div>
      {data.constraints.length > 0 && (
        <div className="connect-banner is-warn">
          수집 제약: {data.constraints.join(", ")} · 외부 대상은 브라우저에서 관측한 통신 증적만 사용합니다
        </div>
      )}
      <ol className="narrative-timeline">
        {data.entries.map((step) => (
          <li key={`${step.order}-${step.kind}`} className="narrative-item is-observe">
            <div className="narrative-order">{step.order}</div>
            <div className="narrative-body">
              <strong>
                {entryTitleKo(step)}
                {step.requestSequence != null ? (
                  <span className="muted"> · 요청 {step.requestSequence}번째</span>
                ) : null}
              </strong>
              {step.detail && <p>{step.detail}</p>}
              {!!step.maskedFields?.length && (
                <small className="masked-fields">마스킹: {step.maskedFields.join(", ")}</small>
              )}
              {step.truncated && <small className="muted"> · 본문 일부 생략</small>}
              {step.timestamp && <small className="muted"> · {step.timestamp}</small>}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function statusLabel(status: string) {
  if (status === "linked") return "연결됨";
  if (status === "partial") return "부분 증적";
  if (status === "external_network_only") return "외부(네트워크만)";
  return status || "미정";
}

/** 개발자 이벤트명을 테스터가 읽는 한 문장으로 바꾼다 (없는 사실은 만들지 않는다). */
const ENTRY_TITLE_KO: Record<string, string> = {
  browser_input: "화면에 입력값을 넣습니다",
  frontend_request: "버튼을 눌러 서버 요청을 일으킵니다",
  browser_response_received: "화면에 돌아온 결과를 관측합니다",
  backend_request_received: "서버가 요청을 받았습니다",
  backend_controller_entered: "서버 처리 구간에 진입했습니다",
  backend_service_called: "서버 내부 처리를 호출했습니다",
  backend_response_returned: "서버가 응답을 돌려줬습니다",
  binding: "결과 화면 데이터 바인딩 대조",
};

const BROWSER_ACTION_KO: Record<string, string> = {
  set_headers: "실행 추적 헤더를 붙입니다",
  navigate: "대상 화면을 엽니다",
  fill: "입력값을 채웁니다",
  type: "입력값을 채웁니다",
  click: "버튼을 클릭합니다",
  press: "키 입력을 보냅니다",
  snapshot: "화면 DOM을 스냅샷으로 남깁니다",
  screenshot: "화면 스크린샷을 남깁니다",
  verify_navigation: "화면 이동 결과를 확인합니다",
  wait_for_response: "서버 응답을 기다립니다",
  assert_visible: "화면 구성 표시를 확인합니다",
  assert_text: "결과 안내 문구를 확인합니다",
  select: "화면에서 제공된 항목을 선택합니다",
  capture_value: "업무 수행 전 현재 값을 기록합니다",
  capture_collection: "업무 수행 전 목록 상태를 기록합니다",
  verify_numeric_delta: "입력 전후 값의 변화를 확인합니다",
  verify_collection_change: "목록에 이번 실행 결과가 추가됐는지 확인합니다",
  verify_binding: "결과 값이 화면에 반영됐는지 확인합니다",
};

function entryTitleKo(entry: TimelineEntry): string {
  const mapped = ENTRY_TITLE_KO[entry.kind];
  if (mapped) return mapped;
  if (entry.kind === "browser_step") {
    const action = entry.title.split("·").pop()?.trim().toLowerCase() ?? "";
    return BROWSER_ACTION_KO[action] ?? `화면 단계를 수행합니다 (${action || "단계"})`;
  }
  return entry.title;
}

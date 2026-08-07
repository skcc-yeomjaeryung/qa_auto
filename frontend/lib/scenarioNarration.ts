/** Map technical agent-browser steps → human-readable scenario narration. */

import { screenLabelKo } from "./scenarioGuide";

export type TechStep = {
  stepId?: string;
  action?: string;
  status?: string;
  mcpTool?: string | null;
  refOrLocator?: string | null;
  observationSummary?: string | null;
  value?: string | null;
};

export type NarrativeStep = {
  order: number;
  title: string;
  detail: string;
  status: "success" | "failure" | "pending" | "unknown";
  reason: string;
};

export function narrateRunSteps(steps: TechStep[]): NarrativeStep[] {
  if (!steps?.length) {
    return [
      {
        order: 1,
        title: "실행 관측 대기",
        detail: "아직 기록된 시나리오 단계가 없습니다.",
        status: "pending",
        reason: "—",
      },
    ];
  }

  return steps.map((step, index) => {
    const action = String(step.action || "").toLowerCase();
    const tool = String(step.mcpTool || "").toLowerCase();
    const ref = String(step.refOrLocator || "");
    const obs = String(step.observationSummary || "");
    const ok = String(step.status || "").toLowerCase();
    const status: NarrativeStep["status"] =
      ok.includes("fail") || ok.includes("error")
        ? "failure"
        : ok === "ok" || ok.includes("success") || ok.includes("pass")
          ? "success"
          : ok.includes("queue") || ok.includes("run")
            ? "pending"
            : "unknown";

    const hint = `${ref} ${obs} ${action}`.toLowerCase();
    let title = "테스트 단계 수행";
    let detail = obs || ref || action || "관측 단계";

    if (action.includes("header") || tool.includes("header")) {
      title = "테스트 추적 준비";
      detail = "실행 추적용 헤더를 설정합니다";
    } else if (action.includes("navigate") || tool.includes("open")) {
      if (/login|signin|auth/.test(hint)) title = "로그인 화면으로 이동합니다";
      else if (/search|조회/.test(hint)) title = "조회 화면으로 이동합니다";
      else if (/dashboard|main|home/.test(hint)) title = "메인 대시보드로 이동합니다";
      else title = "대상 화면으로 이동합니다";
      detail = ref || obs || "화면을 엽니다";
    } else if (action.includes("fill") || action.includes("type") || tool.includes("fill") || tool.includes("type")) {
      if (/password|pwd|passwd/.test(hint)) title = "패스워드를 입력합니다";
      else if (/user|login|account|email/.test(hint)) title = "로그인 아이디를 입력합니다";
      else if (/customer|cus-/.test(hint)) title = "고객 ID를 입력합니다";
      else title = "입력값을 입력합니다";
      detail = ref ? `입력 위치: ${simplifyRef(ref)}` : obs || "입력 필드를 채웁니다";
    } else if (action === "select") {
      title = "화면에서 제공된 항목을 선택합니다";
      detail = obs || (ref ? `선택 위치: ${simplifyRef(ref)}` : "선택 목록을 확인합니다");
    } else if (action === "capture_value") {
      title = "업무 수행 전 현재 값을 기록합니다";
      detail = obs || "결과와 비교할 기준 값을 화면에서 관측합니다";
    } else if (action === "capture_collection") {
      title = "업무 수행 전 목록 상태를 기록합니다";
      detail = obs || "새 결과 행과 비교할 목록을 화면에서 관측합니다";
    } else if (action.includes("click") || tool.includes("click")) {
      if (/login|signin|submit|검색|조회/.test(hint)) title = "사용자가 버튼을 눌러 테스트를 진행합니다";
      else title = "사용자 동작을 수행합니다 (클릭)";
      detail = ref ? `대상: ${simplifyRef(ref)}` : obs || "버튼을 클릭합니다";
    } else if (action.includes("wait") || tool.includes("wait")) {
      title = "화면 응답을 기다립니다";
      detail = obs || "다음 화면·요소를 대기합니다";
    } else if (action.includes("snapshot") || tool.includes("snapshot")) {
      if (/result|detail|dashboard|main/.test(hint)) title = "결과 화면을 확인합니다";
      else title = "화면 상태를 확인합니다";
      detail = obs || "DOM 스냅샷으로 결과를 관측합니다";
    } else if (action.includes("screenshot") || tool.includes("screenshot")) {
      title = "화면 증적을 저장합니다";
      detail = obs || "스크린샷을 남깁니다";
    } else if (action === "assert_text") {
      title = "업무 결과 안내 문구를 확인합니다";
      detail = obs || "후속 화면의 안내 문구를 관측합니다";
    } else if (action === "verify_numeric_delta") {
      title = "입력값만큼 상태가 변했는지 확인합니다";
      detail = obs || "업무 수행 전후 값을 대조합니다";
    } else if (action === "verify_collection_change") {
      title = "목록에 이번 실행 결과가 추가됐는지 확인합니다";
      detail = obs || "새 행의 라벨과 입력값을 대조합니다";
    } else if (action.includes("verify") || action.includes("binding")) {
      title = "결과 확인 및 데이터 바인딩을 검증합니다";
      detail = obs || "후속 화면 데이터를 대조합니다";
    }

    return {
      order: index + 1,
      title,
      detail,
      status,
      reason: statusLabel(status, obs),
    };
  });
}

/** Scenario-facing labels for flow nodes (not raw variable names). */
export function flowStepLabel(type: string, name: string, role?: string): string {
  const t = type.toLowerCase();
  const n = name.toLowerCase();

  if (t === "screen") {
    // 모든 화면을 「화면 진입」으로 부르면 어떤 화면인지 알 수 없다 — 이름에서 화면을 읽는다.
    const label = screenLabelKo(name, "");
    if (label) return `${label} 화면`;
    if (role === "A" || /search|list|조회/.test(n)) return "조회 화면";
    if (role === "B" || /detail|result/.test(n)) return "결과 화면";
    return "화면 진입";
  }
  if (t === "input") {
    if (/password|pwd|passwd/.test(n)) return "패스워드 입력";
    if (/user|login|account|email/.test(n)) return "로그인 아이디 입력";
    if (/customer/.test(n)) return "고객 ID 입력";
    return "입력값 입력";
  }
  if (t === "event") {
    if (/login|signin|submit|search|조회/.test(n)) return "버튼 클릭 · 진행";
    return "사용자 동작";
  }
  if (t === "validation") return "입력 검증";
  if (t === "frontend_api_call") return "화면에서 서버 요청";
  if (t === "backend_endpoint") return "서버 처리";
  if (t === "request_dto") return "요청 데이터 구성";
  if (t === "response_dto") return "응답 데이터 수신";
  if (t === "service") return "업무 서비스 처리";
  if (t === "route_transition") return "다음 화면으로 이동";
  if (t === "binding") return "결과 바인딩";
  return name || type;
}

function simplifyRef(ref: string): string {
  const testid = ref.match(/data-testid=["']([^"']+)["']/);
  if (testid) return testid[1];
  if (ref.length > 48) return `${ref.slice(0, 45)}…`;
  return ref;
}

function statusLabel(status: NarrativeStep["status"], obs: string): string {
  if (status === "success") return obs || "성공";
  if (status === "failure") return obs || "실패";
  if (status === "pending") return obs || "진행 중";
  return obs || "확인 필요";
}

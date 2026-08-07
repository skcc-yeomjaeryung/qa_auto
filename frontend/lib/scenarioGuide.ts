/**
 * 테스트 시나리오를 테스터가 읽을 수 있는 한글 안내로 바꾼다.
 *
 * `INDEX-UI-001` 같은 케이스 ID만 보여주면 무엇을 테스트하는지 알 수 없다.
 * 여기서는 저장된 시나리오 단계·케이스 분석에서 읽을 수 있는 사실만 문장으로 옮긴다.
 * 데이터에 없는 기대값·판정은 만들지 않고 확인이 필요하다고 알린다.
 */

import { serviceLabelKo } from "./scenarioLabels";

export type ScenarioGuideInput = {
  scenarioId: string;
  serviceId?: string | null;
  name?: string | null;
  unresolvedCount?: number;
  result?: {
    caseId?: string;
    testType?: string;
    journeyTitle?: string;
    name?: string;
    steps?: Array<Record<string, unknown>>;
    caseAnalysis?: {
      caseId?: string;
      testType?: string;
      targetScreen?: string;
      connectedApi?: string;
      expectedResult?: string;
      requestValues?: string;
    };
  } | null;
};

export type ScenarioGuide = {
  /** 화면 제목으로 쓸 한 문장 */
  headline: string;
  /** 이 화면이 무엇을 하는 화면인지 */
  purpose: string;
  /** 테스트가 실제로 무엇을 수행하는지 (단계 요약 문장) */
  whatWeDo: string[];
  /** 성공으로 관측되는 모습 */
  successLooksLike: string;
  /** 실패로 관측되는 모습 */
  failureLooksLike: string;
  /** 남는 증적 */
  evidenceNote: string;
  /** 실행 전 확인이 필요한 사항 (없으면 빈 배열) */
  cautions: string[];
  /** 테스트 종류 라벨 */
  kindLabel: string;
};

const UI_HINT = /UI/i;
const API_HINT = /API/i;
const E2E_HINT = /E2E|FLOW/i;

/** 라우트 경로를 화면 이름으로 — 테스터에게 "/" 는 화면 이름이 아니다 */
const ROUTE_KO: Array<[RegExp, string]> = [
  [/^\/?$|index/i, "첫 진입(메인)"],
  [/home|dashboard/i, "홈"],
  [/login|signin/i, "로그인"],
  [/signup|register/i, "회원가입"],
  [/logout|signout/i, "로그아웃"],
  [/consent|agree/i, "약관 동의"],
  [/payment|transfer/i, "송금·결제"],
  [/deposit/i, "입금"],
  [/balance/i, "잔액"],
  [/account/i, "계좌"],
  [/transaction/i, "거래내역"],
  [/profile|mypage/i, "내 정보"],
  [/search/i, "조회"],
];

/** 라우트·화면 식별자를 화면 이름으로 (플로우 노드·그래프 공용) */
export function screenLabelKo(raw: string | null | undefined, fallback = "화면"): string {
  const text = String(raw || "").trim();
  if (!text) return fallback;
  for (const [re, label] of ROUTE_KO) {
    if (re.test(text)) return label;
  }
  const last = text.split(/[/?#]/).filter(Boolean).pop();
  return last || fallback;
}

function screenKo(input: ScenarioGuideInput): string {
  const target = (input.result?.caseAnalysis?.targetScreen || "").trim();
  const blob = `${target} ${input.serviceId || ""}`;
  for (const [re, label] of ROUTE_KO) {
    if (re.test(blob)) return label;
  }
  if (target && !target.startsWith("/")) return target;
  return serviceLabelKo(input.serviceId || "", input.name || input.result?.name);
}

function kindOf(input: ScenarioGuideInput): "ui" | "api" | "e2e" {
  const blob = `${input.result?.testType || ""} ${input.result?.caseAnalysis?.testType || ""} ${
    input.result?.caseId || ""
  }`;
  if (E2E_HINT.test(blob)) return "e2e";
  if (API_HINT.test(blob)) return "api";
  if (UI_HINT.test(blob)) return "ui";
  return input.result?.caseAnalysis?.connectedApi ? "e2e" : "ui";
}

const KIND_LABEL: Record<string, string> = {
  ui: "화면 구성 확인",
  api: "서버 요청·응답 확인",
  e2e: "화면 → 서버 → 화면 관통 확인",
};

/** 셀렉터·필드명을 테스터가 아는 항목 이름으로 — 못 알아보면 원문을 그대로 둔다 */
const FIELD_KO: Array<[RegExp, string]> = [
  [/user(name)?|아이디|loginid/i, "아이디"],
  [/pass(word)?|비밀번호/i, "비밀번호"],
  [/submit|login[-_]?btn|로그인/i, "로그인"],
  [/signup|register|가입/i, "가입"],
  [/amount|금액/i, "금액"],
  [/account/i, "계좌번호"],
  [/email|메일/i, "이메일"],
  [/phone|tel/i, "연락처"],
  [/name|이름/i, "이름"],
  [/confirm|동의|agree/i, "동의"],
  [/search|검색/i, "검색어"],
];

function fieldKo(raw: string, fallback: string): string {
  const text = (raw || "").trim();
  if (!text) return fallback;
  for (const [re, label] of FIELD_KO) {
    if (re.test(text)) return label;
  }
  // 셀렉터 문법(#id, [attr], .class)은 사용자에게 의미가 없다
  if (/[#.[\]'"=>]/.test(text)) return fallback;
  return text;
}

/** 세션 선행조건·세션 확인 단계는 생성기가 만든 문장이 정확하다 (D-015) */
function presetSentence(step: Record<string, unknown>): string | null {
  const preset = typeof step.title === "string" ? step.title.trim() : "";
  if (!preset) return null;
  return isGeneratedSentence(step) ? preset : null;
}

/** 생성기가 근거와 함께 만든 문장인지 (선행 로그인 · 세션 확인 · 화면 트리거) */
function isGeneratedSentence(step: Record<string, unknown>): boolean {
  return (
    Boolean(step.precondition) ||
    Boolean(step.sessionCheck) ||
    Boolean(step.expectSessionEnded) ||
    Boolean(step.preserveTitle)
  );
}

/** 단계 하나를 사람이 읽는 한 문장으로 */
function stepSentence(step: Record<string, unknown>, screen: string): string | null {
  const action = String(step.action || "").toLowerCase();
  const target = (step.target as Record<string, unknown>) || {};
  const req = (step.request as Record<string, unknown>) || {};
  const expect = (step.expect as Record<string, unknown>) || {};
  const path = String(req.path || target.route || "");
  const method = String(req.method || "").toUpperCase();

  const preset = presetSentence(step);
  if (preset) return preset;

  if (action === "navigate") {
    // 이동 단계는 시나리오 대표 화면이 아니라 그 단계가 여는 화면을 말한다
    const routeScreen = screenLabelKo(String(target.route || ""), screen);
    return `${routeScreen} 화면을 브라우저로 엽니다${path ? ` (경로 ${path})` : ""}`;
  }
  if (action === "assert_absent") {
    const selectors = (target.selectors as string[]) || [];
    return `동작 후 사라져야 할 요소가 실제로 사라졌는지 확인합니다${
      selectors.length ? ` (${selectors.length}개 항목)` : ""
    }`;
  }
  if (action === "fill") {
    const field = fieldKo(String(target.value ?? target.name ?? ""), "입력 항목");
    return `${field}에 추천 입력값을 채웁니다`;
  }
  if (action === "click") {
    const label = fieldKo(String(target.value ?? target.text ?? ""), "제출");
    return `${label} 버튼을 눌러 다음 단계로 넘어갑니다`;
  }
  if (action === "wait_for_response") {
    return `서버 응답을 기다립니다${method || path ? ` (${`${method} ${path}`.trim()})` : ""}`;
  }
  if (action === "verify_binding") {
    const field = String(expect.field || target.value || "결과 값");
    return `응답으로 받은 ${field}이 화면에 제대로 표시되는지 대조합니다`;
  }
  if (action === "assert_visible") {
    const selectors = (target.selectors as string[]) || [];
    return `${screen} 화면에 필요한 요소가 보이는지 확인합니다${
      selectors.length ? ` (${selectors.length}개 항목)` : ""
    }`;
  }
  if (action === "screenshot") return "화면을 스크린샷으로 남깁니다";
  return null;
}

/** 분석이 만든 기대 결과 문장은 같은 요소명이 반복되고 길다 — 중복을 접고 길이를 줄인다. */
function tidyExpected(expected: string, limit = 6): string {
  const match = expected.match(/^(.*?)\s*(이\(가\)\s*표시되어야 함.*)$/);
  const listPart = match ? match[1] : expected;
  const tailPart = match ? ` ${match[2]}` : "";
  const items = listPart
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (items.length < 2) return expected;
  const unique = Array.from(new Set(items));
  const shown = unique.slice(0, limit).join(", ");
  const rest = unique.length - limit;
  return `${shown}${rest > 0 ? ` 외 ${rest}개` : ""}${tailPart}`;
}

export type ScenarioFlowNode = {
  key: string;
  /** 컴포넌트 제목 — 「로그인 화면」처럼 무엇을 다루는 단계인지 */
  label: string;
  /** 한 문장 설명 */
  text: string;
  /** 이 단계가 넣는 값 (필드 · 값) */
  inputs: Array<[string, string]>;
  kind: "screen" | "input" | "action" | "server" | "check";
};

const ACTION_KIND: Record<string, ScenarioFlowNode["kind"]> = {
  navigate: "screen",
  fill: "input",
  type: "input",
  select: "input",
  check: "input",
  click: "action",
  press: "action",
  wait_for_response: "server",
  verify_binding: "check",
  assert_visible: "check",
  assert_absent: "check",
  screenshot: "check",
};

/**
 * 시나리오 단계를 플로우 노드(제목 · 설명 · 입력값)로 만든다.
 *
 * 모든 노드를 「화면 진입 → 화면」으로 보여주면 무엇을 하는 단계인지 알 수 없다.
 * 여기서는 단계의 action·target·route에서 읽히는 사실만 한글 제목으로 옮긴다.
 */
export function buildScenarioFlowNodes(
  input: ScenarioGuideInput,
  runInputs: Record<string, unknown> = {}
): ScenarioFlowNode[] {
  const screen = screenKo(input);
  const steps = input.result?.steps || [];
  return steps.map((step, index) => {
    const action = String((step as Record<string, unknown>).action || "").toLowerCase();
    const target = ((step as Record<string, unknown>).target as Record<string, unknown>) || {};
    const req = ((step as Record<string, unknown>).request as Record<string, unknown>) || {};
    const kind = ACTION_KIND[action] || "check";
    const route = String(target.route || "");
    const rawField = String(target.value ?? target.name ?? target.text ?? "");
    const field = fieldKo(rawField, "입력 항목");

    const stepRecord = step as Record<string, unknown>;
    const isSessionStep = isGeneratedSentence(stepRecord);
    const preservedTitle =
      isSessionStep && typeof stepRecord.title === "string" ? stepRecord.title.trim() : "";
    let label: string;
    // 분석기가 업무 근거와 함께 보존을 요청한 제목은 action별 범용 문구보다 우선한다.
    // capture/검증 단계가 전부 「로그인 세션 확인」으로 보이던 정보 손실도 막는다.
    if (preservedTitle) label = preservedTitle;
    else if (kind === "screen") label = `${screenLabelKo(route, screen)} 화면`;
    else if (kind === "input") label = `${field} 입력`;
    else if (kind === "action") {
      // 선행조건·화면 트리거 클릭은 selector 추측 대신 생성기 문장을 쓴다 (D-015)
      const title = typeof stepRecord.title === "string" ? stepRecord.title.trim() : "";
      label = isSessionStep && title ? title : `${fieldKo(rawField, "제출")} 클릭`;
    } else if (kind === "server")
      label = `서버 호출 ${String(req.method || "").toUpperCase() || ""}`.trim();
    else if (action === "verify_binding") label = "결과 값 대조";
    else if (action === "assert_absent") label = "사라짐 확인";
    else if (isSessionStep) label = "로그인 세션 확인";
    else label = `${screen} 화면 확인`;

    const inputs: Array<[string, string]> = [];
    if (kind === "input") {
      const key = Object.keys(runInputs).find(
        (k) => k.toLowerCase().replace(/[^a-z0-9가-힣]/g, "") === rawField.toLowerCase().replace(/[^a-z0-9가-힣]/g, "")
      );
      const value = key ? runInputs[key] : (step as Record<string, unknown>).value;
      inputs.push([field, value === undefined || value === "" ? "(빈 값)" : String(value)]);
    }
    if (kind === "screen" && route) inputs.push(["경로", route]);
    if (kind === "server" && (req.method || req.path)) {
      inputs.push(["요청", `${String(req.method || "").toUpperCase()} ${String(req.path || "")}`.trim()]);
    }

    return {
      key: String((step as Record<string, unknown>).id || `step-${index}`),
      label,
      text: stepSentence(step, screen) || label,
      inputs,
      kind,
    };
  });
}

export function buildScenarioGuide(input: ScenarioGuideInput): ScenarioGuide {
  const screen = screenKo(input);
  const kind = kindOf(input);
  const kindLabel = KIND_LABEL[kind];
  const caseId = input.result?.caseId || input.result?.caseAnalysis?.caseId || input.scenarioId;
  const steps = input.result?.steps || [];
  const api = input.result?.caseAnalysis?.connectedApi;
  const expected = input.result?.caseAnalysis?.expectedResult;

  const sentences = steps
    .map((step) => stepSentence(step, screen))
    .filter((s): s is string => Boolean(s));

  const whatWeDo = sentences.length
    ? sentences
    : kind === "ui"
      ? [
          `${screen} 화면을 실제 브라우저로 엽니다`,
          "화면에 있어야 할 입력 항목과 버튼이 보이는지 확인합니다",
          "확인한 화면을 스크린샷으로 남깁니다",
        ]
      : [
          `${screen} 화면을 열고 추천 입력값을 채웁니다`,
          api ? `${api} 요청이 나가고 응답이 오는지 확인합니다` : "서버 요청과 응답을 관측합니다",
          "응답 값이 다음 화면에 제대로 표시되는지 대조합니다",
        ];

  const headline =
    kind === "ui"
      ? `${screen} 화면이 정상적으로 구성되는지 확인합니다`
      : kind === "api"
        ? `${screen} 요청이 정상 응답을 주는지 확인합니다`
        : `${screen} 화면에서 서버 요청까지 이어지는 흐름을 확인합니다`;

  const purpose =
    `이 화면은 테스트 케이스 ${caseId} 한 건을 실행하고 결과를 확인하는 화면입니다. ` +
    `테스트 종류는 「${kindLabel}」이며, 실제 브라우저로 ${screen} 화면을 열어 동작을 관측합니다.`;

  const successLooksLike = expected
    ? `분석에서 기대 결과로 「${tidyExpected(expected)}」가 확인되었습니다. 이대로 관측되면 성공 후보입니다.`
    : kind === "ui"
      ? `${screen} 화면이 열리고, 확인 대상 요소가 모두 화면에 보이면 성공으로 관측됩니다.`
      : `요청이 정상 응답(2xx)을 받고, 응답 값이 다음 화면에 그대로 표시되면 성공으로 관측됩니다.`;

  const failureLooksLike =
    kind === "ui"
      ? `화면이 열리지 않거나, 확인 대상 요소를 화면에서 찾지 못하면 실패로 관측됩니다. 요소가 아예 없으면 근거 없음(missing_data)으로 표시합니다.`
      : `요청이 실패(4xx·5xx)하거나 응답이 오지 않을 때, 또는 응답 값과 화면에 표시된 값이 다를 때 실패로 관측됩니다.`;

  const evidenceNote =
    "실행하면 단계별 스크린샷, 화면 구성(DOM) 기록, 서버 요청·응답, 실행 로그가 증적으로 저장됩니다. " +
    "증적은 실행 이력과 증적 메뉴에서 다시 확인할 수 있습니다.";

  const cautions: string[] = [];
  if ((input.unresolvedCount ?? 0) > 0) {
    cautions.push(
      `근거가 부족해 확인이 필요한 항목이 ${input.unresolvedCount}건 있습니다. 입력값을 검토한 뒤 실행하세요.`,
    );
  }
  if (!expected) {
    cautions.push(
      "분석 결과에 확정된 기대값이 없어, 성공 여부는 관측 결과를 보고 담당자가 판단해야 합니다.",
    );
  }
  cautions.push("이 화면의 결과는 관측 자료입니다. 최종 합격·불합격 판정은 담당자가 승인 검토에서 확정합니다.");

  return {
    headline,
    purpose,
    whatWeDo,
    successLooksLike,
    failureLooksLike,
    evidenceNote,
    cautions,
    kindLabel,
  };
}

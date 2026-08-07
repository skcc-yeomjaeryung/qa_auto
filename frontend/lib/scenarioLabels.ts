/** Korean display helpers for scenario list / detail (never invent missing facts). */

const TOKEN_KO: Array<[RegExp, string]> = [
  [/customer/i, "고객"],
  [/search|조회/i, "조회"],
  [/login|signin|auth/i, "로그인"],
  [/deposit|입금/i, "입금"],
  [/payment|결제|이체/i, "결제"],
  [/balance|잔액/i, "잔액"],
  [/transaction|거래/i, "거래"],
  [/transfer|송금/i, "송금"],
  [/account|계좌/i, "계좌"],
  [/home|dashboard|main/i, "홈"],
  [/signup|register|가입/i, "가입"],
];

/** 화면 ID를 테스터가 아는 화면 이름으로 (index-ui → 첫 진입(메인)) */
const SCREEN_KO: Array<[RegExp, string]> = [
  [/^index([-_]|$)|^root([-_]|$)/i, "첫 진입(메인)"],
  [/^home([-_]|$)|dashboard/i, "홈"],
  [/login|signin/i, "로그인"],
  [/signup|register/i, "회원가입"],
  [/consent|agree|terms/i, "약관 동의"],
  [/payment|transfer/i, "송금·결제"],
  [/deposit/i, "입금"],
  [/^account/i, "계좌"],
  [/transaction/i, "거래내역"],
];

/** 케이스 ID 접두어(LOGOUT-E2E-001)가 있으면 화면 이름은 그쪽이 정확하다 */
function caseLabelKo(caseId?: string | null): string | null {
  const prefix = String(caseId || "")
    .split("-")[0]
    .toLowerCase();
  if (!prefix) return null;
  if (/^logout|signout$/.test(prefix)) return "로그아웃";
  for (const [re, label] of SCREEN_KO) {
    if (re.test(prefix)) return label;
  }
  for (const [re, label] of TOKEN_KO) {
    if (re.test(prefix)) return label;
  }
  return null;
}

export function serviceLabelKo(serviceId: string, name?: string | null): string {
  for (const [re, label] of SCREEN_KO) {
    if (re.test(serviceId)) return label;
  }
  const blob = `${serviceId} ${name || ""}`;
  const hits: string[] = [];
  for (const [re, label] of TOKEN_KO) {
    if (re.test(blob) && !hits.includes(label)) hits.push(label);
  }
  if (hits.length) return hits.slice(0, 3).join(" ");
  if (serviceId === "multi") return "다중 API";
  if (serviceId === "customer-search") return "고객 조회";
  return serviceId.replace(/[-_]/g, " ").trim() || "API";
}

export function scenarioTitleKo(row: {
  name?: string | null;
  serviceId?: string | null;
  result?: {
    serviceLabelKo?: string;
    name?: string;
    businessJourney?: boolean;
    caseId?: string;
    testType?: string;
    caseAnalysis?: { caseId?: string; testType?: string; expectedResult?: string };
  };
}): string {
  const generatedBusinessTitle = row.result?.name || row.name;
  if (
    row.result?.businessJourney &&
    generatedBusinessTitle &&
    !/A→API→B|draft/i.test(generatedBusinessTitle) &&
    !/^SCN-/i.test(generatedBusinessTitle)
  ) {
    return generatedBusinessTitle;
  }
  const caseId = row.result?.caseId || row.result?.caseAnalysis?.caseId;
  const testType = row.result?.testType || row.result?.caseAnalysis?.testType || "";
  // 케이스 ID는 별도 셀·부제로 이미 보인다. 제목은 무엇을 검증하는지 문장으로 쓴다.
  if (caseId && /UI/.test(testType || caseId)) {
    const label =
      caseLabelKo(caseId) || serviceLabelKo(row.serviceId || "", row.name || row.result?.name);
    return `${label} 화면이 정상 구성되는지 확인`;
  }
  if (caseId) {
    const label =
      caseLabelKo(caseId) || serviceLabelKo(row.serviceId || "", row.name || row.result?.name);
    if (/API/i.test(testType)) return `${label} 서버 요청·응답 확인`;
    if (/E2E|FLOW/i.test(testType)) return `${label} 화면→서버→화면 관통 확인`;
    const fromResult = row.result?.name;
    if (fromResult && !fromResult.includes(caseId)) return fromResult;
    return `${label} 동작 확인`;
  }
  const fromResult = row.result?.serviceLabelKo || row.result?.name;
  if (fromResult && !/A→API→B|draft/i.test(fromResult)) return fromResult;
  if (row.name && !/A→API→B|draft/i.test(row.name) && !/^SCN-/i.test(row.name)) {
    return row.name;
  }
  return `${serviceLabelKo(row.serviceId || "", row.name)} 시나리오`;
}

export function narrateScenarioSteps(
  steps: Array<Record<string, unknown>> | undefined,
): Array<{ order: number; title: string; detail: string }> {
  if (!steps?.length) {
    return [
      {
        order: 1,
        title: "분석 기반 시나리오 초안",
        detail: "화면 입력 → API 호출 → 결과 화면 확인 흐름으로 생성됩니다.",
      },
    ];
  }
  return steps.map((s, i) => {
    const action = String(s.action || "").toLowerCase();
    const title =
      (typeof s.title === "string" && s.title) ||
      defaultStepTitle(action, s);
    const detail =
      (typeof s.description === "string" && s.description) ||
      (typeof s.note === "string" && s.note) ||
      stepDetail(action, s);
    return { order: i + 1, title, detail };
  });
}

function defaultStepTitle(action: string, step: Record<string, unknown>): string {
  const target = (step.target as Record<string, unknown>) || {};
  const req = (step.request as Record<string, unknown>) || {};
  const path = String(req.path || target.route || target.value || "");
  if (action === "navigate") return `화면으로 이동${path ? ` (${path})` : ""}`;
  if (action === "fill") return `입력값을 채웁니다 (${String(target.value || "field")})`;
  if (action === "click") return "버튼을 눌러 다음 단계로 진행합니다";
  if (action === "wait_for_response")
    return `API 응답을 기다립니다 (${String(req.method || "")} ${path})`.trim();
  if (action === "verify_binding") {
    const field = ((step.expect as Record<string, unknown>) || {}).field;
    return `결과 바인딩을 확인합니다 (${String(field || target.value || "")})`;
  }
  if (action === "assert_visible") {
    const sels = (target.selectors as string[]) || [];
    return `UI 구성 표시를 확인합니다${sels.length ? ` (${sels.slice(0, 3).join(", ")})` : ""}`;
  }
  return "테스트 단계를 수행합니다";
}

function stepDetail(action: string, step: Record<string, unknown>): string {
  const refs = step.evidenceRefs;
  if (Array.isArray(refs) && refs.length) return `근거: ${refs.slice(0, 3).join(", ")}`;
  if (action === "navigate") return "대상 화면을 엽니다";
  if (action === "fill") return "입력 필드를 채웁니다";
  if (action === "click") return "사용자 클릭 이벤트를 발생합니다";
  if (action === "wait_for_response") return "네트워크 응답을 관측합니다";
  if (action === "verify_binding") return "후속 화면 데이터 바인딩을 대조합니다";
  return "";
}

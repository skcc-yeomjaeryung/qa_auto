/** 증적 파일명을 테스터가 읽는 한국어 라벨로 옮긴다 (파일명 SSOT: browser_execute/execute_run). */
const SHOT_LABELS: Array<[RegExp, string]> = [
  [/-screen\.png$/i, "화면 진입 캡쳐"],
  [/-after-input\.png$/i, "입력 직후 화면"],
  [/-input-completed\.png$/i, "입력 완료 화면"],
  [/-submitted\.png$/i, "입력 섬밋 직후 화면"],
  [/-composition\.png$/i, "화면 구성 확인 캡쳐"],
  [/-result\.png$/i, "결과 화면"],
  [/-failure\.png$/i, "실패 시점 화면"],
  [/-extra\.png$/i, "추가 캡쳐"],
];

export function shotLabelKo(fileName: string): string {
  for (const [pattern, label] of SHOT_LABELS) {
    if (pattern.test(fileName)) return label;
  }
  return fileName;
}

/** 입력 바인딩 출처 라벨 — 값이 어디서 왔는지 화면에 그대로 보여준다. */
export const BIND_SOURCE_LABEL: Record<string, string> = {
  input_profile: "실행 입력값",
  connection_account: "연결 계정",
  llm_dom_bind: "LLM 제안값",
  derived_synthetic: "자동 생성값",
  missing_data: "근거 없음",
};

export type MissingEvidenceDetail = {
  code: string;
  label: string;
  guidance: string;
  section: string;
};

const MISSING_EVIDENCE_DETAILS: Record<string, Omit<MissingEvidenceDetail, "code">> = {
  "criterion:C-collection-change": {
    label: "업무 처리 전후의 목록 변화를 확인하지 못했습니다",
    guidance: "결과 화면에서 새 거래나 변경된 항목이 표시됐는지 확인해 주세요.",
    section: "실행 결과",
  },
  "criterion:C-state-delta": {
    label: "업무 처리 전후의 화면 값 변화를 확인하지 못했습니다",
    guidance: "잔액·상태·건수처럼 변경돼야 하는 값이 실제로 달라졌는지 확인해 주세요.",
    section: "실행 결과",
  },
  "criterion:C-success-message": {
    label: "완료 안내 문구를 화면에서 확인하지 못했습니다",
    guidance: "업무 완료 또는 오류 안내가 화면에 표시됐는지 확인해 주세요.",
    section: "실행 결과",
  },
  submit_blocked_destructive: {
    label: "데이터를 변경하는 제출 단계가 안전 정책에 따라 실행되지 않았습니다",
    guidance: "실제 데이터 변경이 허용되는 테스트인지 확인한 뒤 담당자가 다시 실행해 주세요.",
    section: "실행 단계",
  },
  input_precondition_invalid: {
    label: "현재 테스트 계정 상태로는 입력값을 제출할 수 없습니다",
    guidance: "계정 잔액·허용 범위를 확인하고 테스트 데이터를 초기화하거나 충전한 뒤 다시 실행해 주세요.",
    section: "실행 선행조건",
  },
  backend_telemetry: {
    label: "서버 처리 추적 정보를 수집하지 못했습니다",
    guidance: "실행 ID가 서버 로그까지 전달됐는지 확인해 주세요.",
    section: "서버 검증",
  },
  input_profile: {
    label: "실행에 사용한 입력값 묶음 정보가 연결되지 않았습니다",
    guidance: "어떤 입력값으로 실행했는지 입력 프로필을 확인해 주세요.",
    section: "실행 입력",
  },
  backend_request: {
    label: "서버로 보낸 요청 내용을 수집하지 못했습니다",
    guidance: "Network 증적 또는 서버 요청 로그를 확인해 주세요.",
    section: "서버 검증",
  },
  backend_response: {
    label: "서버 응답 내용을 수집하지 못했습니다",
    guidance: "응답 상태와 본문이 기록됐는지 확인해 주세요.",
    section: "서버 검증",
  },
  backend_events: {
    label: "서버 내부 처리 이벤트를 수집하지 못했습니다",
    guidance: "실행 ID 기준 서버 이벤트 로그가 남았는지 확인해 주세요.",
    section: "서버 검증",
  },
  httpStatus: {
    label: "서버 응답 상태를 확인하지 못했습니다",
    guidance: "Network 기록에서 응답 상태 코드가 수집됐는지 확인해 주세요.",
    section: "기술 검증",
  },
};

export function missingEvidenceDetail(code: string): MissingEvidenceDetail {
  if (code.startsWith("run_status:")) {
    const status = code.split(":", 2)[1] || "확인 필요";
    return {
      code,
      label: "자동 실행에서 확인이 필요한 결과가 발생했습니다",
      guidance: `실행 상태(${status})와 단계별 관측 내용을 확인해 주세요.`,
      section: "실행 결과",
    };
  }
  if (code.startsWith("locator:")) {
    return {
      code,
      label: "화면에서 확인 대상 요소를 찾지 못했습니다",
      guidance: "화면 구조가 변경됐는지 또는 대상 요소가 실제로 표시됐는지 확인해 주세요.",
      section: "화면 검증",
    };
  }
  return {
    code,
    ...(MISSING_EVIDENCE_DETAILS[code] ?? {
      label: "자동 검증에 필요한 자료를 충분히 수집하지 못했습니다",
      guidance: "실행 단계와 증적 패키지에서 관련 자료가 남았는지 확인해 주세요.",
      section: "추가 확인",
    }),
  };
}

export function humanizeMissingEvidence(code: string): string {
  return missingEvidenceDetail(code).label;
}

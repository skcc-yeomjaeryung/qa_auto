export type ScenarioStatus = "draft" | "ready" | "running" | "review";

export type ScenarioRow = {
  id: string;
  name: string;
  path: string;
  status: ScenarioStatus;
  lastRun: string;
  owner: string;
  coverage: number;
  tags: string[];
};

/** Dashboard summary rows — replaced by live API when available. */
export const scenarioRows: ScenarioRow[] = [];

export const statusLabel: Record<ScenarioStatus, string> = {
  draft: "작성중",
  ready: "준비됨",
  running: "실행중",
  review: "검토중",
};

/**
 * 실행 결과 표기.
 *
 * 「성공」이라고 단정하지 않는다 — 화면·응답이 기대대로 관측됐다는 뜻이며
 * 합격 확정은 담당자(HITL)가 한다.
 */
export const outcomeLabel: Record<string, string> = {
  success: "정상 관측",
  be_error: "서버 오류 관측",
  business_error: "업무 오류 관측",
  fe_error: "화면 오류 관측",
  unknown: "판정 불가",
};

/** 실행 상태 코드를 담당자가 읽는 문장으로 */
const runStateSentence: Record<string, string> = {
  WAITING_FOR_REVIEW: "화면과 응답을 끝까지 관측했습니다",
  AUTO_FAILED: "실행 중 막힌 단계가 있어 실패로 관측됐습니다",
  CANCELLED: "실행을 중단했습니다",
  RUNNING: "아직 실행 중입니다",
  PREPARING: "실행을 준비하고 있습니다",
  QUEUED: "실행을 기다리고 있습니다",
};

/**
 * 실행 관측 요약을 담당자 문장으로 옮긴다.
 *
 * 실행 산출물의 요약문에는 `기술 실행 관측 완료` · `기술 상태=...` 같은 내부 표기와
 * 화면에 이미 안내된 HITL 문장이 섞여 있다. 원문은 증적에 그대로 남기고,
 * 화면에는 사람이 읽는 문장만 보여준다.
 */
export function humanizeObservation(text: string | null | undefined): string {
  if (!text) return "";
  const stateMatch = text.match(/기술 상태=([A-Z_]+)/);
  if (stateMatch) {
    return runStateSentence[stateMatch[1]] ?? "실행 관측 자료만 있습니다";
  }
  const cleaned = text
    .replace(/기술 실행 관측 완료\.?/g, runStateSentence.WAITING_FOR_REVIEW + ".")
    .replace(/기술 실행 완료/g, "실행 완료")
    // 「Pass/Fail·배포는 HITL에서 확정합니다」는 화면 안내문에 이미 있다
    .replace(/Pass\/Fail[^.]*확정합니다\.?/g, "")
    .replace(/\s{2,}/g, " ")
    .trim();
  return cleaned;
}

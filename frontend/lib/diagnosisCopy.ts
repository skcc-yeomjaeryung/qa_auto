export type DiagnosisCopy = {
  sectionKicker: string;
  primaryQuestion: string;
  causeQuestion: string;
  actionTitle: string;
  emptyAction: string;
  retestLabel: string;
  handoffLabel: string;
  reviewTitle: string;
  reviewHint: string;
};

export function getDiagnosisCopy(outcome?: string | null): DiagnosisCopy {
  if (outcome === "success") {
    return {
      sectionKicker: "성공 관측과 최종 검토",
      primaryQuestion: "무엇이 정상 관측됐나요?",
      causeQuestion: "어떤 근거로 성공을 확인했나요?",
      actionTitle: "담당자는 무엇을 확인하나요?",
      emptyAction: "자동 관측 근거와 증적을 확인한 뒤 최종 결과를 판정하세요.",
      retestLabel: "최종 검토 조건",
      handoffLabel: "담당자 검토 요청",
      reviewTitle: "담당자가 확인할 근거",
      reviewHint: "정상 관측과 증적을 확인한 뒤 최종 판정을 확정합니다.",
    };
  }
  if (outcome === "failure") {
    return {
      sectionKicker: "실패 원인과 후속 조치",
      primaryQuestion: "무슨 문제가 있었나요?",
      causeQuestion: "왜 이런 오류가 발생했나요?",
      actionTitle: "어떻게 해결하나요?",
      emptyAction: "실패 단계와 증적을 개발·QA 담당자에게 전달해 조치 내용을 확인하세요.",
      retestLabel: "재검증 조건",
      handoffLabel: "담당자 전달문",
      reviewTitle: "담당자가 확인할 대상",
      reviewHint: "오류·기대 불충족·근거 부족을 먼저 확인합니다.",
    };
  }
  return {
    sectionKicker: "확인 필요 원인과 근거 보강",
    primaryQuestion: "무엇을 확인해야 하나요?",
    causeQuestion: "왜 판정이 보류됐나요?",
    actionTitle: "어떤 근거를 보강하나요?",
    emptyAction: "누락된 실행 단계와 증적을 보강한 뒤 다시 확인하세요.",
    retestLabel: "재확인 조건",
    handoffLabel: "담당자 확인 요청",
    reviewTitle: "담당자가 확인할 대상",
    reviewHint: "판정 보류 원인과 누락된 근거를 먼저 확인합니다.",
  };
}

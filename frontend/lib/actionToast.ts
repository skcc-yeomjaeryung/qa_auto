export type ActionToastTone = "progress" | "success" | "error" | "info";

export type ActionToastInput = {
  id?: string;
  title: string;
  message: string;
  tone?: ActionToastTone;
  durationMs?: number;
};

export const ACTION_TOAST_EVENT = "ai-test-action-toast";

function generatedToastId(): string {
  const suffix = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `action-toast-${suffix}`;
}

/**
 * 앱 전체 공통 장시간·대량 작업 알림.
 * 같은 id를 다시 보내면 시작 → 완료/실패 상태가 한 자리에서 갱신된다.
 */
export function showActionToast(input: ActionToastInput): string {
  const id = input.id || generatedToastId();
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent<ActionToastInput>(ACTION_TOAST_EVENT, {
      detail: { ...input, id },
    }));
  }
  return id;
}

export function actionToastId(action: string, target: string): string {
  return `action-toast:${action}:${target}`;
}

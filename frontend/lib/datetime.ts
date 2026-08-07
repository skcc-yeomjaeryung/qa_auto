/**
 * 목록·상세 화면의 시간 표기 SSOT.
 * 모든 실행 시간은 `yyyy-mm-dd hh:mm:ss` (로컬 시간) 로 보여준다.
 */

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

export function formatDateTime(value?: string | number | Date | null, fallback = "—"): string {
  if (value === null || value === undefined || value === "") return fallback;
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return typeof value === "string" ? value : fallback;
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  );
}

export function formatDateOnly(value?: string | number | Date | null, fallback = "—"): string {
  const full = formatDateTime(value, fallback);
  return full === fallback ? fallback : full.slice(0, 10);
}

/** 실행 소요 시간 — 시작·종료가 모두 있을 때만 계산한다 (없으면 null). */
export function formatDuration(startedAt?: string | null, endedAt?: string | null): string | null {
  if (!startedAt || !endedAt) return null;
  const start = new Date(startedAt).getTime();
  const end = new Date(endedAt).getTime();
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return null;
  const seconds = Math.round((end - start) / 1000);
  if (seconds < 60) return `${seconds}초`;
  return `${Math.floor(seconds / 60)}분 ${pad(seconds % 60)}초`;
}

"use client";

/**
 * 화면별 검색 입력 — 화면 제목 기준 가장 우측에 놓는다.
 *
 * 상단 전역 검색 한 칸으로는 화면마다 다른 속성(프로젝트명·시나리오 케이스·실행 ID …)을
 * 찾을 수 없어, 각 화면이 자기 목록의 의미 있는 컬럼을 직접 걸러낸다.
 */
export function ScreenSearch({
  value,
  onChange,
  placeholder,
  label = "화면 내 검색",
  testId = "screen-search",
  hint,
}: {
  value: string;
  onChange: (next: string) => void;
  /** 이 화면에서 무엇으로 찾을 수 있는지 알려준다 */
  placeholder: string;
  label?: string;
  testId?: string;
  hint?: string;
}) {
  return (
    <div className="screen-search-wrap">
      <label className="screen-search">
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          aria-hidden
        >
          <circle cx="11" cy="11" r="7" />
          <path d="M20 20l-3.6-3.6" />
        </svg>
        <input
          type="search"
          value={value}
          placeholder={placeholder}
          aria-label={label}
          onChange={(e) => onChange(e.target.value)}
          data-testid={testId}
        />
        {value && (
          <button
            type="button"
            className="screen-search-clear"
            onClick={() => onChange("")}
            aria-label="검색어 지우기"
          >
            ×
          </button>
        )}
      </label>
      {hint && <span className="screen-search-hint">{hint}</span>}
    </div>
  );
}

/** 여러 필드를 한 번에 부분 일치로 대조 */
export function matchesQuery(query: string, ...fields: Array<unknown>): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return fields.some((f) => String(f ?? "").toLowerCase().includes(q));
}

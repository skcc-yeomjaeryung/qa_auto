"use client";

import Link from "next/link";

/**
 * 화면 뎁스 표기 — 꺾쇠(›)로 상위 → 현재를 잇는다.
 * 상세 화면은 어떤 대상(저장소·시나리오)의 상세인지 라벨에 담는다.
 * 예: 테스트 시나리오 › Bank of Anthos 테스트 시나리오 상세 › 건별 테스트
 */
export type Crumb = {
  label: string;
  href?: string;
};

export function Breadcrumbs({
  trail,
  testId = "breadcrumbs",
}: {
  trail: Crumb[];
  testId?: string;
}) {
  const items = trail.filter((c) => c.label);
  return (
    <nav className="crumbs" aria-label="현재 위치" data-testid={testId}>
      {items.map((crumb, index) => {
        const last = index === items.length - 1;
        return (
          <span className="crumbs-item" key={`${crumb.label}-${index}`}>
            {crumb.href && !last ? (
              <Link className="crumbs-link" href={crumb.href}>
                {crumb.label}
              </Link>
            ) : (
              <span className={last ? "crumbs-current" : "crumbs-text"} aria-current={last ? "page" : undefined}>
                {crumb.label}
              </span>
            )}
            {!last && (
              <span className="crumbs-sep" aria-hidden="true">
                ›
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
}

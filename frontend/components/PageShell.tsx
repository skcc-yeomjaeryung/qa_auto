"use client";

import type { ReactNode } from "react";

/**
 * 공통 화면 골격 — header(고정) / center(스크롤) / footer(sticky CTA).
 * 작업 완료 후 다음 CTA는 footer에만 둔다 (프레임 안 중복 버튼 금지).
 */
export function PageShell({
  header,
  children,
  footer,
  className = "",
  testId,
}: {
  header?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
  testId?: string;
}) {
  return (
    <section
      className={`page-shell table-workspace enterprise-page anim-fade-in ${className}`.trim()}
      data-testid={testId ?? "page-shell"}
    >
      <div className="page-shell-card content-card enterprise-card fill-center">
        {header ? <div className="page-shell-header">{header}</div> : null}
        <div className="page-shell-center">{children}</div>
        {footer ? <div className="page-shell-footer-slot">{footer}</div> : null}
      </div>
    </section>
  );
}

/** 스크롤과 무관하게 하단에 고정되는 CTA 바 */
export function PageStickyFooter({
  note,
  actions,
  testId,
  className = "",
}: {
  note?: ReactNode;
  actions: ReactNode;
  testId?: string;
  className?: string;
}) {
  return (
    <footer
      className={`page-sticky-footer ${className}`.trim()}
      data-testid={testId ?? "page-sticky-footer"}
    >
      {note ? <div className="page-footer-note">{note}</div> : <span className="page-footer-note-spacer" />}
      <div className="page-footer-actions">{actions}</div>
    </footer>
  );
}

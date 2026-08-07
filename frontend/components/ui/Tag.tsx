"use client";

import type { ReactNode } from "react";

export type UiTagTone = "neutral" | "positive" | "negative" | "warning";

/** Stripe SaaS Tag — Figma `PpfVifGgaC7AbPgMF3yd9T` · `19:1099` / `36:354` */
export function Tag({
  children,
  tone = "neutral",
  withIcon = false,
  className = "",
}: {
  children: ReactNode;
  tone?: UiTagTone;
  withIcon?: boolean;
  className?: string;
}) {
  return (
    <span className={`ui-tag is-${tone} ${withIcon ? "has-icon" : ""} ${className}`.trim()}>
      <span>{children}</span>
      {withIcon && tone === "positive" ? (
        <img src="/icons/saas/check-thin.svg" width={16} height={16} alt="" />
      ) : null}
    </span>
  );
}

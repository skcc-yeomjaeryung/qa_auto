"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { BusyIndicator } from "../ProgressBar";

export type UiButtonVariant = "primary" | "secondary" | "ghost";
export type UiButtonSize = "sm" | "md" | "lg";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: UiButtonVariant;
  size?: UiButtonSize;
  fullWidth?: boolean;
  busy?: boolean;
  children: ReactNode;
};

/** Stripe SaaS kit Button — Figma `PpfVifGgaC7AbPgMF3yd9T` · `34:1502` / `19:614` */
export function Button({
  variant = "primary",
  size = "md",
  fullWidth = false,
  busy = false,
  className = "",
  type = "button",
  disabled,
  children,
  ...rest
}: Props) {
  const classes = [
    "ui-btn",
    `ui-btn-${variant}`,
    `ui-btn-${size}`,
    fullWidth ? "is-full" : "",
    busy ? "is-busy" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button type={type} className={classes} disabled={disabled || busy} aria-busy={busy || undefined} {...rest}>
      {busy ? <BusyIndicator size={size === "sm" ? 12 : 14} /> : null}
      <span className="ui-btn-label">{children}</span>
    </button>
  );
}

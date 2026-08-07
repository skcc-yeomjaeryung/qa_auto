"use client";

import { useId, type InputHTMLAttributes } from "react";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "size"> & {
  label?: string;
};

/** Stripe SaaS Checkbox — Figma `PpfVifGgaC7AbPgMF3yd9T` · `35:2069` / `34:1487` */
export function Checkbox({ label, className = "", id, checked, ...rest }: Props) {
  const autoId = useId();
  const inputId = id ?? (rest.name ? String(rest.name) : autoId);
  return (
    <label className={`ui-check ${className}`.trim()} htmlFor={inputId}>
      <input id={inputId} type="checkbox" className="ui-check-input" checked={checked} {...rest} />
      <span className={`ui-check-box ${checked ? "is-on" : ""}`} aria-hidden>
        {checked ? (
          <img src="/icons/saas/check-white.svg" width={12} height={12} alt="" />
        ) : null}
      </span>
      {label ? <span className="ui-check-label">{label}</span> : null}
    </label>
  );
}

"use client";

import type { InputHTMLAttributes, ReactNode } from "react";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "size"> & {
  label: string;
  hint?: ReactNode;
  action?: ReactNode;
  error?: string | null;
  trailing?: ReactNode;
};

/** Stripe SaaS kit Input Group — Figma `PpfVifGgaC7AbPgMF3yd9T` · `34:1460` */
export function InputField({
  label,
  hint,
  action,
  error,
  trailing,
  className = "",
  id,
  ...rest
}: Props) {
  const inputId = id ?? rest.name ?? undefined;

  return (
    <label className={`ui-field ${className}`.trim()} htmlFor={inputId}>
      <span className="ui-field-head">
        <span className="ui-field-label">{label}</span>
        {action ? <span className="ui-field-action">{action}</span> : null}
      </span>
      <span className={`ui-field-control ${trailing ? "has-trail" : ""}`}>
        <input id={inputId} className="ui-input" {...rest} />
        {trailing ? <span className="ui-field-trail">{trailing}</span> : null}
      </span>
      {hint ? <span className="ui-field-hint">{hint}</span> : null}
      {error ? (
        <span className="ui-field-error" data-testid="ui-field-error">
          {error}
        </span>
      ) : null}
    </label>
  );
}

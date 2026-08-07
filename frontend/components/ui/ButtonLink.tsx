import Link from "next/link";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import type { UiButtonSize, UiButtonVariant } from "./Button";

type Props = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & {
  href: string;
  variant?: UiButtonVariant;
  size?: UiButtonSize;
  fullWidth?: boolean;
  children: ReactNode;
};

/** Link counterpart of the Figma-mapped shared Button component. */
export function ButtonLink({
  href,
  variant = "primary",
  size = "md",
  fullWidth = false,
  className = "",
  children,
  ...rest
}: Props) {
  const classes = [
    "ui-btn",
    `ui-btn-${variant}`,
    `ui-btn-${size}`,
    fullWidth ? "is-full" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return <Link href={href} className={classes} {...rest}><span className="ui-btn-label">{children}</span></Link>;
}

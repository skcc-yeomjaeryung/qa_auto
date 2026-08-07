"use client";

type IconName =
  | "search"
  | "filter"
  | "refresh"
  | "settings"
  | "plus"
  | "chevron-down"
  | "cross"
  | "more"
  | "eye"
  | "panel-collapse"
  | "progress-check"
  | "progress-error"
  | "progress-warning"
  | "progress-progressing"
  | "progress-empty"
  | "progress-disable";

const SRC: Record<IconName, string> = {
  search: "/icons/ui/search.svg",
  filter: "/icons/ui/filter.svg",
  refresh: "/icons/ui/refresh.svg",
  settings: "/icons/ui/settings.svg",
  plus: "/icons/ui/plus.svg",
  "chevron-down": "/icons/ui/chevron-down.svg",
  cross: "/icons/ui/cross.svg",
  more: "/icons/ui/more.svg",
  eye: "/icons/ui/eye.svg",
  "panel-collapse": "/icons/ui/panel-collapse.svg",
  "progress-check": "/icons/progress/check.svg",
  "progress-error": "/icons/progress/error.svg",
  "progress-warning": "/icons/progress/warning.svg",
  "progress-progressing": "/icons/progress/progressing.svg",
  "progress-empty": "/icons/progress/empty.svg",
  "progress-disable": "/icons/progress/disable.svg",
};

export function Icon({
  name,
  size = 16,
  className,
  alt = "",
}: {
  name: IconName;
  size?: number;
  className?: string;
  alt?: string;
}) {
  return (
    <span
      className={`ui-icon ${className ?? ""}`}
      style={{ width: size, height: size }}
      aria-hidden={alt ? undefined : true}
    >
      {/* Figma-exported asset — committed under public/icons */}
      <img src={SRC[name]} alt={alt} width={size} height={size} />
    </span>
  );
}

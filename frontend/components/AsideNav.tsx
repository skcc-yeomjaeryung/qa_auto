"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { navGroups } from "../lib/nav";

const ICON_BASE = "/goodfood-dash/icons";

const NAV_ICON_BY_HREF: Record<string, string> = {
  "/": "nav-chart.svg",
  "/projects": "nav-buy.svg",
  "/analysis": "nav-document.svg",
  "/scenarios": "nav-chat.svg",
  "/runs": "nav-wallet.svg",
  "/evidence": "nav-profile.svg",
  "/hitl": "nav-info.svg",
  "/manage/schedules": "nav-setting.svg",
  "/manage/models": "nav-document.svg",
  "/manage/agents": "nav-chart.svg",
};

function navIconSrc(href: string): string {
  const file = NAV_ICON_BY_HREF[href] ?? "nav-document.svg";
  return `${ICON_BASE}/${file}`;
}

/**
 * 좌측 주 메뉴 — 1depth만 둔다.
 *
 * 테스트 시나리오 그룹은 메뉴가 아니라 `/scenarios` 화면의 그룹 목록에서 고른다.
 */
export function AsideNav({ hasProject }: { hasProject: boolean }) {
  const pathname = usePathname();

  return (
    <nav className="aside-menu" data-testid="aside-menu">
      {navGroups.map((group) => (
        <div key={group.id} className="nav-group">
          <p className="nav-section-label">{group.label}</p>
          {group.items.map((item) => {
            const locked = Boolean(item.requiresProject && !hasProject);
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname === item.href || pathname.startsWith(`${item.href}/`);
            const iconSrc = navIconSrc(item.href);
            if (locked) {
              return (
                <span
                  key={item.href}
                  className="el-menu-item is-locked"
                  title="프로젝트를 먼저 생성하세요"
                  data-testid={`nav-locked-${item.href.replace(/\//g, "")}`}
                >
                  <span className="nav-ic">
                    <img src={iconSrc} alt="" width={18} height={18} />
                  </span>
                  <span>{item.label}</span>
                  <em className="nav-lock">잠김</em>
                </span>
              );
            }
            return (
              <Link
                key={item.href}
                href={item.href}
                className={active ? "el-menu-item is-active" : "el-menu-item"}
                data-testid={`nav-${item.href.replace(/\//g, "") || "home"}`}
              >
                <span className="nav-ic">
                  <img src={iconSrc} alt="" width={18} height={18} />
                </span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

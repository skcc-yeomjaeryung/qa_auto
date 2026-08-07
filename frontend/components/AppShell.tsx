"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { logout } from "../lib/auth";
import { getCurrentUserId, getCurrentUserName } from "../lib/user";
import { closeTab, openTab, type WorkspaceTab } from "../lib/workspaceTabs";
import { AsideNav } from "./AsideNav";
import { AuthProvider } from "./AuthProvider";
import { Icon } from "./Icon";
import { RightPanelProvider, useRightPanel } from "./RightPanelContext";
import { ActionToastHost } from "./ActionToastHost";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";
const ICON_BASE = "/goodfood-dash/icons";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <RightPanelProvider>
        <ShellFrame>{children}</ShellFrame>
        <ActionToastHost />
      </RightPanelProvider>
    </AuthProvider>
  );
}

function ShellFrame({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { panel, collapsed, setCollapsed, toggleCollapsed } = useRightPanel();
  const isLogin = pathname === "/login";
  const [userName, setUserName] = useState("TEST 사용자");
  const [userId, setUserId] = useState("TEST");
  // null = 아직 확인하지 못함. 네트워크 오류를 "프로젝트 0건"으로 바꾸면
  // 실제 프로젝트가 있어도 보호 라우트에서 강제 이탈하는 심각한 UX 결함이 된다.
  const [hasProject, setHasProject] = useState<boolean | null>(null);
  const [projectReady, setProjectReady] = useState(false);
  const [tabs, setTabs] = useState<WorkspaceTab[]>([]);
  const isDashboard = pathname === "/";

  const refreshProjects = useCallback(async () => {
    const uid = getCurrentUserId();
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const res = await fetch(`${API}/api/projects?ownerUserId=${encodeURIComponent(uid)}`, {
          cache: "no-store",
        });
        if (!res.ok) continue;
        const data = (await res.json()) as unknown[];
        setHasProject(data.length > 0);
        setProjectReady(true);
        return;
      } catch {
        // 즉시 한 번 더 조회한다. 둘 다 실패해도 unknown을 유지해 잘못된
        // 프로젝트 생성 화면으로 보내지 않는다.
      }
    }
  }, []);

  useEffect(() => {
    if (isLogin) return;
    setUserName(getCurrentUserName());
    setUserId(getCurrentUserId());
    void refreshProjects();
    const onChange = () => void refreshProjects();
    window.addEventListener("ai-test-projects-changed", onChange);
    return () => window.removeEventListener("ai-test-projects-changed", onChange);
  }, [isLogin, pathname, refreshProjects]);

  useEffect(() => {
    if (isLogin) return;
    setTabs(openTab(pathname));
  }, [pathname, isLogin]);

  // Keep right context collapsed by default — no column space for CENTER
  useEffect(() => {
    if (!collapsed) {
      setCollapsed(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- force collapsed shell layout
  }, []);

  useEffect(() => {
    if (isLogin || !projectReady || pathname === "/" || pathname === "/projects") return;
    if (hasProject === false) {
      router.replace("/projects?needProject=1");
    }
  }, [hasProject, projectReady, pathname, isLogin, router]);

  if (isLogin) {
    return <>{children}</>;
  }

  function handleLogout() {
    logout();
    router.replace("/login");
  }

  function onCloseTab(href: string) {
    const next = closeTab(href);
    setTabs(next);
    if (pathname === href) {
      router.push(next[next.length - 1]?.href || "/");
    }
  }

  const initials = userName.slice(0, 2).toUpperCase() || "TE";

  return (
    <div
      className={`app-wrapper is-goodfood is-soft-shell ${collapsed ? "right-collapsed" : ""} ${isDashboard ? "is-dashboard" : "is-workspace"}`}
      data-testid="app-shell"
      data-has-project={hasProject === null ? "unknown" : hasProject ? "true" : "false"}
      data-right-collapsed={collapsed ? "true" : "false"}
    >
      <aside className="el-aside" aria-label="주 메뉴">
        <Link href="/" className="gf-brand" data-testid="gf-brand">
          <img src={`${ICON_BASE}/logo-oval.svg`} alt="" width={20} height={20} className="gf-brand-oval" />
          <span className="gf-brand-name">SK 테스트 자동화도구</span>
        </Link>

        <AsideNav hasProject={hasProject !== false} />

        {hasProject === false && (
          <div className="aside-gate">
            <p>프로젝트 생성 후 분석·테스트 시나리오가 열립니다.</p>
            <Link className="primary-btn" href="/projects">
              프로젝트로 이동
            </Link>
          </div>
        )}

        <div className="aside-foot">
          <span className="dot" aria-hidden />
          AI_TEST · 품질 콘솔
        </div>
      </aside>

      <div className="main-column">
        <header className="el-header">
          <div className="header-inner">
            {/* 검색은 화면마다 성격이 달라 각 화면 제목 우측(ScreenSearch)으로 귀속한다 */}
            <div className="header-actions">
              <div className="header-user gf-header-user">
                <div className="avatar gf-avatar" aria-hidden>
                  {initials}
                </div>
                <div>
                  <div className="hu-name">{userName}</div>
                  <div className="hu-team gf-account-chevron">
                    {userId}
                    <img src={`${ICON_BASE}/chevron-down.svg`} alt="" width={12} height={12} />
                  </div>
                </div>
              </div>

              <button type="button" className="gf-notif-btn" aria-label="알림">
                <img src={`${ICON_BASE}/notif.svg`} alt="" width={20} height={20} />
                <img src={`${ICON_BASE}/notif-dot.svg`} alt="" width={8} height={8} className="gf-notif-dot" />
              </button>

              <button type="button" className="ghost-btn header-logout" onClick={handleLogout}>
                로그아웃
              </button>
            </div>
          </div>
        </header>

        {!isDashboard && (
          <div className="workspace-tabs gf-workspace-tabs" data-testid="workspace-tabs" data-figma-ref="31225:41861">
            {tabs.map((tab) => {
              const active = pathname === tab.href || pathname.startsWith(`${tab.href}/`);
              return (
                <div key={tab.href} className={active ? "ws-tab is-active" : "ws-tab"}>
                  <Link href={tab.href} className="ws-tab-link">
                    <span className="ws-tab-ic" aria-hidden />
                    {tab.label}
                  </Link>
                  {tab.href !== "/" && (
                    <button
                      type="button"
                      className="ws-tab-close"
                      aria-label={`${tab.label} 탭 닫기`}
                      onClick={() => onCloseTab(tab.href)}
                    >
                      ×
                    </button>
                  )}
                </div>
              );
            })}
            {tabs.length === 0 && <div className="ws-tab is-active">대시보드</div>}
          </div>
        )}

        <div className={`app-body-inner ${collapsed ? "is-center-only" : ""}`}>
          <main className={`shell-center ${isDashboard ? "is-dash" : "is-compact"}`}>{children}</main>

          {!collapsed && (
            <aside className="shell-right" aria-label="컨텍스트 패널" data-testid="shell-right">
              <div className="right-panel-toolbar">
                <span className="panel-kicker" style={{ margin: 0 }}>
                  컨텍스트
                </span>
                <button type="button" className="icon-btn" aria-label="패널 접기" onClick={toggleCollapsed}>
                  <Icon name="cross" size={14} />
                </button>
              </div>
              {panel ?? (
                <div className="right-panel">
                  <h3 className="panel-title">{hasProject === false ? "시작 안내" : "작업 중"}</h3>
                  <p className="panel-note">
                    {hasProject === false
                      ? "반드시 프로젝트를 먼저 생성하세요. 생성 전 다른 기능은 사용할 수 없습니다."
                      : "프로젝트 하위 메뉴에서 분석과 테스트 시나리오를 진행하세요."}
                  </p>
                </div>
              )}
            </aside>
          )}
        </div>
      </div>
    </div>
  );
}

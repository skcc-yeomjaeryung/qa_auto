/** Browser-like workspace tabs (AML Header tab pattern). */

const KEY = "ai_test_workspace_tabs";

export type WorkspaceTab = {
  href: string;
  label: string;
};

const LABEL: Record<string, string> = {
  "/": "대시보드",
  "/projects": "프로젝트",
  "/analysis": "분석",
  "/scenarios": "테스트 시나리오",
  "/runs": "실행 이력",
  "/evidence": "증적",
  "/hitl": "HITL 승인",
  "/manage/schedules": "관리 · 스케줄링",
  "/manage/models": "관리 · 모델",
  "/manage/agents": "관리 · Agent 모니터링",
};

export function labelForPath(pathname: string): string {
  if (LABEL[pathname]) return LABEL[pathname];
  if (pathname.startsWith("/scenarios/")) return "시나리오 상세";
  if (pathname === "/flow") return "테스트 시나리오";
  if (pathname.startsWith("/runs/")) return "실행 상세";
  if (pathname.startsWith("/manage/")) return "관리";
  return pathname;
}

export function readTabs(): WorkspaceTab[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as WorkspaceTab[]) : [];
  } catch {
    return [];
  }
}

export function writeTabs(tabs: WorkspaceTab[]): void {
  window.localStorage.setItem(KEY, JSON.stringify(tabs.slice(0, 8)));
}

export function openTab(pathname: string): WorkspaceTab[] {
  const label = labelForPath(pathname);
  const tabs = readTabs();
  if (!tabs.some((t) => t.href === pathname)) {
    tabs.push({ href: pathname, label });
  }
  writeTabs(tabs);
  return tabs;
}

export function closeTab(href: string): WorkspaceTab[] {
  const next = readTabs().filter((t) => t.href !== href);
  writeTabs(next);
  return next;
}

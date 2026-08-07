export type NavItem = {
  href: string;
  label: string;
  short: string;
  /** Requires at least one project owned by the user */
  requiresProject?: boolean;
};

export type NavGroup = {
  id: string;
  label: string;
  items: NavItem[];
};

export const navGroups: NavGroup[] = [
  {
    id: "home",
    label: "MENU",
    items: [
      { href: "/", label: "대시보드", short: "홈" },
      { href: "/projects", label: "프로젝트", short: "프로젝트" },
    ],
  },
  {
    id: "project-work",
    label: "WORK",
    items: [
      { href: "/analysis", label: "분석", short: "분석", requiresProject: true },
      { href: "/scenarios", label: "테스트 시나리오", short: "시나리오", requiresProject: true },
    ],
  },
  {
    id: "others",
    label: "OTHERS",
    items: [
      { href: "/runs", label: "실행 이력", short: "실행", requiresProject: true },
      { href: "/hitl", label: "HITL 승인", short: "승인", requiresProject: true },
    ],
  },
  {
    id: "manage",
    label: "MANAGE",
    items: [
      { href: "/manage/schedules", label: "스케줄링", short: "스케줄", requiresProject: true },
      { href: "/manage/models", label: "모델 관리", short: "모델" },
      { href: "/manage/agents", label: "Agent 모니터링", short: "Agent" },
    ],
  },
];

export const navItems: NavItem[] = navGroups.flatMap((group) => group.items);

export const journeySteps = [
  "프로젝트",
  "저장소",
  "시나리오생성",
  "시나리오목록",
  "테스트실행",
] as const;

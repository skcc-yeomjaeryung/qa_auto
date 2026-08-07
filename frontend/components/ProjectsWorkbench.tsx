"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { lsGet, lsSet } from "../lib/localStore";
import { PILOT_SANDBOX_BASE_URL } from "../lib/pilotTarget";
import { getCurrentUserId } from "../lib/user";
import {
  ProgressBarType2,
  ProgressBarType4,
  type JourneyStepState,
  type ProgressStatus,
} from "./ProgressBar";
import { useRightPanel } from "./RightPanelContext";
import { PageStickyFooter } from "./PageShell";
import {
  TableBulkDeleteForm,
  confirmBulkDelete,
} from "./TableBulkDeleteForm";
import { Button, Tag } from "./ui";
import { Breadcrumbs } from "./Breadcrumbs";
import { CommonDataTable } from "./CommonDataTable";
import { matchesQuery, ScreenSearch } from "./ScreenSearch";
import { formatDateTime } from "../lib/datetime";
import {
  ModelSelectionDialog,
  type ModelCapability,
  type SelectableModelProfile,
} from "./ModelSelectionDialog";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";

type ConnectUiPhase = "idle" | "registering" | "syncing" | "analyzing" | "complete" | "error";

const CONNECT_PHASE_LABEL: Record<ConnectUiPhase, string> = {
  idle: "대기",
  registering: "저장소 등록 중",
  syncing: "저장소 동기화 중",
  analyzing: "자동 분석 진행 중",
  complete: "연결·자동 분석 완료",
  error: "연결 오류",
};

const CONTEXT_STATUS_LABEL: Record<ProjectContextDocument["status"], string> = {
  queued: "업로드 완료 · 대기",
  extracting: "내용 추출 중",
  embedding: "임베딩·인덱싱 중",
  ready: "컨텍스트 준비 완료",
  partial: "일부 보강 완료",
  error: "처리 오류",
};

/** 관리 화면이 열려 있는 동안 연결 저장소 상태를 갱신하는 Pilot 주기. */
const PROJECT_SYNC_INTERVAL_MS = 5 * 60 * 1000;

type AiPolicy = "auto" | "cost_saver" | "balanced" | "highest_quality" | "internal_only";
type ModelSelectionMode = "auto" | "manual";
type ModelRole = "general" | "vision" | "embedding" | "advanced" | "image_generation";

const MODEL_ROLES: {
  id: ModelRole;
  name: string;
  description: string;
  requiredCapabilities: ModelCapability[];
}[] = [
  {
    id: "general",
    name: "일반 추론·분석",
    description: "코드 구조 파악과 일상적인 분석 작업에 사용합니다.",
    requiredCapabilities: ["chat", "code"],
  },
  {
    id: "embedding",
    name: "임베딩·검색",
    description: "문서와 코드 컨텍스트를 벡터로 변환해 검색할 때 사용합니다.",
    requiredCapabilities: ["embedding"],
  },
  {
    id: "vision",
    name: "PPT·브라우저 화면 이해",
    description: "PPT 이미지와 agent-browser 스크린샷을 읽어 관측 내용을 구조화합니다.",
    requiredCapabilities: ["chat", "vision"],
  },
  {
    id: "advanced",
    name: "고급 추론·요약",
    description: "시나리오 생성, 복잡한 분석, 요약과 문장 톤 조절에 사용합니다.",
    requiredCapabilities: ["chat", "code"],
  },
  {
    id: "image_generation",
    name: "이미지 생성·편집",
    description: "가이드 이미지나 시각 자료를 새로 만들거나 편집할 때만 사용합니다.",
    requiredCapabilities: ["image_generation"],
  },
];

const AI_POLICIES: { id: AiPolicy; name: string; description: string }[] = [
  { id: "auto", name: "자동 추천", description: "작업별 capability·context·health를 기준으로 Core가 선택" },
  { id: "cost_saver", name: "비용 절약", description: "가능한 작업은 sLLM과 규칙 기반 실행을 우선" },
  { id: "balanced", name: "균형", description: "품질·속도·비용·신뢰도를 균형 있게 평가" },
  { id: "highest_quality", name: "최고 품질", description: "복잡한 분석과 시나리오 생성에서 품질 우선" },
  { id: "internal_only", name: "내부망 전용", description: "외부 배포 모델은 후보 단계에서 제외" },
];

type Project = {
  id: string;
  name: string;
  description?: string | null;
  ownerUserId?: string;
  repositorySetIds?: string[];
  createdAt?: string;
  updatedAt?: string;
  aiPolicy?: AiPolicy;
  modelSelectionMode?: ModelSelectionMode;
  modelBindings?: Partial<Record<ModelRole, string>>;
};

type ConfirmSummary = {
  projectId: string;
  projectName: string;
  description: string;
  tags: string[];
  mode: "github" | "local";
  location: string;
  repoName: string;
  setId?: string;
  setStatus?: string;
  createdAt: string;
  connectedAt: string;
  environmentId?: string;
  environmentName?: string;
  frontendBaseUrl?: string;
  healthStatus?: string;
  analysisStatus?: "complete" | "partial" | "error";
  analysisCount?: number;
  contextDocumentCount?: number;
  contextReadyCount?: number;
  aiPolicy?: AiPolicy;
  modelSelectionMode?: ModelSelectionMode;
  modelBindings?: Partial<Record<ModelRole, string>>;
};

type ProjectContextDocument = {
  id: string;
  projectId: string;
  fileName: string;
  contentType: string;
  kind: "scenario_csv" | "design_ppt" | "unknown";
  status: "queued" | "extracting" | "embedding" | "ready" | "partial" | "error";
  progress: number;
  sizeBytes: number;
  chunkCount: number;
  scenarioHintCount: number;
  summary?: string | null;
  processingMode?: string | null;
  indexBackend?: string | null;
  error?: string | null;
  missingData?: string[];
};

type EnvPreset = {
  key: string;
  name: string;
  frontendBaseUrl: string;
  backendBaseUrl?: string | null;
  healthCheckPath?: string;
  accessNotes?: string | null;
  browser?: string;
  loginId?: string | null;
  loginPassword?: string | null;
};

// 파일럿 샌드박스(Bank of Anthos 데모) 연결 기본값 — 실행에 반드시 필요한 4개 값
const CONNECT_DEFAULTS = {
  url: "https://cymbal-bank.fsi.cymbal.dev",
  browser: "chrome",
  loginId: "testuser",
  loginPassword: "bankofanthos",
} as const;

const BROWSER_OPTIONS = [
  { value: "chrome", label: "Chrome (권장)" },
  { value: "chromium", label: "Chromium" },
  { value: "edge", label: "Edge" },
];

const CYMBAL_BANK_URL = PILOT_SANDBOX_BASE_URL;

type Repository = {
  id: string;
  role: string;
  sourceType: string;
  url?: string | null;
  path?: string | null;
  commitSha?: string | null;
  fileCount: number;
  syncStatus: string;
  lastError?: string | null;
  stack?: { languages?: string[]; frameworks?: string[] };
};

type RepositorySet = {
  id: string;
  projectId: string;
  name: string;
  status: string;
  repositories: Repository[];
};

type ProjectRow = {
  project: Project;
  sets: RepositorySet[];
};

type ProjectEnvironment = {
  id: string;
  name: string;
  frontendBaseUrl: string;
  status?: string;
  lastHealthStatus?: string | null;
  lastHealthAt?: string | null;
  browser?: string;
  loginId?: string | null;
  loginRole?: string | null;
  hasLoginSecret?: boolean;
  createdAt?: string;
  updatedAt?: string;
};

type ViewMode = "list" | "create" | "edit" | "detail";
type CreateStep = 1 | 2 | 3 | 4 | 5 | 6;

function guessRepoNameFromUrl(url: string): string {
  const cleaned = url.trim().replace(/\.git$/i, "");
  const parts = cleaned.split("/").filter(Boolean);
  return parts[parts.length - 1] || "";
}

function guessRepoNameFromPath(path: string): string {
  const cleaned = path.trim().replace(/[/\\]+$/, "");
  const parts = cleaned.split(/[/\\]/).filter(Boolean);
  return parts[parts.length - 1] || "";
}

function statusLabel(status: string): { text: string; tone: "ok" | "warn" | "bad" | "muted" } {
  if (status === "complete" || status === "cached") return { text: "연결완료", tone: "ok" };
  if (status === "syncing" || status === "analyzing") return { text: status, tone: "warn" };
  if (status === "error" || status === "failed") return { text: status, tone: "bad" };
  if (!status) return { text: "미연결", tone: "muted" };
  return { text: status, tone: "warn" };
}

function primaryRepo(set: RepositorySet | undefined): Repository | null {
  if (!set?.repositories?.length) return null;
  return set.repositories.find((r) => r.role === "workspace") ?? set.repositories[0];
}

function repositoryIdentity(repository: Repository | null): string {
  if (!repository) return "";
  const location = String(repository.url || repository.path || "")
    .trim()
    .replace(/\.git\/?$/i, "")
    .replace(/[/\\]+$/, "")
    .toLocaleLowerCase();
  return [repository.sourceType, location].join(":");
}

/** 과거에 같은 URL을 다른 표시명으로 연결한 데이터는 한 개의 연결로 다룬다. */
function uniqueRepositorySets(sets: RepositorySet[]): RepositorySet[] {
  const bySource = new Map<string, RepositorySet>();
  for (const set of sets) {
    const identity = repositoryIdentity(primaryRepo(set)) || set.id;
    // API 순서의 뒤쪽(프로젝트의 현재 primary 연결)을 대표값으로 사용한다.
    bySource.set(identity, set);
  }
  return Array.from(bySource.values());
}

function descriptionParts(raw: string | null | undefined): { description: string; tags: string } {
  const lines = String(raw || "").split(/\r?\n/);
  const tagLine = lines.find((line) => line.trim().toLowerCase().startsWith("tags:"));
  return {
    tags: tagLine ? tagLine.replace(/^\s*tags:\s*/i, "") : "",
    description: lines.filter((line) => line !== tagLine).join("\n").trim(),
  };
}

function parseTags(raw: string): string[] {
  return raw
    .split(/[,，]/)
    .map((t) => t.trim())
    .filter(Boolean)
    .slice(0, 8);
}

function buildDescription(description: string, tags: string[]): string | undefined {
  const desc = description.trim();
  const tagLine = tags.length ? `tags: ${tags.join(", ")}` : "";
  const merged = [tagLine, desc].filter(Boolean).join("\n");
  return merged || undefined;
}

export function ProjectsWorkbench() {
  const router = useRouter();
  const { setPanel } = useRightPanel();
  const searchParams = useSearchParams();
  const needProject = searchParams.get("needProject") === "1";
  const userId = useMemo(() => getCurrentUserId(), []);

  const [view, setView] = useState<ViewMode>("list");
  const [createStep, setCreateStep] = useState<CreateStep>(1);
  const [rows, setRows] = useState<ProjectRow[]>([]);
  const [query, setQuery] = useState("");
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [projectName, setProjectName] = useState("");
  const [projectDescription, setProjectDescription] = useState("");
  const [projectTags, setProjectTags] = useState("");
  const [aiPolicy, setAiPolicy] = useState<AiPolicy>("auto");
  const [modelSelectionMode, setModelSelectionMode] = useState<ModelSelectionMode>("auto");
  const [modelBindings, setModelBindings] = useState<Partial<Record<ModelRole, string>>>({});
  const [modelProfiles, setModelProfiles] = useState<SelectableModelProfile[]>([]);
  const [modelPickerRole, setModelPickerRole] = useState<ModelRole | null>(null);
  const [mode, setMode] = useState<"github" | "local">("github");
  const [repoName, setRepoName] = useState("");
  const [githubUrl, setGithubUrl] = useState(
    "https://github.com/GoogleCloudPlatform/bank-of-anthos.git",
  );
  const [localPath, setLocalPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [ok, setOk] = useState(false);
  const [confirmSummary, setConfirmSummary] = useState<ConfirmSummary | null>(null);
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  const [connectPhase, setConnectPhase] = useState<ConnectUiPhase>("idle");
  const [connectPercent, setConnectPercent] = useState(0);
  const [envName, setEnvName] = useState("Cymbal Bank (FSI)");
  const [frontendBaseUrl, setFrontendBaseUrl] = useState(CYMBAL_BANK_URL);
  const [backendBaseUrl, setBackendBaseUrl] = useState("");
  const [healthCheckPath, setHealthCheckPath] = useState("/");
  const [connectBrowser, setConnectBrowser] = useState<string>(CONNECT_DEFAULTS.browser);
  const [connectLoginId, setConnectLoginId] = useState<string>(CONNECT_DEFAULTS.loginId);
  const [connectPassword, setConnectPassword] = useState<string>(CONNECT_DEFAULTS.loginPassword);
  const [connectLoginRole, setConnectLoginRole] = useState("관리자");
  const [envPresets, setEnvPresets] = useState<EnvPreset[]>([]);
  const [healthBusy, setHealthBusy] = useState(false);
  const [syncingSetIds, setSyncingSetIds] = useState<Set<string>>(new Set());
  const [detailEnvironments, setDetailEnvironments] = useState<ProjectEnvironment[]>([]);
  const [contextDocuments, setContextDocuments] = useState<ProjectContextDocument[]>([]);
  const [contextBusy, setContextBusy] = useState(false);
  const [contextDragActive, setContextDragActive] = useState(false);
  const tagList = useMemo(() => parseTags(projectTags), [projectTags]);

  const loadAll = useCallback(async () => {
    const res = await fetch(`${API}/api/projects?ownerUserId=${encodeURIComponent(userId)}`, {
      cache: "no-store",
    });
    if (!res.ok) throw new Error("프로젝트 목록을 불러오지 못했습니다");
    const projects = (await res.json()) as Project[];
    const repositorySetFailures: string[] = [];
    const next: ProjectRow[] = await Promise.all(
      projects.map(async (project) => {
        let sets: RepositorySet[] = [];
        try {
          const setsRes = await fetch(`${API}/api/projects/${project.id}/repository-sets`, {
            cache: "no-store",
          });
          if (!setsRes.ok) throw new Error(`HTTP ${setsRes.status}`);
          sets = uniqueRepositorySets((await setsRes.json()) as RepositorySet[]);
        } catch {
          // 한 프로젝트의 보조 조회 실패가 전체 프로젝트 목록을 숨기지 않게 격리한다.
          // 다음 수동/주기 조회에서 성공하면 아래 경고도 함께 제거된다.
          repositorySetFailures.push(project.name || project.id);
        }
        return { project, sets };
      }),
    );
    setRows(next);
    setSelectedProjectId((prev) => prev ?? next[0]?.project.id ?? null);
    lsSet(`projects.catalog.${userId}`, next.map((r) => ({
      id: r.project.id,
      name: r.project.name,
      setCount: r.sets.length,
      updatedAt: r.project.updatedAt,
    })));
    if (repositorySetFailures.length > 0) {
      setMessage(`프로젝트 ${repositorySetFailures.length}건의 저장소 목록을 일시적으로 불러오지 못했습니다. 다음 조회에서 다시 확인합니다.`);
      setOk(false);
    } else {
      setMessage((current) => (
        current === "Failed to fetch"
        || current === "프로젝트 목록을 불러오지 못했습니다"
        || current?.startsWith("프로젝트 ") && current.includes("저장소 목록을 일시적으로")
          ? null
          : current
      ));
      setOk(true);
    }
  }, [userId]);

  const loadContextDocuments = useCallback(async (projectId: string) => {
    const response = await fetch(`${API}/api/projects/${encodeURIComponent(projectId)}/context-documents`, {
      cache: "no-store",
      headers: { "X-User-Id": userId },
    });
    if (!response.ok) throw new Error("품질 보강 자료를 불러오지 못했습니다");
    const documents = (await response.json()) as ProjectContextDocument[];
    setContextDocuments(Array.isArray(documents) ? documents : []);
    setConfirmSummary((current) => current ? {
      ...current,
      contextDocumentCount: documents.length,
      contextReadyCount: documents.filter((item) => item.status === "ready" || item.status === "partial").length,
    } : current);
    return documents;
  }, [userId]);

  const loadModelProfiles = useCallback(async () => {
    const response = await fetch(`${API}/api/models`, { cache: "no-store" });
    if (!response.ok) throw new Error("등록 모델을 불러오지 못했습니다");
    const items = (await response.json()) as SelectableModelProfile[];
    setModelProfiles(Array.isArray(items) ? items : []);
    return items;
  }, []);

  useEffect(() => {
    setPanel(null);
    return () => setPanel(null);
  }, [setPanel]);

  useEffect(() => {
    loadAll()
      .catch((e: Error) => {
        setMessage(e.message);
        setOk(false);
      })
      .finally(() => setListLoading(false));
    fetch(`${API}/api/environment-presets`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then((presets: EnvPreset[]) => setEnvPresets(Array.isArray(presets) ? presets : []))
      .catch(() => setEnvPresets([]));
    loadModelProfiles().catch(() => setModelProfiles([]));
  }, [userId, loadModelProfiles]); // eslint-disable-line react-hooks/exhaustive-deps -- initial load

  useEffect(() => {
    if (rows.length === 0) return;
    const timer = window.setInterval(() => {
      const setIds = rows.flatMap((row) => row.sets.map((set) => set.id));
      if (setIds.length > 0) void syncRepositorySets(setIds, { quiet: true, force: false });
    }, PROJECT_SYNC_INTERVAL_MS);
    return () => window.clearInterval(timer);
    // rows are intentionally the current server catalog used by the periodic sync tick.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows]);

  useEffect(() => {
    if (needProject && rows.length === 0 && view === "list") {
      setView("create");
      setCreateStep(1);
    }
  }, [needProject, rows.length, view]);

  useEffect(() => {
    if ((view !== "detail" && view !== "edit") || !selectedProjectId) {
      setDetailEnvironments([]);
      return;
    }
    let cancelled = false;
    fetch(`${API}/api/projects/${selectedProjectId}/environments`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : []))
      .then((envs: ProjectEnvironment[]) => {
        const nextEnvironments = Array.isArray(envs) ? envs : [];
        if (!cancelled) setDetailEnvironments(nextEnvironments);
        if (!cancelled && view === "edit" && nextEnvironments[0]) {
          const environment = nextEnvironments[0];
          setEnvName(environment.name);
          setFrontendBaseUrl(environment.frontendBaseUrl);
          setConnectBrowser(environment.browser || CONNECT_DEFAULTS.browser);
          setConnectLoginId(environment.loginId || "");
          setConnectLoginRole(environment.loginRole || "관리자");
          // 기존 Secret은 다시 노출하지 않는다. 빈 값이면 PATCH에서 기존 값을 유지한다.
          setConnectPassword("");
          setConfirmSummary((current) => current ? {
            ...current,
            environmentId: environment.id,
            environmentName: environment.name,
            frontendBaseUrl: environment.frontendBaseUrl,
            healthStatus: environment.lastHealthStatus || "unknown",
          } : current);
        }
      })
      .catch(() => {
        if (!cancelled) setDetailEnvironments([]);
      });
    loadContextDocuments(selectedProjectId).catch(() => {
      if (!cancelled) setContextDocuments([]);
    });
    return () => {
      cancelled = true;
    };
  }, [view, selectedProjectId, loadContextDocuments]);

  useEffect(() => {
    if (view !== "create" || createStep !== 5 || !selectedProjectId) return;
    let cancelled = false;
    const refresh = async () => {
      try {
        const documents = await loadContextDocuments(selectedProjectId);
        if (cancelled) return;
        if (documents.some((item) => ["queued", "extracting", "embedding"].includes(item.status))) {
          window.setTimeout(() => { if (!cancelled) void refresh(); }, 900);
        }
      } catch (caught) {
        if (!cancelled) {
          setMessage(caught instanceof Error ? caught.message : "품질 보강 자료 조회 실패");
          setOk(false);
        }
      }
    };
    void refresh();
    return () => { cancelled = true; };
  }, [view, createStep, selectedProjectId, loadContextDocuments]);

  function openCreate() {
    setView("create");
    setCreateStep(1);
    setProjectName("");
    setProjectDescription("");
    setProjectTags("");
    setAiPolicy("auto");
    setModelSelectionMode("auto");
    setModelBindings({});
    setModelPickerRole(null);
    setRepoName("");
    setSelectedProjectId(null);
    setMessage(null);
    setConfirmSummary(null);
    setContextDocuments([]);
  }

  function openEdit(projectId: string) {
    setSelectedProjectId(projectId);
    setView("edit");
    setCreateStep(1);
    const row = rows.find((r) => r.project.id === projectId);
    const parts = descriptionParts(row?.project.description);
    const repositorySet = row?.sets[0];
    const repository = primaryRepo(repositorySet);
    setProjectName(row?.project.name ?? "");
    setProjectDescription(parts.description);
    setProjectTags(parts.tags);
    setAiPolicy(row?.project.aiPolicy ?? "auto");
    setModelSelectionMode(row?.project.modelSelectionMode ?? "auto");
    setModelBindings(row?.project.modelBindings ?? {});
    setRepoName(repositorySet?.name ?? "");
    setMode(repository?.sourceType === "local" ? "local" : "github");
    setGithubUrl(repository?.url || "https://github.com/GoogleCloudPlatform/bank-of-anthos.git");
    setLocalPath(repository?.path || "");
    setConfirmSummary(row ? {
      projectId: row.project.id,
      projectName: row.project.name,
      description: parts.description,
      tags: parseTags(parts.tags),
      mode: repository?.sourceType === "local" ? "local" : "github",
      location: repository?.url || repository?.path || "",
      repoName: repositorySet?.name || "",
      setId: repositorySet?.id,
      setStatus: repositorySet?.status,
      createdAt: row.project.createdAt || new Date().toISOString(),
      connectedAt: "",
      aiPolicy: row.project.aiPolicy || "auto",
      modelSelectionMode: row.project.modelSelectionMode || "auto",
      modelBindings: row.project.modelBindings || {},
    } : null);
    setMessage(null);
  }

  function openDetail(projectId: string) {
    setSelectedProjectId(projectId);
    setView("detail");
    setMessage(null);
  }

  function backToList() {
    setView("list");
    setCreateStep(1);
    setMessage(null);
    void loadAll();
  }

  const cachedHint = useMemo(
    () => lsGet<{ id: string; name: string }[]>(`projects.catalog.${userId}`, []),
    [userId, rows.length],
  );

  async function createProject() {
    if (!projectName.trim()) {
      setMessage("프로젝트 이름을 입력하세요.");
      setOk(false);
      return;
    }
    setBusy(true);
    try {
      const description = buildDescription(projectDescription, tagList);
      const res = await fetch(`${API}/api/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: projectName.trim(),
          ownerUserId: userId,
          description,
          aiPolicy,
          modelSelectionMode,
          modelBindings,
        }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "생성 실패");
      setSelectedProjectId(body.id);
      setConfirmSummary({
        projectId: body.id,
        projectName: body.name,
        description: projectDescription.trim(),
        tags: tagList,
        mode,
        location: "",
        repoName: "",
        createdAt: body.createdAt || new Date().toISOString(),
        connectedAt: "",
        aiPolicy: body.aiPolicy || aiPolicy,
        modelSelectionMode: body.modelSelectionMode || modelSelectionMode,
        modelBindings: body.modelBindings || modelBindings,
      });
      setMessage(`프로젝트 「${body.name}」이 생성되었습니다. 사용할 AI 모델 방식을 정하세요.`);
      setOk(true);
      setCreateStep(2);
      window.dispatchEvent(new Event("ai-test-projects-changed"));
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "생성 실패");
      setOk(false);
    } finally {
      setBusy(false);
    }
  }

  async function saveModelSettings() {
    if (!selectedProjectId) {
      setMessage("먼저 프로젝트 이름을 저장하세요.");
      setOk(false);
      return;
    }
    setBusy(true);
    try {
      const response = await fetch(`${API}/api/projects/${selectedProjectId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          aiPolicy,
          modelSelectionMode,
          modelBindings,
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "모델 설정 저장 실패");
      setConfirmSummary((current) => current ? {
        ...current,
        aiPolicy: body.aiPolicy || aiPolicy,
        modelSelectionMode: body.modelSelectionMode || modelSelectionMode,
        modelBindings: body.modelBindings || modelBindings,
      } : current);
      const fixedCount = Object.values(modelBindings).filter(Boolean).length;
      setMessage(
        modelSelectionMode === "auto"
          ? "AI 자동 추천을 저장했습니다. 작업별 capability·context·health로 모델을 선택합니다."
          : `역할별 고정 모델 ${fixedCount}개를 저장했습니다. 비어 있는 역할은 자동 추천을 사용합니다.`,
      );
      setOk(true);
      window.dispatchEvent(new Event("ai-test-projects-changed"));
      await loadAll();
      if (view === "create") setCreateStep(3);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "모델 설정 저장 실패");
      setOk(false);
    } finally {
      setBusy(false);
    }
  }

  function ensureRepoName(): string {
    if (repoName.trim()) return repoName.trim();
    if (mode === "github") return guessRepoNameFromUrl(githubUrl) || "repository";
    return guessRepoNameFromPath(localPath) || "repository";
  }

  async function connectRepo() {
    if (!selectedProjectId) {
      setMessage("먼저 프로젝트를 생성하세요.");
      setOk(false);
      return;
    }
    if (mode === "github" && !githubUrl.trim()) {
      setMessage("GitHub URL을 입력하세요.");
      setOk(false);
      return;
    }
    if (mode === "local" && !localPath.trim()) {
      setMessage("로컬 경로를 입력하세요.");
      setOk(false);
      return;
    }
    const name = ensureRepoName();
    setBusy(true);
    setConnectPhase("registering");
    setConnectPercent(10);
    setMessage("저장소 연결을 시작합니다. 동기화 후 코드 자동 분석까지 이어서 진행합니다.");
    setOk(true);

    // 연결 API의 register/sync 구간 안내. 분석 구간은 실제 bulk-analyze 요청과 맞춘다.
    const timers: number[] = [];
    timers.push(
      window.setTimeout(() => {
        setConnectPhase("syncing");
        setConnectPercent(40);
        setMessage("저장소를 동기화하는 중입니다…");
      }, 500),
    );

    try {
      const body =
        mode === "github"
          ? {
              projectId: selectedProjectId,
              repositorySetId: view === "edit" ? confirmSummary?.setId : undefined,
              ownerUserId: userId,
              repositoryName: name,
              sourceType: "github",
              autoAnalyze: false,
              repository: { url: githubUrl.trim(), branch: "main" },
            }
          : {
              projectId: selectedProjectId,
              repositorySetId: view === "edit" ? confirmSummary?.setId : undefined,
              ownerUserId: userId,
              repositoryName: name,
              sourceType: "local",
              autoAnalyze: false,
              repository: { path: localPath.trim() },
            };
      const res = await fetch(`${API}/api/console/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "연결 실패");
      const location = mode === "github" ? githubUrl.trim() : localPath.trim();
      const now = new Date().toISOString();
      setConfirmSummary((prev) => ({
        projectId: selectedProjectId,
        projectName: prev?.projectName || projectName.trim(),
        description: prev?.description || projectDescription.trim(),
        tags: prev?.tags?.length ? prev.tags : tagList,
        mode,
        location,
        repoName: data.repositoryName || name,
        setId: data.repositorySetId,
        setStatus: "complete",
        createdAt: prev?.createdAt || now,
        connectedAt: now,
        aiPolicy: prev?.aiPolicy || aiPolicy,
        modelSelectionMode: prev?.modelSelectionMode || modelSelectionMode,
        modelBindings: prev?.modelBindings || modelBindings,
      }));

      setConnectPhase("analyzing");
      setConnectPercent(72);
      setMessage("저장소 연결이 완료되었습니다. AI가 DOM 구조와 코드를 자동 분석하는 중입니다…");
      // 분석 요청 전에 진행 상태가 실제 DOM에 그려지도록 한 렌더 프레임을 양보한다.
      await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
      const analysisRes = await fetch(`${API}/api/console/bulk-analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          projectId: selectedProjectId,
          repositorySetIds: [data.repositorySetId],
          force: false,
        }),
      });
      const analysis = await analysisRes.json();
      const analysisIds = new Set<string>();
      for (const result of analysis.results || []) {
        if (result.analysisId) analysisIds.add(result.analysisId);
        for (const id of result.analysisIds || []) analysisIds.add(id);
      }
      const analysisStatus: "complete" | "partial" | "error" = !analysisRes.ok
        ? "error"
        : analysis.status === "complete"
          ? "complete"
          : "partial";
      setConfirmSummary((prev) => prev ? {
        ...prev,
        analysisStatus,
        analysisCount: analysisIds.size,
      } : prev);
      setConnectPhase("complete");
      setConnectPercent(100);
      setMessage(
        analysisStatus === "complete"
          ? `저장소 연결과 자동 분석이 완료되었습니다. 분석 결과 ${analysisIds.size}건을 분석 메뉴에서 확인할 수 있습니다.`
          : "저장소 연결은 완료됐지만 자동 분석 일부를 확인해야 합니다. 분석 메뉴에서 상태를 확인하세요.",
      );
      setOk(analysisStatus !== "error");
      window.dispatchEvent(new Event("ai-test-projects-changed"));
      try {
        await loadAll();
      } catch {
        // 연결·분석 자체는 이미 서버에서 완료됐다. 후속 목록 갱신 실패를 연결 실패로 뒤집지 않는다.
        setMessage(
          analysisStatus === "complete"
            ? `저장소 연결과 자동 분석이 완료되었습니다. 목록 새로고침은 다음 화면 진입 때 다시 시도합니다.`
            : "저장소 연결은 완료됐고 분석 일부 확인이 필요합니다. 목록은 다음 화면에서 다시 불러옵니다.",
        );
      }
    } catch (e) {
      setConnectPhase("error");
      setConnectPercent(100);
      setMessage(e instanceof Error ? e.message : "연결 실패");
      setOk(false);
    } finally {
      timers.forEach((id) => window.clearTimeout(id));
      setBusy(false);
    }
  }

  function applyEnvPreset(key: string) {
    const preset = envPresets.find((p) => p.key === key);
    if (!preset) return;
    setEnvName(preset.name);
    setFrontendBaseUrl(preset.frontendBaseUrl);
    setBackendBaseUrl(preset.backendBaseUrl || "");
    setHealthCheckPath(preset.healthCheckPath || "/");
    setConnectBrowser(preset.browser || CONNECT_DEFAULTS.browser);
    setConnectLoginId(preset.loginId ?? "");
    setConnectPassword(preset.loginPassword ?? "");
  }

  async function saveEnvironment() {
    if (!selectedProjectId) {
      setMessage("먼저 프로젝트를 생성하세요.");
      setOk(false);
      return;
    }
    if (!frontendBaseUrl.trim()) {
      setMessage("연결 URL을 입력하세요.");
      setOk(false);
      return;
    }
    if (!connectBrowser.trim()) {
      setMessage("연결 브라우저를 선택하세요.");
      setOk(false);
      return;
    }
    const editingEnvironment = view === "edit" ? detailEnvironments[0] : undefined;
    if (!connectLoginId.trim() || (!editingEnvironment?.hasLoginSecret && !connectPassword.trim())) {
      setMessage("연결 ID와 연결 PASSWORD는 실제 테스트 실행에 필요한 필수 입력값입니다.");
      setOk(false);
      return;
    }
    setBusy(true);
    setHealthBusy(true);
    try {
      const environmentUrl = editingEnvironment
        ? `${API}/api/environments/${editingEnvironment.id}`
        : `${API}/api/projects/${selectedProjectId}/environments`;
      const environmentPayload = {
        name: envName.trim() || "DEV",
        frontendBaseUrl: frontendBaseUrl.trim(),
        backendBaseUrl: backendBaseUrl.trim() || null,
        healthCheckPath: healthCheckPath.trim() || "/",
        verifyTls: true,
        browser: connectBrowser,
        loginId: connectLoginId.trim(),
        ...(connectPassword ? { loginPassword: connectPassword } : {}),
        loginRole: connectLoginRole.trim() || "관리자",
        accessNotes: "Registered from project wizard",
      };
      const createRes = await fetch(environmentUrl, {
        method: editingEnvironment ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(environmentPayload),
      });
      const created = await createRes.json();
      if (!createRes.ok) throw new Error(created.detail || "실행 환경 등록 실패");

      const healthRes = await fetch(`${API}/api/environments/${created.id}/health-check`, {
        method: "POST",
      });
      const health = healthRes.ok ? await healthRes.json() : null;

      setConfirmSummary((prev) =>
        prev
          ? {
              ...prev,
              environmentId: created.id,
              environmentName: created.name,
              frontendBaseUrl: created.frontendBaseUrl,
              healthStatus: health?.status || created.lastHealthStatus || "unknown",
            }
          : prev,
      );
      setMessage(
        health?.message ||
          `실행 환경 「${created.name}」을 등록했습니다. Health: ${health?.status || "unknown"}`,
      );
      setOk(true);
      if (view === "create") setCreateStep(5);
      lsSet(`projects.env.${selectedProjectId}`, {
        environmentId: created.id,
        frontendBaseUrl: created.frontendBaseUrl,
      });
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "실행 환경 등록 실패");
      setOk(false);
    } finally {
      setBusy(false);
      setHealthBusy(false);
    }
  }

  async function uploadContextFiles(files: FileList | File[]) {
    if (!selectedProjectId) return;
    const selected = Array.from(files).filter((file) => /\.(csv|ppt|pptx)$/i.test(file.name));
    if (selected.length === 0) {
      setMessage("CSV 또는 PPT/PPTX 파일을 선택하세요.");
      setOk(false);
      return;
    }
    setContextBusy(true);
    setMessage(`품질 보강 자료 ${selected.length}건을 업로드하고 분석을 시작합니다…`);
    setOk(true);
    try {
      for (const file of selected) {
        const response = await fetch(
          `${API}/api/projects/${encodeURIComponent(selectedProjectId)}/context-documents?fileName=${encodeURIComponent(file.name)}`,
          {
            method: "POST",
            headers: {
              "Content-Type": file.type || "application/octet-stream",
              "X-User-Id": userId,
            },
            body: file,
          },
        );
        const body = await response.json();
        if (!response.ok) throw new Error(body.detail || `${file.name} 업로드 실패`);
      }
      await loadContextDocuments(selectedProjectId);
      setMessage("파일 업로드가 완료되었습니다. 정형화·VLM OCR·임베딩 진행 상태를 확인하세요.");
      setOk(true);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "품질 보강 자료 업로드 실패");
      setOk(false);
    } finally {
      setContextBusy(false);
    }
  }

  async function deleteContextDocument(documentId: string) {
    if (!selectedProjectId) return;
    setContextBusy(true);
    try {
      const response = await fetch(
        `${API}/api/projects/${encodeURIComponent(selectedProjectId)}/context-documents/${encodeURIComponent(documentId)}`,
        { method: "DELETE", headers: { "X-User-Id": userId } },
      );
      if (!response.ok && response.status !== 204) throw new Error("자료 삭제 실패");
      await loadContextDocuments(selectedProjectId);
      setMessage("품질 보강 자료를 삭제했습니다. 이후 시나리오 생성 컨텍스트에서 제외됩니다.");
      setOk(true);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "자료 삭제 실패");
      setOk(false);
    } finally {
      setContextBusy(false);
    }
  }

  function openAnalysis(projectId: string) {
    router.push(`/analysis?projectId=${encodeURIComponent(projectId)}`);
  }

  async function syncRepositorySets(
    setIds: string[],
    options: { quiet?: boolean; force?: boolean } = {},
  ) {
    if (setIds.length === 0) {
      if (!options.quiet) {
        setMessage("동기화할 연결 저장소가 없습니다.");
        setOk(false);
      }
      return;
    }
    setSyncingSetIds((current) => new Set([...current, ...setIds]));
    if (!options.quiet) {
      setMessage("연결 저장소의 최신 변경분을 확인하고 있습니다…");
      setOk(true);
    }
    try {
      const results = await Promise.all(
        setIds.map(async (setId) => {
          const response = await fetch(`${API}/api/repository-sets/${encodeURIComponent(setId)}/sync`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ force: options.force ?? true }),
          });
          const body = await response.json();
          if (!response.ok) throw new Error(body.detail || `${setId} 동기화 실패`);
          return body as RepositorySet;
        }),
      );
      const projectIds = Array.from(new Set(results.map((set) => set.projectId).filter(Boolean)));
      const analysisRes = await fetch(`${API}/api/console/bulk-analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          projectId: projectIds.length === 1 ? projectIds[0] : undefined,
          repositorySetIds: setIds,
          force: false,
        }),
      });
      const analysis = await analysisRes.json();
      if (!analysisRes.ok) throw new Error(analysis.detail || "동기화 후 자동 분석 실패");
      if (!options.quiet) {
        const changed = results.filter((set) => set.status !== "cached").length;
        const completed = (analysis.results || []).filter((item: { status?: string }) => item.status === "complete").length;
        setMessage(`저장소 ${results.length}건 동기화 완료 · 변경 확인 ${changed}건 · 자동 분석 ${completed}건 완료`);
        setOk(analysis.status !== "partial");
      }
      await loadAll();
    } catch (caught) {
      if (!options.quiet) {
        setMessage(caught instanceof Error ? caught.message : "저장소 동기화 실패");
        setOk(false);
      }
    } finally {
      setSyncingSetIds((current) => {
        const next = new Set(current);
        setIds.forEach((setId) => next.delete(setId));
        return next;
      });
    }
  }

  async function bulkDeleteProjects() {
    if (!confirmBulkDelete("프로젝트", checkedIds.size)) return;
    setBusy(true);
    try {
      let removed = 0;
      for (const projectId of Array.from(checkedIds)) {
        const res = await fetch(`${API}/api/projects/${projectId}`, { method: "DELETE" });
        if (res.ok || res.status === 204) removed += 1;
      }
      setCheckedIds(new Set());
      setMessage(`프로젝트 ${removed}건을 삭제했습니다.`);
      setOk(true);
      window.dispatchEvent(new Event("ai-test-projects-changed"));
      await loadAll();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "일괄 삭제 실패");
      setOk(false);
    } finally {
      setBusy(false);
    }
  }

  async function deleteProject(projectId: string, name: string) {
    if (!window.confirm(`프로젝트 「${name}」을 삭제할까요?`)) return;
    setSelectedProjectId(projectId);
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/projects/${projectId}`, { method: "DELETE" });
      if (!res.ok && res.status !== 204) throw new Error("삭제 실패");
      setMessage("프로젝트가 삭제되었습니다.");
      setOk(true);
      if (selectedProjectId === projectId) setSelectedProjectId(null);
      window.dispatchEvent(new Event("ai-test-projects-changed"));
      await loadAll();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "삭제 실패");
      setOk(false);
    } finally {
      setBusy(false);
    }
  }

  async function renameProject() {
    if (!selectedProjectId || !projectName.trim()) {
      setMessage("프로젝트 이름을 입력하세요.");
      setOk(false);
      return;
    }
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/projects/${selectedProjectId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: projectName.trim(),
          description: buildDescription(projectDescription, tagList) || "",
          aiPolicy,
          modelSelectionMode,
          modelBindings,
        }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "수정 실패");
      setConfirmSummary((current) => current ? {
        ...current,
        projectName: body.name,
        description: projectDescription.trim(),
        tags: tagList,
        aiPolicy,
        modelSelectionMode,
        modelBindings,
      } : current);
      setMessage(`프로젝트 「${body.name}」의 기본 정보를 저장했습니다.`);
      setOk(true);
      window.dispatchEvent(new Event("ai-test-projects-changed"));
      await loadAll();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "수정 실패");
      setOk(false);
    } finally {
      setBusy(false);
    }
  }

  // 화면 내 검색 — 프로젝트명·ID·저장소 위치로 목록을 좁힌다
  const visibleRows = useMemo(
    () =>
      rows.filter((row) =>
        matchesQuery(
          query,
          row.project.name,
          row.project.id,
          ...row.sets.flatMap((set) => [
            set.name,
            ...(set.repositories || []).flatMap((repo) => [repo.url, repo.path, repo.role]),
          ]),
        ),
      ),
    [rows, query],
  );
  const detailRow = rows.find((r) => r.project.id === selectedProjectId) ?? null;
  const connectionReady = Boolean(
    view === "create" &&
    createStep === 3 &&
    confirmSummary?.setId &&
    connectPhase === "complete",
  );
  const contextProcessing = contextDocuments.some((item) => ["queued", "extracting", "embedding"].includes(item.status));

  const createProgressSteps = useMemo((): JourneyStepState[] => {
    const connecting = busy && createStep === 3 && connectPhase !== "idle" && connectPhase !== "error";
    const statusFor = (step: CreateStep): ProgressStatus => {
      if (view === "edit") return createStep === step ? "progressing" : "complete";
      if (createStep > step) return "complete";
      if (createStep === step) {
        if (step === 3 && connectPhase === "error") return "error";
        if (step === 3 && connectPhase === "complete") return "complete";
        if (step === 3 && connecting) return "progressing";
        if (step === 4 && healthBusy) return "progressing";
        if (step === 5 && contextBusy) return "progressing";
        return "progressing";
      }
      return "empty";
    };
    return [
      { label: "프로젝트 이름", status: statusFor(1) },
      { label: "모델 설정", status: statusFor(2) },
      {
        label: connecting ? `저장소 연결 · ${CONNECT_PHASE_LABEL[connectPhase]}` : "저장소 연결",
        status: statusFor(3),
      },
      { label: "실행 환경", status: statusFor(4) },
      { label: "품질 보강 자료", status: statusFor(5) },
      { label: "최종 등록 확인", status: statusFor(6) },
    ];
  }, [view, createStep, busy, connectPhase, healthBusy, contextBusy]);

  if (view === "detail" && detailRow) {
    const detailSets = uniqueRepositorySets(detailRow.sets);
    const set = detailSets[0];
    const st = statusLabel(set?.status ?? "");
    const repositoryCount = detailSets.reduce(
      (total, repositorySet) => total + repositorySet.repositories.length,
      0,
    );
    const healthyEnvironmentCount = detailEnvironments.filter(
      (environment) => environment.lastHealthStatus === "up",
    ).length;
    return (
      <section
        className="page-shell table-workspace enterprise-page finance-page is-create anim-fade-in"
        data-testid="projects-workbench"
      >
        <div className="page-shell-card content-card enterprise-card fill-center finance-card">
          <div className="page-shell-header content-header finance-header">
            <div>
              <Breadcrumbs
                trail={[
                  { label: "콘솔", href: "/" },
                  { label: "프로젝트", href: "/projects" },
                  { label: "프로젝트 상세" },
                ]}
              />
              <h2 className="project-detail-title">
                <span>{detailRow.project.name}</span><b aria-hidden>›</b><small>프로젝트 상세</small>
              </h2>
              <p className="muted project-detail-lead">
                입력·연결 결과와 후속 프로세스를 한눈에 확인합니다.
              </p>
            </div>
          </div>
          <div className="page-shell-center">
            <div className="finance-wizard-panel anim-slide-up" data-testid="project-detail-panel">
              <div className="finance-wizard-body project-detail-body">
                <div className="project-detail-grid">
                  <section className="project-detail-section" aria-labelledby="project-info-heading">
                    <header className="project-detail-section-head">
                      <div>
                        <h4 id="project-info-heading">프로젝트 정보</h4>
                      </div>
                      <Tag
                        tone={st.tone === "ok" ? "positive" : st.tone === "bad" ? "negative" : "neutral"}
                        withIcon={st.tone === "ok"}
                      >
                        {st.text}
                      </Tag>
                    </header>
                    <dl className="project-detail-list">
                      <div><dt>설명</dt><dd>{descriptionParts(detailRow.project.description).description || "—"}</dd></div>
                      <div><dt>AI 실행 정책</dt><dd>{detailRow.project.modelSelectionMode === "manual" ? `역할별 고정 ${Object.values(detailRow.project.modelBindings || {}).filter(Boolean).length}개` : `자동 추천 · ${AI_POLICIES.find((item) => item.id === (detailRow.project.aiPolicy || "auto"))?.name}`}</dd></div>
                      <div><dt>등록/수정</dt><dd>{formatDateTime(detailRow.project.createdAt)} / {formatDateTime(detailRow.project.updatedAt || detailRow.project.createdAt)}</dd></div>
                    </dl>
                    <div className="project-detail-kpis" aria-label="프로젝트 연결 요약">
                      <div><strong>{repositoryCount}</strong><span>연결 저장소</span></div>
                      <div><strong>{healthyEnvironmentCount}</strong><span>정상 실행환경</span></div>
                      <div><strong>{contextDocuments.length}</strong><span>보강 자료</span></div>
                    </div>
                  </section>

                  <section
                    className="project-detail-section"
                    aria-labelledby="project-repository-heading"
                    data-testid="project-detail-repositories"
                  >
                    <header className="project-detail-section-head">
                      <div>
                        <h4 id="project-repository-heading">연결 저장소</h4>
                      </div>
                      <span className="project-detail-count">{detailSets.length}개 연결</span>
                    </header>
                    {detailSets.length === 0 ? (
                      <p className="project-detail-empty">연결된 저장소가 없습니다.</p>
                    ) : (
                      <div className="project-detail-card-grid">
                        {detailSets.map((repositorySet) => {
                          const repository = primaryRepo(repositorySet);
                          const repositoryStatus = statusLabel(repositorySet.status);
                          return (
                            <article key={repositorySet.id} className="project-detail-connection-card">
                              <header>
                                <div>
                                  <strong>{repositorySet.name}</strong>
                                </div>
                                <Tag
                                  tone={
                                    repositoryStatus.tone === "ok"
                                      ? "positive"
                                      : repositoryStatus.tone === "bad"
                                        ? "negative"
                                        : "neutral"
                                  }
                                >
                                  {repositoryStatus.text}
                                </Tag>
                              </header>
                              <dl>
                                <div><dt>연결 방식</dt><dd>{repository?.sourceType || "—"}</dd></div>
                                <div>
                                  <dt>저장소 위치</dt>
                                  <dd className="project-detail-path">{repository?.url || repository?.path || "—"}</dd>
                                </div>
                                <div><dt>동기화</dt><dd>{repository?.syncStatus || repositorySet.status || "—"}</dd></div>
                                <div><dt>파일</dt><dd>{repository?.fileCount ?? 0}개</dd></div>
                                <div><dt>Commit</dt><dd className="saas-cell-mono">{repository?.commitSha || "—"}</dd></div>
                              </dl>
                            </article>
                          );
                        })}
                      </div>
                    )}
                  </section>

                  <section
                    className="project-detail-section is-wide"
                    aria-labelledby="project-environment-heading"
                    data-testid="project-detail-environments"
                  >
                    <header className="project-detail-section-head">
                      <div>
                        <h4 id="project-environment-heading">실행 환경</h4>
                      </div>
                      <span className="project-detail-count">{detailEnvironments.length}개 등록</span>
                    </header>
                    {detailEnvironments.length === 0 ? (
                      <p className="project-detail-empty">등록된 실행 환경이 없습니다.</p>
                    ) : (
                      <div className="project-detail-environment-grid">
                        {detailEnvironments.map((env) => (
                          <article key={env.id} className="project-detail-environment-card">
                            <header>
                              <div>
                                <strong>{env.name}</strong>
                              </div>
                              <Tag tone={env.lastHealthStatus === "up" ? "positive" : "neutral"} withIcon>
                                Health {env.lastHealthStatus || "unknown"}
                              </Tag>
                            </header>
                            <p className="project-detail-environment-url">{env.frontendBaseUrl}</p>
                            <dl>
                              <div><dt>브라우저</dt><dd>{env.browser || "chrome"}</dd></div>
                              <div><dt>연결 ID</dt><dd>{env.loginId || "미등록"}</dd></div>
                              <div><dt>권한</dt><dd>{env.loginRole || "미지정"}</dd></div>
                              <div><dt>비밀번호</dt><dd>{env.hasLoginSecret ? "등록됨 (***)" : "미등록"}</dd></div>
                              <div><dt>상태</dt><dd>{env.status || "unknown"}</dd></div>
                              <div><dt>최근 확인</dt><dd>{formatDateTime(env.lastHealthAt || env.createdAt)}</dd></div>
                            </dl>
                          </article>
                        ))}
                      </div>
                    )}
                  </section>

                  <section
                    className="project-detail-section is-wide"
                    aria-labelledby="project-context-heading"
                    data-testid="project-detail-context-documents"
                  >
                    <header className="project-detail-section-head">
                      <div>
                        <h4 id="project-context-heading">테스트 시나리오 품질 보강 자료</h4>
                      </div>
                      <div className="project-detail-context-actions">
                        <span className="project-detail-count">{contextDocuments.length}개 등록</span>
                        <Button
                          variant="secondary"
                          size="sm"
                          busy={contextBusy}
                          onClick={() => document.getElementById("project-detail-context-files")?.click()}
                        >
                          자료 추가
                        </Button>
                        <input
                          id="project-detail-context-files"
                          type="file"
                          accept=".csv,.ppt,.pptx"
                          multiple
                          hidden
                          onChange={(event) => {
                            if (event.target.files?.length) void uploadContextFiles(event.target.files);
                            event.currentTarget.value = "";
                          }}
                        />
                      </div>
                    </header>
                    {contextDocuments.length === 0 ? (
                      <p className="project-detail-empty">등록된 보강 자료가 없습니다. 시나리오는 코드·DOM·LLM 기본 경로로 생성됩니다.</p>
                    ) : (
                      <div className="project-context-list">
                        {contextDocuments.map((item) => (
                          <article key={item.id} className={`project-context-item is-${item.status}`}>
                            <div className="project-context-file-icon">{item.kind === "scenario_csv" ? "CSV" : "PPT"}</div>
                            <div className="project-context-file-copy">
                              <div><strong>{item.fileName}</strong><span>{CONTEXT_STATUS_LABEL[item.status]}</span></div>
                              <p>{item.summary || item.error || "문서 컨텍스트를 처리하고 있습니다."}</p>
                              <div className="project-context-progress"><i style={{ width: `${item.progress}%` }} /></div>
                              <small>컨텍스트 {item.chunkCount}개 · 시나리오 힌트 {item.scenarioHintCount}개 · {item.indexBackend || "인덱스 준비 중"}</small>
                            </div>
                            <button
                              type="button"
                              className="ghost-btn"
                              disabled={contextBusy || ["queued", "extracting", "embedding"].includes(item.status)}
                              onClick={() => void deleteContextDocument(item.id)}
                            >삭제</button>
                          </article>
                        ))}
                      </div>
                    )}
                  </section>
                </div>
              </div>
            </div>
          </div>
          <div className="page-shell-footer-slot">
            <PageStickyFooter
              className="finance-wizard-foot"
              testId="project-detail-footer"
              note="Complete ≠ HITL Pass · 후속 CTA는 하단에서 진행합니다."
              actions={
                <>
                  <Button
                    variant="ghost"
                    size="md"
                    className="is-danger-text"
                    onClick={() => void deleteProject(detailRow.project.id, detailRow.project.name)}
                  >
                    삭제
                  </Button>
                  <Button variant="secondary" size="md" onClick={() => openEdit(detailRow.project.id)}>
                    수정
                  </Button>
                  <Button
                    variant="secondary"
                    size="md"
                    busy={detailSets.some((item) => syncingSetIds.has(item.id))}
                    disabled={detailSets.length === 0}
                    onClick={() => void syncRepositorySets(detailSets.map((item) => item.id))}
                    data-testid="project-detail-sync"
                  >
                    저장소 동기화
                  </Button>
                  <Button
                    variant="secondary"
                    size="md"
                    disabled={detailSets.length === 0}
                    onClick={() => openAnalysis(detailRow.project.id)}
                    data-testid="project-detail-analysis-menu"
                  >
                    분석 메뉴
                  </Button>
                  <Button variant="primary" size="md" onClick={backToList}>
                    프로젝트 목록으로
                  </Button>
                </>
              }
            />
          </div>
        </div>
      </section>
    );
  }

  if (view === "create" || view === "edit") {
    const stepTitle =
      createStep === 1
        ? view === "edit" ? "프로젝트 정보를 수정하세요" : "프로젝트 이름을 입력하세요"
        : createStep === 2
          ? "이 프로젝트에서 사용할 AI 모델을 정하세요"
          : createStep === 3
            ? view === "edit" ? "연결 저장소를 수정하세요" : "저장소를 연결하세요"
            : createStep === 4
              ? view === "edit" ? "실행 환경을 수정하세요" : "실행 중인 개발 서버를 등록하세요"
              : createStep === 5
                ? "테스트 시나리오 품질 보강 자료를 추가하세요"
                : "최종 등록 결과를 확인하세요";
    const stepHint =
      createStep === 1
        ? "이름·설명·태그로 프로젝트를 구분합니다. 다음 단계에서 AI 실행 방식을 정합니다."
        : createStep === 2
          ? "자동 추천을 그대로 쓰거나, 필요한 역할만 모델 관리에 등록된 모델로 고정할 수 있습니다."
          : createStep === 3
            ? "GitHub URL 또는 로컬 경로만 입력하면 저장소 루트를 연결합니다."
            : createStep === 4
              ? "실제 테스트 실행을 위해 기동 중인 개발 서버의 IP, Port 또는 URL을 입력하세요. 기본 예시는 Cymbal Bank입니다."
              : createStep === 5
                ? "현업 CSV는 정형 데이터로, 설계 PPTX는 VLM 관측과 임베딩으로 처리합니다. 자료가 없으면 건너뛸 수 있습니다."
                : "프로젝트 등록이 모두 완료되면, 코드 자동 분석이 진행됩니다.";
    const tipTitle =
      createStep === 1
        ? "등록 가이드"
        : createStep === 2
          ? "모델 선택 가이드"
          : createStep === 3
            ? "저장소 연결 팁"
            : createStep === 4
              ? "실행 환경 팁"
              : createStep === 5
                ? "자료 활용 원칙"
                : "다음 단계";
    const tipBody =
      createStep === 1 ? (
        <ol>
          <li>프로젝트 이름은 목록·분석·시나리오에서 공통으로 표시됩니다.</li>
          <li>태그는 검색·분류용이며 Secret을 넣지 마세요.</li>
          <li>다음 단계에서 자동 추천 또는 역할별 고정을 선택합니다.</li>
        </ol>
      ) : createStep === 2 ? (
        <ol>
          <li><b>자동 추천</b>은 모델 선택을 상황에 맞게 자동으로 추천합니다.</li>
          <li><b>역할별 고정</b>은 모델 관리 메뉴에서 등록된 모델을 직접 선택합니다..</li>
          <li>GPT Image 계열은 이미지 생성·편집용입니다. 화면 인식은 vision 모델을 선택하세요.</li>
        </ol>
      ) : createStep === 3 ? (
        <ol>
          <li>파일럿 기본 URL: GoogleCloudPlatform/bank-of-anthos</li>
          <li>모노레포는 루트를 연결합니다 (하위 FE/BE 경로 불필요).</li>
          <li>연결 중에는 Progress Type4로 동기화 상태를 표시합니다.</li>
        </ol>
      ) : createStep === 4 ? (
        <ol>
          <li>기본 프리셋: https://cymbal-bank.fsi.cymbal.dev/</li>
          <li>등록 시 Health Check를 수행하며 up/down만 관측합니다.</li>
          <li>이후 시나리오 실행은 이 URL을 agent-browser baseUrl로 사용합니다.</li>
        </ol>
      ) : createStep === 5 ? (
        <ol>
          <li>CSV: 시나리오 ID·설명·요청값·응답값을 정형화합니다.</li>
          <li>PPTX: 슬라이드 텍스트와 화면 이미지를 VLM로 읽고 로컬 FAISS에 임베딩합니다.</li>
          <li>문서는 보조 근거입니다. 코드 Graph·DOM·API와 일치하는 내용만 실행 DSL에 반영합니다.</li>
          <li>업로드 자료가 없으면 기존 코드+DOM+LLM 경로를 그대로 사용합니다.</li>
        </ol>
      ) : (
        <ol>
          <li>저장소 연결·동기화 → 코드 자동 분석 → 분석 메뉴에서 결과 확인</li>
          <li>시나리오 목록에서 실행 환경으로 agent-browser 테스트</li>
          <li>증적(스크린샷·snapshot) 확인 · HITL은 사람이 확정</li>
        </ol>
      );
    const activeModelRole = MODEL_ROLES.find((item) => item.id === modelPickerRole) ?? null;

    return (
      <section
        className="page-shell table-workspace enterprise-page finance-page is-create anim-fade-in"
        data-testid="projects-workbench"
      >
        <div className="page-shell-card content-card enterprise-card fill-center finance-card">
          <div className="page-shell-header">
            <div className="content-header finance-header">
              <div>
                <p className="breadcrumbs">콘솔 / 프로젝트 / {view === "edit" ? "수정" : "생성"}</p>
                <h2>{view === "edit" ? "프로젝트 수정" : "프로젝트 생성"}</h2>
                <p className="muted" style={{ marginTop: 4 }}>
                  {view === "edit" ? "원하는 STEP을 눌러 해당 정보만 바로 수정할 수 있습니다." : "필요한 정보를 단계별로 입력합니다."}
                </p>
              </div>
            </div>

            <div className="finance-progress-wrap" data-testid="project-create-steps">
              <ProgressBarType2
                steps={createProgressSteps}
                testId="project-create-progress-type2"
                pulseFinal={createStep === 6}
                onStepClick={view === "edit" ? (index) => setCreateStep((index + 1) as CreateStep) : undefined}
              />
              {(connectPhase !== "idle" || (busy && createStep === 3)) && createStep === 3 && (
                <div className="finance-connect-progress anim-slide-down" data-testid="project-connect-progress-type4">
                  <ProgressBarType4
                    title="저장소 연결·자동 분석 진행"
                    stepLabel={CONNECT_PHASE_LABEL[connectPhase === "idle" ? "registering" : connectPhase]}
                    percent={connectPercent || (busy ? 8 : 0)}
                    eta={connectPhase === "complete" ? undefined : "완료 후 실행 환경 등록으로 이동합니다"}
                    status={
                      connectPhase === "error"
                        ? "error"
                        : connectPhase === "complete"
                          ? "complete"
                          : "progressing"
                    }
                    testId="project-connect-type4"
                  />
                </div>
              )}
            </div>

            {message && (
              <div className={`connect-banner ${ok ? "is-ok" : "is-warn"} anim-slide-down`}>{message}</div>
            )}
          </div>

          <div className="page-shell-center finance-wizard-panel anim-fade-in" key={`${view}-${createStep}`}>
            <header className="finance-wizard-head">
              <p className="finance-wizard-kicker">STEP {createStep} / 6</p>
              <h3>{stepTitle}</h3>
              <p className="muted">{stepHint}</p>
            </header>

            <div className="finance-wizard-body">
              {createStep === 1 && (
                <div className="finance-create-layout anim-fade-in">
                  <div className="finance-create-main">
                    <div className="finance-field-stack" style={{ maxWidth: "none", margin: 0 }}>
                      <label className="finance-field">
                        <span className="finance-field-label">프로젝트 이름</span>
                        <input
                          value={projectName}
                          onChange={(e) => setProjectName(e.target.value)}
                          placeholder="예: 고객조회 체인"
                          data-testid="project-name-input"
                          autoFocus
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              void (view === "edit" ? renameProject() : createProject());
                            }
                          }}
                        />
                        <span className="finance-field-hint">2자 이상 권장 · 나중에 수정할 수 있습니다.</span>
                      </label>
                      <label className="finance-field">
                        <span className="finance-field-label">설명 (선택)</span>
                        <textarea
                          value={projectDescription}
                          onChange={(e) => setProjectDescription(e.target.value)}
                          placeholder="예: bank-of-anthos 기반 A→API→B 관통 검증용 프로젝트"
                          data-testid="project-description-input"
                        />
                      </label>
                      <label className="finance-field">
                        <span className="finance-field-label">태그 (선택)</span>
                        <input
                          value={projectTags}
                          onChange={(e) => setProjectTags(e.target.value)}
                          placeholder="예: pilot, e2e, github"
                          data-testid="project-tags-input"
                        />
                        <span className="finance-field-hint">쉼표로 구분 · 최대 8개</span>
                        {tagList.length > 0 && (
                          <span className="finance-tag-preview">
                            {tagList.map((t) => (
                              <Tag key={t} tone="neutral">
                                {t}
                              </Tag>
                            ))}
                          </span>
                        )}
                      </label>
                    </div>
                  </div>
                  <aside className="finance-create-aside">
                    <h4>{tipTitle}</h4>
                    {tipBody}
                  </aside>
                </div>
              )}

              {createStep === 2 && (
                <div className="finance-create-layout anim-fade-in" data-testid="project-model-settings">
                  <div className="finance-create-main project-model-settings-main">
                    <div className="model-strategy-grid" role="radiogroup" aria-label="모델 선택 방식">
                      <label className={modelSelectionMode === "auto" ? "is-selected" : ""}>
                        <input
                          type="radio"
                          name="modelSelectionMode"
                          checked={modelSelectionMode === "auto"}
                          onChange={() => setModelSelectionMode("auto")}
                        />
                        <span><b>AI 자동 추천</b><small>작업마다 capability·context·health를 비교해 가장 적합한 모델을 선택합니다.</small></span>
                        <em>DEFAULT</em>
                      </label>
                      <label className={modelSelectionMode === "manual" ? "is-selected" : ""}>
                        <input
                          type="radio"
                          name="modelSelectionMode"
                          checked={modelSelectionMode === "manual"}
                          onChange={() => setModelSelectionMode("manual")}
                        />
                        <span><b>역할별 모델 고정</b><small>원하는 역할만 등록 모델로 고정합니다. 선택하지 않은 역할은 자동 추천됩니다.</small></span>
                      </label>
                    </div>

                    {modelSelectionMode === "auto" ? (
                      <fieldset className="ai-policy-field" data-testid="project-ai-policy">
                        <legend>AI 실행 정책</legend>
                        <p>자동 추천 안에서 품질·비용·속도의 우선순위를 정합니다.</p>
                        <div className="ai-policy-grid">
                          {AI_POLICIES.map((policy) => (
                            <label key={policy.id} className={aiPolicy === policy.id ? "is-selected" : ""}>
                              <input
                                type="radio"
                                name="aiPolicy"
                                value={policy.id}
                                checked={aiPolicy === policy.id}
                                onChange={() => setAiPolicy(policy.id)}
                              />
                              <span><b>{policy.name}</b><small>{policy.description}</small></span>
                            </label>
                          ))}
                        </div>
                        <small>후보 점수와 제외 사유, 실제 호출 여부는 관리 › Agent 모니터링에서 확인합니다.</small>
                      </fieldset>
                    ) : (
                      <div className="project-model-role-grid">
                        {MODEL_ROLES.map((role) => {
                          const selected = modelProfiles.find((item) => item.id === modelBindings[role.id]);
                          return (
                            <article key={role.id} className={selected ? "is-bound" : ""}>
                              <div>
                                <span>{role.name}</span>
                                <small>{role.description}</small>
                                <div className="model-role-caps">
                                  {role.requiredCapabilities.map((capability) => <i key={capability}>{capability}</i>)}
                                </div>
                              </div>
                              <div className="model-role-selection">
                                {selected ? (
                                  <span><b>{selected.displayName}</b><small>{selected.modelId}</small></span>
                                ) : <em>자동 추천 유지</em>}
                                <Button
                                  variant="secondary"
                                  size="sm"
                                  onClick={() => setModelPickerRole(role.id)}
                                  data-testid={`project-model-select-${role.id}`}
                                >
                                  {selected ? "모델 변경" : "모델 선택"}
                                </Button>
                                {selected && (
                                  <button
                                    type="button"
                                    className="link-btn model-role-reset"
                                    onClick={() => setModelBindings((current) => {
                                      const next = { ...current };
                                      delete next[role.id];
                                      return next;
                                    })}
                                  >자동 추천으로
                                  </button>
                                )}
                              </div>
                            </article>
                          );
                        })}
                        <Button variant="secondary" size="sm" onClick={() => router.push("/manage/models")}>모델 관리 열기</Button>
                      </div>
                    )}
                  </div>
                  <aside className="finance-create-aside project-model-guide">
                    <img src="/dashboard/qa-robot.png" alt="AI 모델 설정을 안내하는 로봇" />
                    <div><h4>{tipTitle}</h4>{tipBody}</div>
                  </aside>
                </div>
              )}

              {createStep === 3 && (
                <div className="finance-create-layout anim-fade-in">
                  <div className="finance-create-main">
                    <div className="finance-field-stack" style={{ maxWidth: "none", margin: 0 }}>
                      <label className="finance-field">
                        <span className="finance-field-label">연결 방식</span>
                        <select value={mode} onChange={(e) => setMode(e.target.value as "github" | "local")}>
                          <option value="github">GitHub URL</option>
                          <option value="local">로컬 경로</option>
                        </select>
                      </label>
                      {mode === "github" ? (
                        <label className="finance-field">
                          <span className="finance-field-label">GitHub URL</span>
                          <input
                            value={githubUrl}
                            onChange={(e) => {
                              setGithubUrl(e.target.value);
                              if (!repoName) setRepoName(guessRepoNameFromUrl(e.target.value));
                            }}
                            placeholder="https://github.com/org/repo.git"
                            data-testid="github-url-input"
                          />
                        </label>
                      ) : (
                        <label className="finance-field">
                          <span className="finance-field-label">로컬 경로</span>
                          <input
                            value={localPath}
                            onChange={(e) => {
                              setLocalPath(e.target.value);
                              if (!repoName) setRepoName(guessRepoNameFromPath(e.target.value));
                            }}
                            placeholder="/Users/…/my-repo"
                            data-testid="local-path-input"
                          />
                        </label>
                      )}
                      <label className="finance-field">
                        <span className="finance-field-label">저장소 표시 이름</span>
                        <input
                          value={repoName}
                          onChange={(e) => setRepoName(e.target.value)}
                          placeholder={
                            mode === "github"
                              ? guessRepoNameFromUrl(githubUrl) || "예: bank-of-anthos"
                              : guessRepoNameFromPath(localPath) || "예: my-service"
                          }
                        />
                        <span className="finance-field-hint">
                          Frontend/Backend 하위 경로는 묻지 않습니다. 저장소 루트를 그대로 연결합니다.
                        </span>
                      </label>
                    </div>
                  </div>
                  <aside className="finance-create-aside">
                    <h4>{tipTitle}</h4>
                    {tipBody}
                  </aside>
                </div>
              )}

              {createStep === 4 && (
                <div className="finance-create-layout anim-fade-in" data-testid="project-environment-form">
                  <div className="finance-create-main">
                    <div className="finance-field-stack" style={{ maxWidth: "none", margin: 0 }}>
                      <label className="finance-field">
                        <span className="finance-field-label">환경 프리셋</span>
                        <select
                          defaultValue="cymbal-bank"
                          onChange={(e) => applyEnvPreset(e.target.value)}
                          data-testid="env-preset-select"
                        >
                          {(envPresets.length
                            ? envPresets
                            : [
                                {
                                  key: "cymbal-bank",
                                  name: "Cymbal Bank (FSI)",
                                  frontendBaseUrl: CYMBAL_BANK_URL,
                                },
                              ]
                          ).map((p) => (
                            <option key={p.key} value={p.key}>
                              {p.name}
                            </option>
                          ))}
                        </select>
                        <span className="finance-field-hint">
                          실제 테스트 실행을 위해 현재 기동되어 있는 개발 서버 URL을 등록합니다.
                        </span>
                      </label>
                      <label className="finance-field">
                        <span className="finance-field-label">환경 이름</span>
                        <input
                          value={envName}
                          onChange={(e) => setEnvName(e.target.value)}
                          placeholder="예: Cymbal Bank (FSI)"
                          data-testid="env-name-input"
                        />
                      </label>
                      <label className="finance-field">
                        <span className="finance-field-label">연결 URL (필수)</span>
                        <input
                          value={frontendBaseUrl}
                          onChange={(e) => setFrontendBaseUrl(e.target.value)}
                          placeholder={CONNECT_DEFAULTS.url}
                          required
                          data-testid="env-frontend-url-input"
                        />
                        <span className="finance-field-hint">
                          파일럿 대상: {CONNECT_DEFAULTS.url}
                        </span>
                      </label>
                      <label className="finance-field">
                        <span className="finance-field-label">연결 BROWSER (필수)</span>
                        <select
                          value={connectBrowser}
                          onChange={(e) => setConnectBrowser(e.target.value)}
                          required
                          data-testid="env-browser-select"
                        >
                          {BROWSER_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label className="finance-field">
                        <span className="finance-field-label">계정 권한 (필수)</span>
                        <input
                          value={connectLoginRole}
                          onChange={(e) => setConnectLoginRole(e.target.value)}
                          placeholder="관리자"
                          required
                          data-testid="env-login-role-input"
                        />
                        <span className="finance-field-hint">
                          초기 분석 범위를 넓히기 위해 가급적 관리자 계정을 등록하세요. 실제 실행에서는 시나리오별 계정을 다시 선택합니다.
                        </span>
                      </label>
                      <label className="finance-field">
                        <span className="finance-field-label">연결 ID (필수)</span>
                        <input
                          value={connectLoginId}
                          onChange={(e) => setConnectLoginId(e.target.value)}
                          placeholder={CONNECT_DEFAULTS.loginId}
                          required
                          autoComplete="off"
                          data-testid="env-login-id-input"
                        />
                      </label>
                      <label className="finance-field">
                        <span className="finance-field-label">연결 PASSWORD (필수)</span>
                        <input
                          type="password"
                          value={connectPassword}
                          onChange={(e) => setConnectPassword(e.target.value)}
                          placeholder="••••••••"
                          required
                          autoComplete="new-password"
                          data-testid="env-login-password-input"
                        />
                        <span className="finance-field-hint">
                          로그인이 필요한 화면은 이 계정으로 통과합니다. 값은 화면·증적·로그에 남지 않고
                          실행기에만 전달됩니다.
                        </span>
                      </label>
                      <label className="finance-field">
                        <span className="finance-field-label">Backend Base URL (선택)</span>
                        <input
                          value={backendBaseUrl}
                          onChange={(e) => setBackendBaseUrl(e.target.value)}
                          placeholder="예: https://api.example.com/"
                          data-testid="env-backend-url-input"
                        />
                      </label>
                      <label className="finance-field">
                        <span className="finance-field-label">Health Check Path</span>
                        <input
                          value={healthCheckPath}
                          onChange={(e) => setHealthCheckPath(e.target.value)}
                          placeholder="/"
                          data-testid="env-health-path-input"
                        />
                      </label>
                    </div>
                  </div>
                  <aside className="finance-create-aside">
                    <h4>{tipTitle}</h4>
                    {tipBody}
                  </aside>
                </div>
              )}

              {createStep === 5 && confirmSummary && (
                <div className="project-context-layout anim-fade-in" data-testid="project-context-step">
                  <section className="project-context-main">
                    <div className="project-context-intro">
                      <div>
                        <p className="finance-wizard-kicker">OPTIONAL CONTEXT</p>
                        <h4>테스트 시나리오 품질을 높일 추가 자료가 있나요?</h4>
                        <p>
                          현업 테스트 CSV와 설계 PPTX를 올리면 Project Context Agent가 필요한 자료를 찾아
                          코드·DOM·API 근거와 함께 Scenario Agent에 전달합니다.
                        </p>
                      </div>
                      <Tag tone={contextDocuments.some((item) => item.status === "ready" || item.status === "partial") ? "positive" : "neutral"} withIcon>
                        준비 {contextDocuments.filter((item) => item.status === "ready" || item.status === "partial").length}건
                      </Tag>
                    </div>

                    <div
                      className={`project-context-dropzone ${contextDragActive ? "is-dragging" : ""}`}
                      role="button"
                      tabIndex={0}
                      aria-label="테스트 시나리오 보강 자료 업로드"
                      onClick={() => document.getElementById("project-context-files")?.click()}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          document.getElementById("project-context-files")?.click();
                        }
                      }}
                      onDragEnter={(event) => { event.preventDefault(); setContextDragActive(true); }}
                      onDragOver={(event) => { event.preventDefault(); setContextDragActive(true); }}
                      onDragLeave={(event) => { event.preventDefault(); setContextDragActive(false); }}
                      onDrop={(event) => {
                        event.preventDefault();
                        setContextDragActive(false);
                        void uploadContextFiles(event.dataTransfer.files);
                      }}
                      data-testid="project-context-dropzone"
                    >
                      <span className="project-context-drop-icon">＋</span>
                      <strong>{contextBusy ? "업로드·처리 요청 중…" : "파일을 여기로 끌어 놓거나 클릭해 선택하세요"}</strong>
                      <small>CSV · PPTX · PPT (최대 30MB) · 여러 파일 선택 가능</small>
                      <input
                        id="project-context-files"
                        type="file"
                        accept=".csv,.ppt,.pptx,text/csv,application/vnd.openxmlformats-officedocument.presentationml.presentation"
                        multiple
                        hidden
                        disabled={contextBusy}
                        onChange={(event) => {
                          if (event.target.files?.length) void uploadContextFiles(event.target.files);
                          event.currentTarget.value = "";
                        }}
                        data-testid="project-context-file-input"
                      />
                    </div>

                    <div className="project-context-types">
                      <article><b>CSV · 정형 데이터</b><span>시나리오 ID · 설명 · 요청값 · 응답값을 행 단위로 검증합니다.</span></article>
                      <article><b>PPTX · 비정형 데이터</b><span>슬라이드 텍스트 + VLM 화면 OCR → 임베딩 → 로컬 FAISS 인덱스</span></article>
                    </div>

                    <div className="project-context-list" aria-live="polite">
                      {contextDocuments.length === 0 ? (
                        <div className="project-context-empty">
                          <strong>추가 자료 없이도 계속할 수 있습니다.</strong>
                          <span>이 경우 기존 코드 분석 + 실행 DOM + 시스템 프롬프트 + LLM 경로로 생성합니다.</span>
                        </div>
                      ) : contextDocuments.map((item) => (
                        <article key={item.id} className={`project-context-item is-${item.status}`}>
                          <div className="project-context-file-icon">{item.kind === "scenario_csv" ? "CSV" : "PPT"}</div>
                          <div className="project-context-file-copy">
                            <div><strong>{item.fileName}</strong><span>{(item.sizeBytes / 1024).toFixed(1)} KB</span></div>
                            <p>{item.summary || CONTEXT_STATUS_LABEL[item.status]}{item.error ? ` · ${item.error}` : ""}</p>
                            <div className="project-context-progress" aria-label={`${item.fileName} 처리 ${item.progress}%`}>
                              <i style={{ width: `${item.progress}%` }} />
                            </div>
                            <small>
                              {CONTEXT_STATUS_LABEL[item.status]} · 컨텍스트 {item.chunkCount}개 · 시나리오 힌트 {item.scenarioHintCount}개
                              {item.indexBackend ? ` · ${item.indexBackend}` : ""}
                            </small>
                          </div>
                          <button
                            type="button"
                            className="ghost-btn"
                            disabled={contextBusy || ["extracting", "embedding"].includes(item.status)}
                            onClick={() => void deleteContextDocument(item.id)}
                            aria-label={`${item.fileName} 삭제`}
                          >
                            삭제
                          </button>
                        </article>
                      ))}
                    </div>
                  </section>
                  <aside className="finance-create-aside project-context-aside">
                    <h4>{tipTitle}</h4>
                    {tipBody}
                    <div className="project-context-agent-path">
                      <span>Scenario 생성 분기</span>
                      <b>자료 탐색 Skill</b>
                      <i>↓</i>
                      <b>{contextDocuments.length ? "문서 + 코드 + DOM + LLM" : "코드 + DOM + LLM"}</b>
                      <small>문서는 단독 확정 근거가 아니며 충돌은 unresolved로 남깁니다.</small>
                    </div>
                  </aside>
                </div>
              )}

              {createStep === 6 && confirmSummary && (
                <div data-testid="project-confirm-summary" className="anim-fade-in">
                  <div className="finance-result-cards">
                    <article className="finance-result-card">
                      <p className="card-kicker">PROJECT</p>
                      <h4>{confirmSummary.projectName}</h4>
                      <div className="card-mono">{confirmSummary.projectId}</div>
                      <p className="card-meta">
                        {confirmSummary.description || "설명 없음"}
                        {confirmSummary.tags.length
                          ? ` · ${confirmSummary.tags.join(", ")}`
                          : ""}
                      </p>
                      <p className="card-meta">생성 {formatDateTime(confirmSummary.createdAt)}</p>
                      <p className="card-meta">등록 정보는 각 STEP을 눌러 바로 수정할 수 있습니다.</p>
                    </article>
                    <article className="finance-result-card is-emphasis">
                      <p className="card-kicker">MODEL ROUTING</p>
                      <h4>{confirmSummary.modelSelectionMode === "manual" ? "역할별 모델 고정" : "AI 자동 추천"}</h4>
                      <div className="card-mono">
                        {confirmSummary.modelSelectionMode === "manual"
                          ? `고정 ${Object.values(confirmSummary.modelBindings || {}).filter(Boolean).length}개 · 나머지 자동`
                          : AI_POLICIES.find((item) => item.id === (confirmSummary.aiPolicy || "auto"))?.name}
                      </div>
                      <p className="card-meta">선택·실제 호출·fallback은 Agent 모니터링에 분리 기록됩니다.</p>
                    </article>
                    <article className="finance-result-card">
                      <p className="card-kicker">REPOSITORY</p>
                      <h4>{confirmSummary.repoName}</h4>
                      <div className="card-mono">{confirmSummary.location || "—"}</div>
                      <p className="card-meta">
                        {confirmSummary.mode === "github" ? "GitHub URL" : "로컬 경로"} · 연결{" "}
                        {formatDateTime(confirmSummary.connectedAt)}
                      </p>
                      <Tag tone="positive" withIcon>
                        연결완료
                      </Tag>
                    </article>
                    <article className="finance-result-card is-emphasis">
                      <p className="card-kicker">AUTO ANALYSIS</p>
                      <h4>
                        {confirmSummary.analysisStatus === "complete"
                          ? "자동 분석 완료"
                          : confirmSummary.analysisStatus === "partial"
                            ? "일부 확인 필요"
                            : "분석 상태 확인 필요"}
                      </h4>
                      <div className="card-mono">분석 결과 {confirmSummary.analysisCount ?? 0}건</div>
                      <p className="card-meta">저장소 연결 직후 DOM 구조와 코드를 자동 분석했습니다.</p>
                      <Tag tone={confirmSummary.analysisStatus === "complete" ? "positive" : "warning"} withIcon>
                        {confirmSummary.analysisStatus === "complete" ? "분석완료" : "확인필요"}
                      </Tag>
                    </article>
                    <article className="finance-result-card is-emphasis">
                      <p className="card-kicker">QUALITY CONTEXT</p>
                      <h4>{confirmSummary.contextReadyCount ? "보강 컨텍스트 준비" : "기본 생성 경로"}</h4>
                      <div className="card-mono">자료 {confirmSummary.contextDocumentCount ?? 0}건 · 준비 {confirmSummary.contextReadyCount ?? 0}건</div>
                      <p className="card-meta">Scenario 생성 시 Project Context 탐색 Skill이 자료 존재 여부를 먼저 판단합니다.</p>
                    </article>
                    <article className="finance-result-card is-emphasis">
                      <p className="card-kicker">EXECUTION ENV</p>
                      <h4>{confirmSummary.environmentName || "미등록"}</h4>
                      <div className="card-mono">{confirmSummary.frontendBaseUrl || "—"}</div>
                      <p className="card-meta">
                        Health: {confirmSummary.healthStatus || "unknown"} · agent-browser 실행 baseUrl
                      </p>
                      {confirmSummary.environmentId ? (
                        <div className="card-mono">{confirmSummary.environmentId}</div>
                      ) : null}
                    </article>
                  </div>
                  <aside className="finance-create-aside finance-final-next">
                    <h4>{tipTitle}</h4>
                    {tipBody}
                  </aside>
                </div>
              )}
            </div>

          </div>

          <div className="page-shell-footer-slot">
            <PageStickyFooter
              className="finance-wizard-foot"
              testId="project-wizard-footer"
              note={
                createStep === 6
                  ? "Complete는 기술 연결 완료이며 HITL Pass가 아닙니다."
                  : createStep === 5
                    ? contextProcessing
                      ? "업로드 자료 처리 중입니다. 완료 또는 오류 상태가 되면 다음 단계로 이동할 수 있습니다."
                      : "추가 자료는 선택사항이며, 삭제하면 이후 Scenario Agent 컨텍스트에서 제외됩니다."
                  : createStep === 4
                    ? "서버 미기동 시 Health는 down/error로 표시되며, 코드 분석만은 계속할 수 있습니다."
                    : createStep === 2
                      ? "외부 모델의 API Key는 저장하지 않으며 서버 재시작 후 다시 입력해야 합니다."
                    : undefined
              }
              actions={
                <>
                  {createStep === 1 && (
                    <>
                      <Button variant="secondary" size="md" onClick={backToList}>
                        {view === "edit" ? "목록으로" : "취소"}
                      </Button>
                      <Button
                        variant="primary"
                        size="md"
                        busy={busy}
                        disabled={!projectName.trim()}
                        onClick={() => void (view === "edit" ? renameProject() : createProject())}
                        data-testid="project-create-btn"
                      >
                        {view === "edit" ? "프로젝트 정보 저장" : "다음 · 모델 설정"}
                      </Button>
                    </>
                  )}
                  {createStep === 2 && (
                    <>
                      <Button variant="secondary" size="md" onClick={view === "edit" ? backToList : () => setCreateStep(1)}>
                        {view === "edit" ? "목록으로" : "이전 · 프로젝트 이름"}
                      </Button>
                      <Button
                        variant="primary"
                        size="md"
                        busy={busy}
                        onClick={() => void saveModelSettings()}
                        data-testid="project-model-settings-save"
                      >
                        {view === "edit" ? "모델 설정 저장" : "저장 · 다음 저장소 연결"}
                      </Button>
                    </>
                  )}
                  {createStep === 3 && (
                    <>
                      {view === "create" ? (
                        <Button variant="secondary" size="md" onClick={() => setCreateStep(2)}>
                          이전 · 모델 설정
                        </Button>
                      ) : (
                        <Button variant="secondary" size="md" onClick={backToList}>
                          목록으로
                        </Button>
                      )}
                      {connectionReady ? (
                        <>
                          <Button
                            variant="secondary"
                            size="md"
                            onClick={() => confirmSummary && openAnalysis(confirmSummary.projectId)}
                            data-testid="project-connect-analysis-menu"
                          >
                            분석 메뉴
                          </Button>
                          <Button
                            variant="primary"
                            size="md"
                            onClick={() => {
                              setCreateStep(4);
                              setConnectPhase("idle");
                              setConnectPercent(0);
                            }}
                            data-testid="project-connect-next-environment"
                          >
                            다음 · 실행 환경
                          </Button>
                        </>
                      ) : (
                        <Button
                          variant="primary"
                          size="md"
                          busy={busy}
                          onClick={() => void connectRepo()}
                          data-testid="repo-connect-btn"
                        >
                          {busy ? "연결 중…" : view === "edit" ? "저장소 연결 저장" : "저장소 연결"}
                        </Button>
                      )}
                    </>
                  )}
                  {createStep === 4 && (
                    <>
                      <Button variant="secondary" size="md" onClick={view === "edit" ? backToList : () => setCreateStep(3)}>
                        {view === "edit" ? "목록으로" : "이전"}
                      </Button>
                      <Button
                        variant="primary"
                        size="md"
                        busy={busy || healthBusy}
                        disabled={!frontendBaseUrl.trim()}
                        onClick={() => void saveEnvironment()}
                        data-testid="env-save-btn"
                      >
                        {healthBusy ? "Health Check 중…" : view === "edit" ? "실행 환경 저장 · Health Check" : "환경 등록 · Health Check"}
                      </Button>
                    </>
                  )}
                  {createStep === 5 && confirmSummary && (
                    <>
                      <Button
                        variant="secondary"
                        size="md"
                        onClick={view === "edit" ? backToList : () => setCreateStep(4)}
                      >
                        {view === "edit" ? "수정 완료" : "이전 · 실행 환경"}
                      </Button>
                      <Button
                        variant="primary"
                        size="md"
                        disabled={contextBusy || contextProcessing}
                        onClick={() => setCreateStep(6)}
                        data-testid="project-context-next"
                      >
                        {contextDocuments.length ? "컨텍스트 저장 · 최종 확인" : "건너뛰기 · 최종 확인"}
                      </Button>
                    </>
                  )}
                  {createStep === 6 && confirmSummary && (
                    <>
                      <Button
                        variant="secondary"
                        size="md"
                        onClick={() => openAnalysis(confirmSummary.projectId)}
                        data-testid="project-confirm-analysis-menu"
                      >
                        분석 메뉴
                      </Button>
                      <Button
                        variant="secondary"
                        size="md"
                        onClick={() => setCreateStep(5)}
                        data-testid="project-confirm-context-edit"
                      >
                        보강 자료 수정
                      </Button>
                      <Button
                        variant="primary"
                        size="md"
                        onClick={backToList}
                        data-testid="project-to-list"
                      >
                        프로젝트 목록으로
                      </Button>
                    </>
                  )}
                </>
              }
            />
          </div>
        </div>
        {activeModelRole && (
          <ModelSelectionDialog
            open
            roleLabel={activeModelRole.name}
            roleDescription={activeModelRole.description}
            models={modelProfiles}
            requiredCapabilities={activeModelRole.requiredCapabilities}
            selectedId={modelBindings[activeModelRole.id]}
            onSelect={(profile) => setModelBindings((current) => ({
              ...current,
              [activeModelRole.id]: profile.id,
            }))}
            onClose={() => setModelPickerRole(null)}
          />
        )}
      </section>
    );
  }

  return (
    <section className="page-shell table-workspace enterprise-page finance-page anim-fade-in" data-testid="projects-workbench">
      <div className="page-shell-card content-card enterprise-card fill-center finance-card">
        <div className="page-shell-header content-header finance-header">
          <div>
            <Breadcrumbs trail={[{ label: "콘솔", href: "/" }, { label: "프로젝트" }]} />
            <h2>프로젝트</h2>
            <p className="muted" style={{ marginTop: 4 }}>
              프로젝트와 연결 저장소를 한곳에서 관리합니다.
            </p>
          </div>
        </div>

        <div className="page-shell-center">
        {message && (
          <div className={`connect-banner ${ok ? "is-ok" : "is-warn"} anim-slide-down`}>{message}</div>
        )}

        <CommonDataTable
          rows={visibleRows}
          totalCount={rows.length}
          toolbar={
            <>
              <ScreenSearch
                value={query}
                onChange={setQuery}
                placeholder="프로젝트명 · 저장소 경로"
                testId="projects-search"
                hint="프로젝트명·ID·저장소 URL/경로로 찾습니다"
              />
              <TableBulkDeleteForm
                embedded
                noun="프로젝트"
                totalCount={visibleRows.length}
                selectedCount={checkedIds.size}
                busy={busy}
                onDelete={() => void bulkDeleteProjects()}
                testId="projects-bulk-form"
                extraActions={
                  cachedHint.length > 0 && rows.length === 0 ? (
                    <span className="saas-toolbar-chip">로컬 캐시 있음</span>
                  ) : (
                    <span className="saas-toolbar-chip">
                      저장소 {rows.reduce((n, r) => n + r.sets.length, 0)}건
                    </span>
                  )
                }
              />
            </>
          }
          rowKey={(row) => row.project.id}
          columns={[
            {
              key: "project",
              label: "프로젝트",
              cell: (row) => <><strong className="saas-cell-strong id-link">{row.project.name}</strong><div className="saas-cell-sub">{row.project.id}</div></>,
              sortValue: (row) => row.project.name,
            },
            {
              key: "status",
              label: "상태",
              cell: (row) => {
                const status = statusLabel(row.sets[0]?.status ?? "");
                const tone = status.tone === "ok" ? "positive" : status.tone === "warn" ? "warning" : status.tone === "bad" ? "negative" : "neutral";
                return <Tag tone={tone} withIcon={tone === "positive"}>{status.text}</Tag>;
              },
              sortValue: (row) => statusLabel(row.sets[0]?.status ?? "").text,
            },
            {
              key: "repository",
              label: "저장소",
              cell: (row) => {
                const repositorySet = row.sets[0];
                const repository = primaryRepo(repositorySet);
                return <><span className="saas-cell-mono">{repositorySet?.name ?? "미연결"}</span><div className="saas-cell-sub">{repository?.sourceType ?? "—"}</div></>;
              },
              sortValue: (row) => row.sets[0]?.name ?? "",
            },
            {
              key: "location",
              label: "위치",
              cell: (row) => {
                const repository = primaryRepo(row.sets[0]);
                const location = repository?.url || repository?.path || "—";
                return <span className="saas-cell-muted saas-path" title={location}>{location}</span>;
              },
              sortValue: (row) => {
                const repository = primaryRepo(row.sets[0]);
                return repository?.url || repository?.path || "";
              },
            },
          ]}
          timestamps={{ createdAt: (row) => row.project.createdAt, updatedAt: (row) => row.project.updatedAt }}
          actions={(row) => (
            <>
              <Button variant="secondary" size="sm" busy={row.sets.some((item) => syncingSetIds.has(item.id))} disabled={row.sets.length === 0} onClick={() => void syncRepositorySets(row.sets.map((item) => item.id))} data-testid={`project-sync-${row.project.id}`}>동기화</Button>
              <Button variant="secondary" size="sm" onClick={() => openDetail(row.project.id)} data-testid={`project-detail-${row.project.id}`}>상세</Button>
              <Button variant="secondary" size="sm" onClick={() => openEdit(row.project.id)} data-testid={`project-edit-${row.project.id}`}>수정</Button>
              <Button variant="ghost" size="sm" className="is-danger-text" busy={busy && selectedProjectId === row.project.id} onClick={() => void deleteProject(row.project.id, row.project.name)} data-testid={`project-delete-${row.project.id}`}>삭제</Button>
            </>
          )}
          selection={{ selected: checkedIds, onChange: setCheckedIds, label: (row) => `${row.project.name} 선택` }}
          loading={listLoading}
          emptyText={query ? `검색어 「${query}」와 맞는 프로젝트가 없습니다.` : "등록된 프로젝트가 없습니다. 하단 「프로젝트 생성」으로 시작하세요."}
          loadingText="프로젝트 목록을 불러오는 중입니다"
          onRowClick={(row) => openDetail(row.project.id)}
          rowClassName={(row) => selectedProjectId === row.project.id ? "is-selected" : ""}
          testId="projects-data-table"
        />
        </div>

        <div className="page-shell-footer-slot">
          <PageStickyFooter
            testId="projects-list-footer"
            note="저장소 연결·동기화 시 코드 자동 분석이 함께 진행됩니다."
            actions={
              <Button variant="primary" size="md" onClick={openCreate} data-testid="project-create-open">
                프로젝트 생성
              </Button>
            }
          />
        </div>
      </div>
    </section>
  );
}

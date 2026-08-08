"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { lsGet, lsSet } from "../../lib/localStore";
import { flowStepLabel } from "../../lib/scenarioNarration";
import { PageShell, PageStickyFooter } from "../PageShell";
import { useRightPanel } from "../RightPanelContext";
import { Button } from "../ui";
import { Breadcrumbs } from "../Breadcrumbs";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";

/** Figma User Flow Kit D-008 */
const FIGMA = {
  fileKey: "qpZeClozlSVQd6j8Od8P9x",
  kitNodeId: "0:1",
  exampleNodeId: "1:319",
  accent: "#3300FF",
  arrow: "#1A1A1A",
  pillBg: "#EDEDEE",
};

type GraphNode = {
  id: string;
  type: string;
  name: string;
  attributes?: Record<string, unknown>;
  confidence?: number;
  verificationStatus?: string;
};

type GraphEdge = {
  id: string;
  from: string;
  to: string;
  type: string;
  condition?: string | null;
  confidence?: number;
  editedBy?: string | null;
};

type EdgeDraft = { to: string; type: string; condition: string };
type ConnectDraft = { from: string; to: string; type: string; condition: string };
type EdgeOptions = { types: string[]; conditionPresets: string[] };

type GraphSummary = {
  graphId: string;
  projectId?: string | null;
  nodeCount: number;
  edgeCount: number;
  primaryPath: string[];
  branches: Array<{ id: string; label: string; condition: string }>;
  unresolvedCount: number;
  result?: {
    nodes?: GraphNode[];
    edges?: GraphEdge[];
    unresolved?: Array<Record<string, unknown>>;
    figmaRef?: Record<string, string>;
  };
  /** 시나리오 단위 응답에만 있는 필드 */
  scopedScenarioId?: string;
  scopedScenarioName?: string;
  sourceGraphId?: string | null;
  seedNodeIds?: string[];
  missingData?: string[];
};

type NodeRuntime = {
  nodeId: string;
  graphId: string;
  method?: string | null;
  operation?: {
    kind?: string;
    stepId?: string | null;
    action?: string | null;
    method?: string | null;
    path?: string | null;
    target?: Record<string, unknown> | null;
  };
  status: "success" | "failure" | "warning" | "pending" | "unknown";
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  errorMessage?: string | null;
};

type LaidOut = {
  id: string;
  node: GraphNode;
  x: number;
  y: number;
  w: number;
  h: number;
  lane: number;
};

const NODE_W = 176;
const NODE_H_SCREEN = 136;
const NODE_H = 108;
const GAP_X = 64;
const ROW_H = NODE_H_SCREEN + 64;
const PAD = 24;
const MIN_COLS = 2;

type StepCache = {
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  savedAt: string;
};

type ReplayState = {
  runId: string;
  kickoffNodeId: string;
  currentStepId?: string | null;
  percent: number;
  status: string;
};

/** 같은 그룹의 시나리오 — 그래프 화면에서 시나리오명으로 고를 수 있게 한다 */
export type ScenarioChoice = { scenarioId: string; title: string; graphId?: string | null };

/** 부분 그래프를 만들 근거가 없을 때의 안내 — 추정으로 노드를 채우지 않는다 */
function scopeNote(missingData: string[]): string | null {
  if (missingData.includes("scenario_graph_refs")) {
    return "이 시나리오와 연결된 그래프 근거가 없습니다 (missing_data). 전체 그래프에서 확인하세요.";
  }
  if (missingData.includes("source_graph")) {
    return "이 시나리오가 참조하는 분석 그래프를 찾을 수 없습니다 (missing_data). 저장소를 다시 분석하면 그래프가 다시 생깁니다.";
  }
  if (missingData.includes("scenario_graph_link")) {
    return "이 시나리오에는 연결된 분석 그래프 정보가 없습니다 (missing_data).";
  }
  return null;
}

export function FlowCanvas({
  scenarioId,
  setScenarios,
  backHref,
}: {
  /** 지정하면 이 시나리오와 근거가 연결된 컴포넌트만 그린다 */
  scenarioId?: string;
  setScenarios?: ScenarioChoice[];
  backHref?: string;
} = {}) {
  const { setPanel } = useRightPanel();
  const router = useRouter();
  const searchParams = useSearchParams();
  const serviceIdParam = searchParams.get("serviceId");
  const projectIdParam = searchParams.get("projectId");
  const graphIdParam = searchParams.get("graphId");
  const scoped = Boolean(scenarioId);
  const [scopedNote, setScopedNote] = useState<string | null>(null);
  const [graphs, setGraphs] = useState<GraphSummary[]>([]);
  const [graphId, setGraphId] = useState("");
  const [graph, setGraph] = useState<GraphSummary | null>(null);
  const [branch, setBranch] = useState("happy_path");
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const [edgeDraft, setEdgeDraft] = useState<EdgeDraft>({ to: "", type: "", condition: "" });
  const [connectDraft, setConnectDraft] = useState<ConnectDraft>({
    from: "",
    to: "",
    type: "navigates_to",
    condition: "happy_path",
  });
  const [connectOpen, setConnectOpen] = useState(false);
  const [edgeOptions, setEdgeOptions] = useState<EdgeOptions>({
    types: ["navigates_to"],
    conditionPresets: ["happy_path"],
  });
  const [runtimeMap, setRuntimeMap] = useState<Record<string, NodeRuntime>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const bootRequestRef = useRef(0);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const inspectorRef = useRef<HTMLDivElement | null>(null);
  const [cols, setCols] = useState(4);
  const [zoom, setZoom] = useState(1);
  const [replay, setReplay] = useState<ReplayState | null>(null);
  const [workspaceTab, setWorkspaceTab] = useState<"graph" | "detail">("graph");
  const replaySourceRef = useRef<EventSource | null>(null);

  useEffect(() => () => replaySourceRef.current?.close(), []);

  useEffect(() => {
    if (workspaceTab !== "detail") return;
    const inspector = inspectorRef.current;
    if (!inspector) return;
    inspector.focus({ preventScroll: true });
  }, [workspaceTab, selected, selectedEdge, connectOpen]);

  useEffect(() => {
    const el = viewportRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const measure = () => {
      const usable = el.clientWidth - PAD * 2;
      setCols(Math.max(MIN_COLS, Math.floor((usable + GAP_X) / (NODE_W + GAP_X))));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [graph]);

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(`${API}/api/interaction-graphs/edge-options`);
        if (!res.ok) return;
        setEdgeOptions((await res.json()) as EdgeOptions);
      } catch {
        // presets are a convenience — free text entry still works
      }
    })();
  }, []);

  const nodes = useMemo(() => graph?.result?.nodes ?? [], [graph]);
  const edges = useMemo(() => graph?.result?.edges ?? [], [graph]);
  const nodeMap = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const nodeLabel = useCallback(
    (id: string) => {
      const node = nodeMap.get(id);
      if (!node) return id;
      return `${node.name}${node.type === "screen" ? " (화면)" : ""}`;
    },
    [nodeMap],
  );
  const branchOptions = useMemo(() => {
    const raw = graph?.branches?.length
      ? graph.branches
      : ([{ id: "happy_path", label: "정상 경로", condition: "happy_path" }] as Array<{
          id: string;
          label: string;
          condition: string;
        }>);
    const seen = new Set<string>();
    const out: Array<{ id: string; label: string; condition: string }> = [];
    for (const b of raw) {
      const key = `${b.id}::${b.condition}`;
      if (seen.has(key) || seen.has(b.id)) continue;
      seen.add(key);
      seen.add(b.id);
      out.push(b);
    }
    return out;
  }, [graph]);

  /** 시나리오 단위 화면 제목·셀렉트는 그래프 ID가 아니라 시나리오명으로 보여준다 */
  const scopedScenarioName =
    setScenarios?.find((s) => s.scenarioId === scenarioId)?.title ||
    graph?.scopedScenarioName ||
    "";
  const graphHeading = scoped
    ? `${scopedScenarioName || "선택한 시나리오"} 시나리오 의존관계 그래프`
    : "의존관계 그래프";
  const scenarioChoices = useMemo<ScenarioChoice[]>(() => {
    if (!scenarioId) return [];
    const list = setScenarios ? [...setScenarios] : [];
    if (!list.some((s) => s.scenarioId === scenarioId)) {
      list.unshift({ scenarioId, title: scopedScenarioName || scenarioId });
    }
    return list;
  }, [setScenarios, scenarioId, scopedScenarioName]);

  const layout = useMemo(() => {
    return layoutGraph(nodes, edges, graph?.primaryPath ?? [], branch, cols);
  }, [nodes, edges, graph?.primaryPath, branch, cols]);

  const layoutMap = useMemo(() => new Map(layout.map((l) => [l.id, l])), [layout]);

  const replayCursor = useMemo(() => {
    if (!replay) return null;
    const kickoffIndex = layout.findIndex((item) => item.id === replay.kickoffNodeId);
    const kickoffStepId = String(
      layout[kickoffIndex]?.node.attributes?.scenarioStepId || "",
    );
    const observedIndex = replay.currentStepId
      ? layout.findIndex(
          (item) => String(item.node.attributes?.scenarioStepId || "") === replay.currentStepId,
        )
      : -1;
    const restoringPrerequisites =
      kickoffIndex > -1 && observedIndex > -1 && observedIndex < kickoffIndex;
    return {
      kickoffIndex,
      activeIndex: restoringPrerequisites || observedIndex < 0 ? kickoffIndex : observedIndex,
      activeStepId:
        restoringPrerequisites || observedIndex < 0 ? kickoffStepId : String(replay.currentStepId || ""),
      restoringPrerequisites,
    };
  }, [layout, replay]);

  const visibleEdges = useMemo(() => {
    return edges.filter((e) => {
      if (!layoutMap.has(e.from) || !layoutMap.has(e.to)) return false;
      if (branch === "happy_path") {
        return !e.condition || e.condition === "happy_path" || e.type === "contains" || e.type === "triggers";
      }
      return e.condition === branch || !e.condition || e.type === "contains";
    });
  }, [edges, layoutMap, branch]);

  /**
   * Edge geometry is computed once so the line can render under the node cards
   * while its clickable condition pill renders above them.
   */
  const edgeGeoms = useMemo(() => {
    return visibleEdges.flatMap((edge) => {
      const from = layoutMap.get(edge.from);
      const to = layoutMap.get(edge.to);
      if (!from || !to) return [];
      const sameRow = from.lane === to.lane;
      const forward = to.x >= from.x;
      const x1 = sameRow ? (forward ? from.x + from.w : from.x) : from.x + from.w;
      const y1 = from.y + from.h / 2;
      const x2 = sameRow ? (forward ? to.x : to.x + to.w) : to.x;
      const y2 = to.y + to.h / 2;
      const midX = (x1 + x2) / 2;
      // Row changes travel through the empty gutter between the two rows.  The old
      // max(bottom)+26 route crossed the following row's cards and labels.
      const sourceBottom = from.y + from.h;
      const targetTop = to.y;
      const gutterY = sourceBottom < targetTop
        ? sourceBottom + (targetTop - sourceBottom) / 2
        : Math.max(sourceBottom, to.y + to.h) + 30;
      const rowChange = !sameRow;
      const d = rowChange
        ? `M ${x1} ${y1} L ${x1 + 20} ${y1} L ${x1 + 20} ${gutterY} L ${x2 - 20} ${gutterY} L ${x2 - 20} ${y2} L ${x2} ${y2}`
        : `M ${x1} ${y1} L ${x2} ${y2}`;
      return [
        {
          edge,
          d,
          labelX: rowChange ? (x1 + x2) / 2 : midX,
          labelY: rowChange ? gutterY : y1,
        },
      ];
    });
  }, [visibleEdges, layoutMap]);

  const selectEdge = useCallback((edge: GraphEdge) => {
    setSelectedEdge(edge);
    setEdgeDraft({ to: edge.to, type: edge.type, condition: edge.condition ?? "" });
    setConnectOpen(false);
    setSelected(null);
    setWorkspaceTab("detail");
  }, []);

  const emptyInputNote = (node: GraphNode) => {
    if (node.type === "screen") {
      return "이 화면에서 관측된 입력 컨트롤이 없습니다 (분석 결과 기준).";
    }
    return "정적 분석에서 요청 필드가 추출되지 않았습니다.";
  };

  const notice = useMemo(() => {
    if (!message) return { tone: "is-info", text: "" };
    const failed = /failed to fetch|networkerror|load failed/i.test(message);
    if (failed) {
      return {
        tone: "is-warn",
        text: "그래프 단계 상태를 불러오지 못했습니다. Control Plane 연결을 확인한 뒤 「상태 새로고침」을 눌러주세요.",
      };
    }
    const warn = /실패|없습니다|missing|오류/.test(message);
    return { tone: warn ? "is-warn" : "is-info", text: message };
  }, [message]);

  const runtimeAttention = useMemo(() => {
    const rows = Object.values(runtimeMap);
    const failed = rows.find((item) => item.status === "failure");
    const warning = rows.find((item) => item.status === "warning");
    const selected = failed || warning;
    if (!selected) return null;
    return {
      tone: failed ? "is-error" : "is-warn",
      label: failed ? "기대 결과 불일치" : "담당자 확인 필요",
      detail: selected.errorMessage || "최근 실행의 판정 근거를 이 단계에서 확인해야 합니다.",
      nodeId: selected.nodeId,
    };
  }, [runtimeMap]);

  const canvasSize = useMemo(() => {
    if (layout.length === 0) return { w: 800, h: 320 };
    const maxX = Math.max(...layout.map((l) => l.x + l.w));
    const maxY = Math.max(...layout.map((l) => l.y + l.h));
    return { w: maxX + PAD, h: Math.max(320, maxY + PAD) };
  }, [layout]);

  function stepCacheKey(gid: string, nodeId: string) {
    return `flow.step.${gid}.${nodeId}`;
  }

  function persistStepLocal(gid: string, nodeId: string, input: Record<string, unknown>, output: Record<string, unknown>) {
    lsSet(stepCacheKey(gid, nodeId), {
      input,
      output,
      savedAt: new Date().toISOString(),
    } satisfies StepCache);
    lsSet("flow.lastGraphId", gid);
    lsSet("flow.lastNodeId", nodeId);
  }

  function loadStepLocal(gid: string, nodeId: string): StepCache | null {
    return lsGet<StepCache | null>(stepCacheKey(gid, nodeId), null);
  }

  function selectNode(node: GraphNode, nodeId: string) {
    setSelected(node);
    setSelectedEdge(null);
    setConnectOpen(false);
    setWorkspaceTab("detail");
    if (graphId) lsSet("flow.lastNodeId", nodeId);
  }

  async function loadRuntime(id: string, bootRequestId?: number) {
    let res: Response;
    try {
      res = await fetch(`${API}/api/console/flows/${id}/nodes`, { cache: "no-store" });
    } catch {
      // 개발 서버 HMR·백엔드 재기동 경계에서 첫 연결만 끊길 수 있다. 임의 대기 없이 한 번 재시도한다.
      res = await fetch(`${API}/api/console/flows/${id}/nodes`, { cache: "no-store" });
    }
    if (!res.ok) return;
    const list = (await res.json()) as NodeRuntime[];
    if (bootRequestId !== undefined && bootRequestRef.current !== bootRequestId) return;
    const map: Record<string, NodeRuntime> = {};
    for (const item of list) {
      const cached = loadStepLocal(id, item.nodeId);
      map[item.nodeId] = cached
        ? { ...item, input: cached.input ?? item.input, output: cached.output ?? item.output }
        : item;
    }
    setRuntimeMap(map);
    const lastNode = lsGet<string | null>("flow.lastNodeId", null);
    if (lastNode && !selected) {
      const node = (graph?.result?.nodes ?? nodes).find((n) => n.id === lastNode);
      if (node) setSelected(node);
    }
  }

  async function reprocessNode(nodeId: string, useLocal = true) {
    if (!graphId) return;
    setBusy(true);
    try {
      const cached = useLocal ? loadStepLocal(graphId, nodeId) : null;
      const input = cached?.input ?? runtimeMap[nodeId]?.input ?? {};
      const res = await fetch(`${API}/api/console/flows/${graphId}/nodes/${nodeId}/retry`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input, note: useLocal ? "localStorage reprocess" : "console retry" }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "재처리 실패");
      setRuntimeMap((prev) => ({ ...prev, [nodeId]: body }));
      persistStepLocal(graphId, nodeId, body.input || input, body.output || {});
      const runId = String(body.output?.runId || "");
      if (runId) {
        watchReprocess(runId, nodeId);
        setMessage("저장된 Input으로 재처리를 시작했습니다. 실제 실행 단계에 맞춰 초록 테두리가 이동합니다.");
      } else {
        setMessage("단계 재처리를 등록했습니다. 실행 이력에서 상태를 확인하세요.");
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "재처리 실패");
    } finally {
      setBusy(false);
    }
  }

  function watchReprocess(runId: string, kickoffNodeId: string) {
    replaySourceRef.current?.close();
    setReplay({ runId, kickoffNodeId, currentStepId: null, percent: 0, status: "RUNNING" });
    const source = new EventSource(
      `${API}/api/console/bulk-runs/events?runIds=${encodeURIComponent(runId)}`,
    );
    replaySourceRef.current = source;
    const update = (event: MessageEvent) => {
      const payload = JSON.parse(event.data) as {
        percent?: number;
        runs?: Array<{ status?: string; currentStepId?: string | null; progressPercent?: number }>;
      };
      const run = payload.runs?.[0] || {};
      setReplay((current) => ({
        runId,
        kickoffNodeId: current?.kickoffNodeId || kickoffNodeId,
        currentStepId: run.currentStepId ?? current?.currentStepId ?? null,
        percent: Number(run.progressPercent ?? payload.percent ?? current?.percent ?? 0),
        status: String(run.status || current?.status || "RUNNING"),
      }));
    };
    source.addEventListener("progress", update as EventListener);
    source.addEventListener("complete", ((event: MessageEvent) => {
      update(event);
      source.close();
      replaySourceRef.current = null;
      setMessage("재처리 실행이 완료됐습니다. 각 단계의 새 관측값을 불러왔습니다. 최종 판정은 HITL입니다.");
      if (graphId) void loadRuntime(graphId);
    }) as EventListener);
    source.onerror = () => {
      source.close();
      replaySourceRef.current = null;
      setMessage("재처리 Progress 연결이 종료됐습니다. 실행 이력에서 최신 상태를 확인하세요.");
    };
  }

  async function saveNodeRuntime(
    nodeId: string,
    input: Record<string, unknown>,
    output: Record<string, unknown>,
  ) {
    if (!graphId) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/console/flows/${graphId}/nodes/${nodeId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ input, output }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "저장 실패");
      setRuntimeMap((prev) => ({ ...prev, [nodeId]: body }));
      persistStepLocal(graphId, nodeId, body.input || input, body.output || output);
      setMessage("이 단계의 실제 입·출력값을 서버와 브라우저에 저장했습니다.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "저장 실패");
    } finally {
      setBusy(false);
    }
  }

  function restoreNodeRuntime(nodeId: string) {
    if (!graphId) return;
    const cached = loadStepLocal(graphId, nodeId);
    if (!cached) {
      setMessage("이 단계에 저장된 브라우저 값이 없습니다.");
      return;
    }
    setRuntimeMap((prev) => ({
      ...prev,
      [nodeId]: {
        ...(prev[nodeId] || {
          nodeId,
          graphId,
          status: "unknown",
          input: {},
          output: {},
        }),
        input: cached.input,
        output: cached.output,
      },
    }));
    setMessage(`저장값을 복원했습니다 (${new Date(cached.savedAt).toLocaleString("ko-KR")}).`);
  }

  useEffect(() => {
    const bootRequestId = ++bootRequestRef.current;
    async function boot() {
      try {
        if (scenarioId) {
          // 시나리오 단위 — 서버가 evidenceRefs·evidenceIndex 근거로 만든 부분집합만 그린다
          const res = await fetch(`${API}/api/scenarios/${scenarioId}/interaction-graph`, {
            cache: "no-store",
          });
          const body = (await res.json()) as GraphSummary & {
            detail?: string;
            sourceGraphId?: string | null;
            scopedScenarioName?: string;
            missingData?: string[];
          };
          if (!res.ok) throw new Error(body.detail || "시나리오 의존관계 그래프를 불러오지 못했습니다");
          const runtimeGraphId = body.graphId;
          if (bootRequestRef.current !== bootRequestId) return;
          setGraph(body);
          setGraphId(runtimeGraphId);
          setScopedNote(scopeNote(body.missingData || []));
          await loadRuntime(runtimeGraphId, bootRequestId);
          if (bootRequestRef.current === bootRequestId) setMessage(null);
          return;
        }
        if (serviceIdParam) {
          const qs = new URLSearchParams();
          if (projectIdParam) qs.set("projectId", projectIdParam);
          const res = await fetch(
            `${API}/api/flows/by-service/${encodeURIComponent(serviceIdParam)}?${qs}`,
            { cache: "no-store" },
          );
          if (res.ok) {
            const body = (await res.json()) as { graph?: GraphSummary; graphId?: string };
            if (body.graph) {
              const gid = body.graphId || body.graph.graphId;
              setGraph(body.graph);
              setGraphId(gid);
              await loadRuntime(gid, bootRequestId);
              if (bootRequestRef.current === bootRequestId) {
                setMessage(`서비스 ID ${serviceIdParam} 의존관계 그래프 · Figma Kit ${FIGMA.exampleNodeId}`);
              }
            }
          }
        }
        const listed = (await fetch(`${API}/api/interaction-graphs`, {
          cache: "no-store",
        }).then((r) => r.json())) as GraphSummary[];
        setGraphs(listed);
        const prefer =
          (graphIdParam && listed.find((g) => g.graphId === graphIdParam)) ||
          (!serviceIdParam ? listed[0] : null);
        if (prefer) {
          setGraphId(prefer.graphId);
          setGraph(prefer);
          await loadRuntime(prefer.graphId, bootRequestId);
          if (bootRequestRef.current === bootRequestId) setMessage(null);
        }
      } catch (err) {
        if (bootRequestRef.current === bootRequestId) {
          setMessage(err instanceof Error ? err.message : "로드 실패");
        }
      }
    }
    void boot();
  }, [serviceIdParam, projectIdParam, graphIdParam, scenarioId]);

  /** Single write path for every edge edit — apply, disconnect, connect. */
  async function mutateEdges(
    path: string,
    init: RequestInit,
    successNote: string,
    onDone?: () => void,
  ) {
    if (!graphId) return;
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/interaction-graphs/${graphId}${path}`, {
        headers: { "Content-Type": "application/json" },
        ...init,
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "엣지 편집 실패");
      setGraph(body);
      setGraphs((prev) => prev.map((g) => (g.graphId === body.graphId ? body : g)));
      setMessage(successNote);
      onDone?.();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "엣지 편집 실패");
    } finally {
      setBusy(false);
    }
  }

  async function applyEdgeEdit() {
    if (!selectedEdge) return;
    const nextTo = edgeDraft.to || selectedEdge.to;
    const conditionChanged = edgeDraft.condition !== (selectedEdge.condition ?? "");
    const payload: Record<string, unknown> = {};
    if (nextTo !== selectedEdge.to) payload.to = nextTo;
    if (edgeDraft.type !== selectedEdge.type) payload.type = edgeDraft.type;
    if (conditionChanged) {
      if (edgeDraft.condition.trim() === "") payload.clearCondition = true;
      else payload.condition = edgeDraft.condition.trim();
    }
    if (Object.keys(payload).length === 0) {
      setMessage("변경된 내용이 없습니다.");
      return;
    }
    const parts = [
      payload.to ? `대상 ${nodeLabel(selectedEdge.to)} → ${nodeLabel(nextTo)}` : null,
      payload.type ? `종류 ${edgeDraft.type}` : null,
      conditionChanged
        ? `조건 ${edgeDraft.condition.trim() || "없음"}`
        : null,
    ].filter(Boolean);
    await mutateEdges(
      `/edges/${encodeURIComponent(selectedEdge.id)}`,
      { method: "PATCH", body: JSON.stringify(payload) },
      `${parts.join(" · ")} 변경 · 「재처리」로 관측을 다시 수행하세요.`,
      () => setSelectedEdge(null),
    );
  }

  async function disconnectEdge() {
    if (!selectedEdge) return;
    await mutateEdges(
      `/edges/${encodeURIComponent(selectedEdge.id)}`,
      { method: "DELETE" },
      `연결 끊김: ${nodeLabel(selectedEdge.from)} → ${nodeLabel(selectedEdge.to)} · 노드는 유지됩니다.`,
      () => setSelectedEdge(null),
    );
  }

  async function connectNodes() {
    if (!connectDraft.from || !connectDraft.to) return;
    await mutateEdges(
      "/edges",
      {
        method: "POST",
        body: JSON.stringify({
          from: connectDraft.from,
          to: connectDraft.to,
          type: connectDraft.type,
          condition: connectDraft.condition.trim() || null,
        }),
      },
      `새 연결: ${nodeLabel(connectDraft.from)} → ${nodeLabel(connectDraft.to)} · 사람 편집(신뢰도 0.5)으로 표시됩니다.`,
      () => setConnectDraft((d) => ({ ...d, to: "", condition: "" })),
    );
  }

  useEffect(() => {
    setPanel(
      <FlowNodePanel
        graph={graph}
        selected={selected}
        runtime={selected ? runtimeMap[selected.id] : undefined}
        busy={busy}
        onSave={saveNodeRuntime}
        onRetry={async (nodeId, input) => {
          if (!graphId) return;
          setBusy(true);
          try {
            const cached = loadStepLocal(graphId, nodeId);
            const payloadInput = Object.keys(input || {}).length ? input : cached?.input || {};
            const res = await fetch(`${API}/api/console/flows/${graphId}/nodes/${nodeId}/retry`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ input: payloadInput, note: "console retry" }),
            });
            const body = await res.json();
            if (!res.ok) throw new Error(body.detail || "재시도 실패");
            setRuntimeMap((prev) => ({ ...prev, [nodeId]: body }));
            persistStepLocal(graphId, nodeId, body.input || payloadInput, body.output || {});
            setMessage("컴포넌트 재처리를 등록했습니다.");
          } catch (err) {
            setMessage(err instanceof Error ? err.message : "재시도 실패");
          } finally {
            setBusy(false);
          }
        }}
      />,
    );
    return () => setPanel(null);
  }, [selected, runtimeMap, graph, graphId, busy, setPanel]);

  async function loadGraph(id: string) {
    setBusy(true);
    try {
      const res = await fetch(`${API}/api/interaction-graphs/${id}`, { cache: "no-store" });
      const body = (await res.json()) as GraphSummary & { detail?: string };
      if (!res.ok) throw new Error(body.detail || "로드 실패");
      setGraph(body);
      setGraphId(id);
      await loadRuntime(id);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "로드 실패");
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell
      className="flow-page"
      header={
        <div className="content-header">
          <div>
            <Breadcrumbs
              trail={[
                { label: "콘솔", href: "/" },
                { label: "테스트 시나리오", href: backHref ?? "/scenarios" },
                { label: "의존관계 그래프" },
              ]}
            />
            <h2 data-testid="flow-graph-title">{graphHeading}</h2>
            <p className="muted" style={{ marginTop: 6 }}>
              {scoped
                ? "이 시나리오와 근거가 연결된 화면·API 컴포넌트만 좌→우로 표시합니다. 노드를 선택하면 단계 상세 탭이 열립니다."
                : "A→API→B 단계를 좌→우로 확인합니다. 노드를 선택하면 단계 상세 탭에서 Query · Variables · Response를 봅니다."}
            </p>
          </div>
        </div>
      }
      footer={
        <PageStickyFooter
          testId="flow-footer"
          note={
            scoped
              ? "이 시나리오 범위의 부분 그래프입니다. 연결 편집은 전체 그래프 화면에서 합니다. Complete ≠ HITL Pass."
              : "선을 클릭하면 조건·대상을 편집하거나 연결을 끊습니다. Complete ≠ HITL Pass."
          }
          actions={
            <>
              <Button
                variant="secondary"
                size="md"
                disabled={!graphId || scoped}
                title={scoped ? "부분 그래프에서는 새 연결을 추가하지 않습니다" : undefined}
                onClick={() => {
                  setSelectedEdge(null);
                  setConnectOpen(true);
                  setWorkspaceTab("detail");
                }}
                data-testid="flow-open-connect"
              >
                새 연결 추가
              </Button>
              <Button
                variant="primary"
                size="md"
                busy={busy}
                disabled={!graphId}
                onClick={() => {
                  if (!graphId) return;
                  void loadRuntime(graphId)
                    .then(() => setMessage(null))
                    .catch(() =>
                      setMessage(
                        "그래프 단계 상태를 불러오지 못했습니다. Control Plane 연결을 확인한 뒤 다시 시도해 주세요.",
                      ),
                    );
                }}
              >
                {busy ? "상태 확인 중…" : "상태 새로고침"}
              </Button>
            </>
          }
        />
      }
    >
        <div className="form-grid" style={{ marginBottom: 12 }}>
          {scoped ? (
            <label>
              테스트 시나리오
              <select
                value={scenarioId}
                onChange={(e) => {
                  if (!e.target.value) return;
                  const qs = new URLSearchParams(Array.from(searchParams.entries()));
                  qs.set("scenarioId", e.target.value);
                  qs.set("view", "graph");
                  router.push(`/scenarios?${qs.toString()}`);
                }}
                data-testid="flow-scenario-select"
              >
                {scenarioChoices.map((choice) => (
                  <option key={choice.scenarioId} value={choice.scenarioId}>
                    {choice.title}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <label>
              그래프 ID
              <select
                value={graphId}
                onChange={(e) => {
                  setGraphId(e.target.value);
                  if (e.target.value) void loadGraph(e.target.value);
                }}
              >
                <option value="">(없음)</option>
                {graphs.map((g) => (
                  <option key={g.graphId} value={g.graphId}>
                    {g.graphId} · 노드 {g.nodeCount}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            분기 (Condition)
            <select value={branch} onChange={(e) => setBranch(e.target.value)}>
              {branchOptions.map((b, index) => (
                <option key={`${b.id}-${b.condition}-${index}`} value={b.condition}>
                  {b.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <datalist id="flow-condition-presets">
          {edgeOptions.conditionPresets.map((c) => (
            <option key={c} value={c} />
          ))}
        </datalist>

        <div className="flow-workspace-tabs" role="tablist" aria-label="의존관계 그래프 보기 방식">
          <button
            type="button"
            role="tab"
            aria-selected={workspaceTab === "graph"}
            className={workspaceTab === "graph" ? "is-active" : ""}
            onClick={() => setWorkspaceTab("graph")}
            data-testid="flow-tab-graph"
          >
            의존관계 흐름도
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={workspaceTab === "detail"}
            className={workspaceTab === "detail" ? "is-active" : ""}
            onClick={() => setWorkspaceTab("detail")}
            data-testid="flow-tab-detail"
          >
            선택 단계 상세
            {selected || selectedEdge || connectOpen ? <span>1</span> : null}
          </button>
        </div>

        <div className="flow-workspace-panel is-graph" hidden={workspaceTab !== "graph"}>

        <div className="flow-legend" role="list" aria-label="노드 상태 범례">
          <span className="flow-legend-item is-success" role="listitem">성공 관측</span>
          <span className="flow-legend-item is-failure" role="listitem">실패 관측</span>
          <span className="flow-legend-item is-warning" role="listitem">확인 필요</span>
          <span className="flow-legend-item is-pending" role="listitem">대기/미확인</span>
          <span className="flow-figma-ref">
            Kit {FIGMA.kitNodeId} · Example {FIGMA.exampleNodeId}
          </span>
        </div>

        {message && (
          <div
            className={`connect-banner ${notice.tone}`}
            style={{ margin: "0 12px 12px" }}
            data-testid="flow-message"
            role={notice.tone === "is-warn" ? "alert" : "status"}
          >
            {notice.text}
          </div>
        )}

        {runtimeAttention && (
          <div
            className={`flow-runtime-attention ${runtimeAttention.tone}`}
            data-testid="flow-runtime-attention"
            role="alert"
          >
            <strong>{runtimeAttention.label}</strong>
            <span>{runtimeAttention.detail}</span>
            <button
              type="button"
              onClick={() => {
                const node = nodes.find((item) => item.id === runtimeAttention.nodeId);
                if (node) selectNode(node, node.id);
              }}
            >
              표시된 단계 확인
            </button>
          </div>
        )}

        {scopedNote && (
          <div
            className="connect-banner is-warn"
            style={{ margin: "0 12px 12px" }}
            role="status"
            data-testid="flow-scope-missing"
          >
            {scopedNote}
            {graph?.sourceGraphId && (
              <a
                className="ghost-btn"
                style={{ marginLeft: 10 }}
                href={`/scenarios?view=graph&graphId=${encodeURIComponent(graph.sourceGraphId)}`}
              >
                전체 그래프 보기
              </a>
            )}
          </div>
        )}

        {!graph ? (
          <p className="muted" style={{ padding: 16 }}>
            {scoped
              ? "이 시나리오의 의존관계 그래프를 불러오는 중입니다."
              : "분석 후 생성된 의존관계 그래프가 여기에 표시됩니다."}
          </p>
        ) : nodes.length === 0 ? (
          <p className="muted" style={{ padding: 16 }} data-testid="flow-graph-empty">
            표시할 컴포넌트가 없습니다. 근거가 있는 노드만 그리므로 추정으로 채우지 않습니다
            (missing_data).
          </p>
        ) : (
          <div
            className="flow-graph-viewport"
            ref={viewportRef}
            tabIndex={0}
            aria-label="FLOW 그래프. 상하좌우 방향키와 Page Up, Page Down으로 이동할 수 있습니다."
            onPointerDown={(event) => event.currentTarget.focus({ preventScroll: true })}
            onKeyDown={(event) => {
              if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End"].includes(event.key)) return;
              event.preventDefault();
              const viewport = event.currentTarget;
              if (event.key === "Home") viewport.scrollTo({ left: 0, top: 0, behavior: "smooth" });
              else if (event.key === "End") viewport.scrollTo({ left: viewport.scrollWidth, top: viewport.scrollHeight, behavior: "smooth" });
              else if (event.key === "PageUp") viewport.scrollBy({ top: -Math.max(240, viewport.clientHeight * 0.8), behavior: "smooth" });
              else if (event.key === "PageDown") viewport.scrollBy({ top: Math.max(240, viewport.clientHeight * 0.8), behavior: "smooth" });
              else if (event.key === "ArrowUp" || event.key === "ArrowDown") viewport.scrollBy({ top: event.key === "ArrowUp" ? -180 : 180, behavior: "smooth" });
              else viewport.scrollBy({ left: event.key === "ArrowLeft" ? -240 : 240, behavior: "smooth" });
            }}
            data-testid="flow-canvas"
            data-figma-kit={FIGMA.fileKey}
            data-figma-example={FIGMA.exampleNodeId}
          >
            {replay && (
              <div className="flow-replay-progress" data-testid="flow-replay-progress" role="status">
                <div>
                  <strong>저장값 재처리</strong>
                  <span>
                    {replayCursor?.activeStepId || "실행 준비"}
                    {replayCursor?.restoringPrerequisites ? " · 실행환경 복원" : ""}
                    {` · ${replay.percent}%`}
                  </span>
                </div>
                <div className="flow-replay-track" aria-hidden>
                  <span style={{ width: `${Math.max(3, replay.percent)}%` }} />
                </div>
              </div>
            )}
            <div className="flow-axis">
              <span>시작</span>
              <span className="flow-axis-line" />
              <span className="flow-condition-active" title={branch}>
                조건 · {labelKo(branch)}
              </span>
              <span className="flow-axis-line" />
              <span>종료</span>
            </div>
            <div className="flow-zoom-toolbar" role="group" aria-label="그래프 확대 축소">
              <button
                type="button"
                onClick={() => setZoom((value) => Math.max(0.6, Number((value - 0.1).toFixed(1))))}
                disabled={zoom <= 0.6}
                aria-label="그래프 축소"
                data-testid="flow-zoom-out"
              >−</button>
              <span aria-live="polite">{Math.round(zoom * 100)}%</span>
              <button
                type="button"
                onClick={() => setZoom((value) => Math.min(1.6, Number((value + 0.1).toFixed(1))))}
                disabled={zoom >= 1.6}
                aria-label="그래프 확대"
                data-testid="flow-zoom-in"
              >+</button>
              <button
                type="button"
                onClick={() => setZoom(1)}
                disabled={zoom === 1}
                aria-label="그래프 배율 초기화"
                data-testid="flow-zoom-reset"
              >맞춤</button>
            </div>
            <div
              className="flow-graph-stage"
              style={{
                width: Math.max(canvasSize.w * zoom, 760),
                height: canvasSize.h * zoom,
              }}
            >
              <svg
                className="flow-graph-svg"
                width={canvasSize.w}
                height={canvasSize.h}
                viewBox={`0 0 ${canvasSize.w} ${canvasSize.h}`}
                style={{ transform: `scale(${zoom})` }}
              >
              <defs>
                <marker
                  id="flow-arrowhead"
                  markerWidth="8"
                  markerHeight="8"
                  refX="7"
                  refY="4"
                  orient="auto"
                >
                  <path d="M0,0 L8,4 L0,8 Z" fill={FIGMA.arrow} />
                </marker>
              </defs>

              {edgeGeoms.map(({ edge, d }) => {
                const active = selectedEdge?.id === edge.id;
                return (
                  <g
                    key={edge.id}
                    className={`flow-edge-g${active ? " is-active" : ""}`}
                    style={{ cursor: "pointer" }}
                    onClick={() => selectEdge(edge)}
                    data-testid={`flow-edge-${edge.id}`}
                  >
                    {/* A 1.5px line is a near-impossible click target */}
                    <path d={d} fill="none" stroke="transparent" strokeWidth={14} />
                    <path
                      d={d}
                      fill="none"
                      pointerEvents="none"
                      stroke={active ? FIGMA.accent : FIGMA.arrow}
                      strokeWidth={active ? 2.5 : 1.5}
                      // Hand-made connections read as provisional until observed
                      strokeDasharray={edge.editedBy === "human" ? "6 4" : undefined}
                      markerEnd="url(#flow-arrowhead)"
                    />
                  </g>
                );
              })}

              {layout.map((item) => {
                const rt = runtimeMap[item.id];
                const status = rt?.status || inferStatus(item.node);
                const isScreen = item.node.type === "screen";
                const hasLocal = Boolean(graphId && loadStepLocal(graphId, item.id));
                const itemIndex = layout.findIndex((candidate) => candidate.id === item.id);
                const replayActive = Boolean(
                  replay && replayCursor && itemIndex === replayCursor.activeIndex,
                );
                const replayComplete = Boolean(
                  replay &&
                    replayCursor &&
                    replayCursor.kickoffIndex > -1 &&
                    itemIndex >= replayCursor.kickoffIndex &&
                    itemIndex < replayCursor.activeIndex,
                );
                const stepLabel = flowStepLabel(
                  item.node.type,
                  item.node.name,
                  String(item.node.attributes?.role ?? ""),
                );
                return (
                  <foreignObject
                    key={item.id}
                    x={item.x}
                    y={item.y}
                    width={item.w}
                    height={item.h}
                  >
                    <div
                      className={`flow-card flow-status-${status} ${isScreen ? "is-screen" : "is-node"}${
                        selected?.id === item.id ? " is-selected" : ""
                      }${replayActive ? " is-replay-active" : ""}${replayComplete ? " is-replay-complete" : ""}`}
                      data-replay-state={replayActive ? "active" : replayComplete ? "complete" : undefined}
                    >
                      {isScreen && (
                        <div className="flow-card-chrome">
                          <span /><span /><span />
                        </div>
                      )}
                      <button
                        type="button"
                        className="flow-card-select"
                        aria-pressed={selected?.id === item.id}
                        onClick={() => selectNode(item.node, item.id)}
                        data-testid={`flow-node-${item.id}`}
                      >
                        <span className="flow-card-badge">{typeKo(item.node.type)}</span>
                        <strong className="flow-card-title">{stepLabel}</strong>
                        <span className="flow-card-meta">{item.node.name}</span>
                      </button>
                      {rt?.errorMessage && (
                        <span className="flow-card-error">{rt.errorMessage}</span>
                      )}
                      {/* 재처리 = 컴포넌트 1시 방향 리프레시 아이콘 */}
                      <button
                        type="button"
                        className="flow-card-refresh"
                        disabled={busy}
                        onClick={() => void reprocessNode(item.id, true)}
                        title={hasLocal ? "localStorage 저장값으로 재처리" : "현재 Input으로 재처리"}
                        aria-label={`${stepLabel} 단계 재처리`}
                        data-testid={`flow-reprocess-${item.id}`}
                      >
                        <svg
                          width="12"
                          height="12"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2.4"
                          strokeLinecap="round"
                          aria-hidden
                        >
                          <path d="M21 12a9 9 0 1 1-3.2-6.9" />
                          <path d="M21 3v6h-6" />
                        </svg>
                      </button>
                    </div>
                  </foreignObject>
                );
              })}

              {/* Condition pills sit above the cards so a line is always reachable */}
              {edgeGeoms.map(({ edge, labelX, labelY }) => {
                const label = edge.condition || edge.type;
                const active = selectedEdge?.id === edge.id;
                return (
                  <foreignObject
                    key={`pill-${edge.id}`}
                    x={labelX - 38}
                    y={Math.max(0, labelY - 34)}
                    width={76}
                    height={26}
                  >
                    <button
                      type="button"
                      className={`flow-condition-pill${active ? " is-active" : ""}`}
                      title={`${nodeLabel(edge.from)} → ${nodeLabel(edge.to)} · ${label}`}
                      aria-label={`연결 편집: ${nodeLabel(edge.from)} → ${nodeLabel(edge.to)}, 조건 ${label}`}
                      onClick={() => selectEdge(edge)}
                      data-testid={`flow-edge-pill-${edge.id}`}
                    >
                      {labelKo(label)}
                    </button>
                  </foreignObject>
                );
              })}
              </svg>
            </div>
          </div>
        )}

        {graph && (graph.result?.unresolved?.length ?? 0) > 0 && (
          <div className="flow-comment flow-comment-warn" data-testid="flow-unresolved">
            <strong>미해결 {graph.result?.unresolved?.length ?? 0}건 · 확인 필요</strong>
            <ul>
              {(graph.result?.unresolved ?? []).slice(0, 5).map((u, i) => (
                <li key={i}>
                  {String(u.kind ?? "미해결")}:{" "}
                  {shortenRef(String(u.symbol ?? u.reason ?? "missing_data"))}
                </li>
              ))}
            </ul>
          </div>
        )}

        </div>

        <div
          ref={inspectorRef}
          tabIndex={-1}
          className="flow-workspace-panel is-detail flow-inspector-anchor"
          hidden={workspaceTab !== "detail"}
          data-testid="flow-detail-panel"
        >
        {!selected && !selectedEdge && !connectOpen && (
          <div className="flow-detail-empty">
            <strong>흐름도에서 확인할 단계를 선택하세요</strong>
            <p>노드 또는 연결선을 선택하면 실행 입력·관측 결과·연결 편집 기능이 이 탭에 열립니다.</p>
            <Button variant="primary" size="sm" onClick={() => setWorkspaceTab("graph")}>
              흐름도로 이동
            </Button>
          </div>
        )}

        {selectedEdge && (
          <div className="gql-inspector anim-slide-up" data-testid="flow-edge-editor">
            <header className="gql-inspector-head">
              <div>
                <p className="gql-kicker">
                  연결 편집{selectedEdge.editedBy === "human" ? " · 사람 편집됨" : ""}
                </p>
                <h3>
                  {nodeLabel(selectedEdge.from)} → {nodeLabel(selectedEdge.to)}
                </h3>
              </div>
              <button type="button" className="ghost-btn" onClick={() => setSelectedEdge(null)}>
                닫기
              </button>
            </header>
            <div className="gql-inspector-body edge-editor-body">
              <div className="edge-editor-grid">
                <label className="muted">
                  대상 노드
                  <select
                    value={edgeDraft.to}
                    onChange={(e) => setEdgeDraft((d) => ({ ...d, to: e.target.value }))}
                    data-testid="flow-edge-to"
                  >
                    {nodes.map((n) => (
                      <option key={n.id} value={n.id}>
                        {n.name} · {n.type}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="muted">
                  연결 종류
                  <select
                    value={edgeDraft.type}
                    onChange={(e) => setEdgeDraft((d) => ({ ...d, type: e.target.value }))}
                    data-testid="flow-edge-type"
                  >
                    {edgeOptions.types.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="muted">
                  조건 (condition)
                  <input
                    list="flow-condition-presets"
                    value={edgeDraft.condition}
                    placeholder="비우면 조건 없음"
                    onChange={(e) => setEdgeDraft((d) => ({ ...d, condition: e.target.value }))}
                    data-testid="flow-edge-condition"
                  />
                </label>
              </div>
              <p className="muted edge-editor-note">
                조건을 비우면 무조건 연결이 됩니다. 편집한 연결은 사람 편집으로 표시되고, 노드
                「재처리」로 관측을 다시 수행해야 합니다. Pass/Fail은 HITL입니다.
              </p>
              <div className="edge-editor-actions">
                <Button
                  variant="primary"
                  size="sm"
                  busy={busy}
                  onClick={() => void applyEdgeEdit()}
                  data-testid="flow-edge-apply"
                >
                  변경 적용
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  busy={busy}
                  onClick={() => void disconnectEdge()}
                  data-testid="flow-edge-disconnect"
                >
                  연결 끊기
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setConnectDraft((d) => ({ ...d, from: selectedEdge.from }));
                    setConnectOpen(true);
                    setSelectedEdge(null);
                    setWorkspaceTab("detail");
                  }}
                  data-testid="flow-edge-open-connect"
                >
                  이 노드에서 새 연결
                </Button>
              </div>
            </div>
          </div>
        )}

        {connectOpen && (
          <div className="gql-inspector anim-slide-up" data-testid="flow-edge-connect">
            <header className="gql-inspector-head">
              <div>
                <p className="gql-kicker">새 연결 추가</p>
                <h3>두 노드를 직접 연결</h3>
              </div>
              <button type="button" className="ghost-btn" onClick={() => setConnectOpen(false)}>
                닫기
              </button>
            </header>
            <div className="gql-inspector-body edge-editor-body">
              <div className="edge-editor-grid">
                <label className="muted">
                  시작 노드 (A)
                  <select
                    value={connectDraft.from}
                    onChange={(e) => setConnectDraft((d) => ({ ...d, from: e.target.value }))}
                    data-testid="flow-connect-from"
                  >
                    <option value="">선택하세요</option>
                    {nodes.map((n) => (
                      <option key={n.id} value={n.id}>
                        {n.name} · {n.type}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="muted">
                  도착 노드 (C)
                  <select
                    value={connectDraft.to}
                    onChange={(e) => setConnectDraft((d) => ({ ...d, to: e.target.value }))}
                    data-testid="flow-connect-to"
                  >
                    <option value="">선택하세요</option>
                    {nodes
                      .filter((n) => n.id !== connectDraft.from)
                      .map((n) => (
                        <option key={n.id} value={n.id}>
                          {n.name} · {n.type}
                        </option>
                      ))}
                  </select>
                </label>
                <label className="muted">
                  연결 종류
                  <select
                    value={connectDraft.type}
                    onChange={(e) => setConnectDraft((d) => ({ ...d, type: e.target.value }))}
                    data-testid="flow-connect-type"
                  >
                    {edgeOptions.types.map((t) => (
                      <option key={t} value={t}>
                        {t}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="muted">
                  조건 (condition)
                  <input
                    list="flow-condition-presets"
                    value={connectDraft.condition}
                    placeholder="비우면 조건 없음"
                    onChange={(e) =>
                      setConnectDraft((d) => ({ ...d, condition: e.target.value }))
                    }
                    data-testid="flow-connect-condition"
                  />
                </label>
              </div>
              <p className="muted edge-editor-note">
                사람이 추가한 연결은 코드 근거가 없어 신뢰도 0.5(unresolved 등급)로 저장됩니다.
                실행 관측 후에 승격 여부를 사람이 판단합니다.
              </p>
              <div className="edge-editor-actions">
                <Button
                  variant="primary"
                  size="sm"
                  busy={busy}
                  disabled={!connectDraft.from || !connectDraft.to}
                  onClick={() => void connectNodes()}
                  data-testid="flow-connect-apply"
                >
                  연결 추가
                </Button>
              </div>
            </div>
          </div>
        )}

        {selected && (
          <div>
            <StepRuntimeInspector
              node={selected}
              runtime={runtimeMap[selected.id]}
              cached={graphId ? loadStepLocal(graphId, selected.id) : null}
              busy={busy}
              onSave={(input, output) => saveNodeRuntime(selected.id, input, output)}
              onRestore={() => restoreNodeRuntime(selected.id)}
              onRetry={() => reprocessNode(selected.id, true)}
            />
          </div>
        )}
        </div>
    </PageShell>
  );
}

function StepRuntimeInspector({
  node,
  runtime,
  cached,
  busy,
  onSave,
  onRestore,
  onRetry,
}: {
  node: GraphNode;
  runtime?: NodeRuntime;
  cached: StepCache | null;
  busy: boolean;
  onSave: (input: Record<string, unknown>, output: Record<string, unknown>) => Promise<void>;
  onRestore: () => void;
  onRetry: () => Promise<void>;
}) {
  const initialInput = runtime?.input ?? inputCandidates(node)?.payload ?? {};
  const initialOutput = runtime?.output ?? outputCandidates(node)?.payload ?? {};
  const [inputText, setInputText] = useState(JSON.stringify(initialInput, null, 2));
  const [outputText, setOutputText] = useState(JSON.stringify(initialOutput, null, 2));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setInputText(JSON.stringify(runtime?.input ?? inputCandidates(node)?.payload ?? {}, null, 2));
    setOutputText(JSON.stringify(runtime?.output ?? outputCandidates(node)?.payload ?? {}, null, 2));
    setError(null);
  }, [node.id, runtime?.input, runtime?.output]);

  function parseDrafts() {
    const input = JSON.parse(inputText) as Record<string, unknown>;
    const output = JSON.parse(outputText) as Record<string, unknown>;
    if (!input || Array.isArray(input) || typeof input !== "object") throw new Error("INPUT은 JSON object여야 합니다.");
    if (!output || Array.isArray(output) || typeof output !== "object") throw new Error("OUTPUT은 JSON object여야 합니다.");
    return { input, output };
  }

  const observed = runtime?.output?.observed === true;
  return (
    <div className="gql-inspector anim-slide-up" data-testid="flow-gql-inspector">
      <header className="gql-inspector-head">
        <div>
          <p className="gql-kicker">단계 실행 I/O · 저장/복원 가능</p>
          <h3>{flowStepLabel(node.type, node.name, String(node.attributes?.role ?? ""))}</h3>
        </div>
        <div className="gql-inspector-actions">
          <span className={`gql-status gql-status-${runtime?.status || "unknown"}`}>
            {statusKo(runtime?.status)}{observed ? " · 실행 관측" : " · 실행 전"}
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={!cached || busy}
            onClick={() => {
              onRestore();
              setError(null);
            }}
            data-testid="flow-inspector-restore"
          >
            저장값 복원
          </Button>
          <Button
            variant="secondary"
            size="sm"
            busy={busy}
            onClick={() => void onRetry()}
            data-testid="flow-inspector-reprocess"
          >
            저장값으로 재처리
          </Button>
        </div>
      </header>
      <div className="gql-inspector-grid">
        <section className="gql-pane">
          <h4>Query / Operation</h4>
          <pre data-testid="flow-operation">{formatOperation(node, runtime)}</pre>
        </section>
        <section className="gql-pane gql-pane-editable">
          <h4>Variables (Input) · 실제 단계 입력</h4>
          <textarea
            value={inputText}
            onChange={(event) => setInputText(event.target.value)}
            spellCheck={false}
            aria-label="단계 입력 JSON"
            data-testid="flow-io-input"
          />
        </section>
        <section className="gql-pane gql-pane-editable">
          <h4>Response (Output) · 실행 관측</h4>
          <textarea
            value={outputText}
            onChange={(event) => setOutputText(event.target.value)}
            spellCheck={false}
            aria-label="단계 출력 JSON"
            data-testid="flow-io-output"
          />
        </section>
      </div>
      <div className="gql-inspector-savebar">
        <span className={error ? "error-inline" : "muted"}>
          {error || (cached ? `브라우저 저장: ${new Date(cached.savedAt).toLocaleString("ko-KR")}` : "아직 저장된 단계 값이 없습니다.")}
        </span>
        <Button
          variant="primary"
          size="sm"
          busy={busy}
          onClick={() => {
            try {
              const parsed = parseDrafts();
              setError(null);
              void onSave(parsed.input, parsed.output);
            } catch (reason) {
              setError(reason instanceof Error ? reason.message : "JSON 형식을 확인하세요.");
            }
          }}
          data-testid="flow-inspector-save"
        >
          이 단계 값 저장
        </Button>
      </div>
    </div>
  );
}

type IoCandidates = { source: string; payload: Record<string, unknown> } | null;

/**
 * Renders observed I/O, or the analysis-derived field skeleton when nothing ran yet.
 * Values stay null when unobserved — never filled in.
 */
function IoPane({
  observed,
  fallback,
  emptyNote,
  testId,
}: {
  observed?: Record<string, unknown> | null;
  fallback: IoCandidates;
  emptyNote: string;
  testId: string;
}) {
  const entries = observed ? Object.entries(observed) : [];
  const hasValue = entries.some(([, v]) => v !== null && v !== undefined);
  if (entries.length > 0) {
    return (
      <div data-testid={testId} data-io-state={hasValue ? "observed" : "candidate"}>
        {!hasValue && <p className="gql-io-note">필드만 확인됨 · 값은 미관측(null)</p>}
        <pre>{JSON.stringify(observed, null, 2)}</pre>
        {!hasValue && <p className="gql-io-source">근거: 정적 분석 필드 · 실행 관측 전</p>}
      </div>
    );
  }
  if (fallback) {
    return (
      <div data-testid={testId} data-io-state="candidate">
        <p className="gql-io-note">정적 분석 기준 필드입니다 · 값은 미관측(null)</p>
        <pre>{JSON.stringify(fallback.payload, null, 2)}</pre>
        <p className="gql-io-source">근거: {fallback.source}</p>
      </div>
    );
  }
  return (
    <p className="gql-io-empty" data-testid={testId} data-io-state="missing">
      missing_data — {emptyNote}
    </p>
  );
}

function fieldsToNullMap(names: string[]): Record<string, unknown> {
  return names.reduce<Record<string, unknown>>((acc, name) => {
    acc[name] = null;
    return acc;
  }, {});
}

function inputCandidates(node: GraphNode): IoCandidates {
  const attrs = (node.attributes ?? {}) as Record<string, unknown>;
  const screenInputs = Array.isArray(attrs.inputs) ? (attrs.inputs as Array<Record<string, unknown>>) : [];
  if (screenInputs.length > 0) {
    return {
      source: `화면 입력 컨트롤 ${screenInputs.length}개 (정적 분석)`,
      payload: fieldsToNullMap(
        screenInputs.map((f, i) => String(f.field ?? f.name ?? `field_${i}`)),
      ),
    };
  }
  const dtoFields = Array.isArray(attrs.fields) ? (attrs.fields as Array<Record<string, unknown>>) : [];
  if (dtoFields.length > 0) {
    return {
      source: `${String(attrs.dtoName ?? "DTO")} 필드 (정적 분석)`,
      payload: fieldsToNullMap(dtoFields.map((f, i) => String(f.name ?? `field_${i}`))),
    };
  }
  const requestFields = Array.isArray(attrs.requestFields)
    ? (attrs.requestFields as unknown[]).map(String)
    : [];
  const pathParams = Array.isArray(attrs.pathParams)
    ? (attrs.pathParams as unknown[]).map(String)
    : [];
  const merged = [...pathParams, ...requestFields];
  if (merged.length > 0) {
    const parts = [
      pathParams.length ? `path 파라미터 ${pathParams.length}개` : null,
      requestFields.length ? `요청 필드 ${requestFields.length}개` : null,
    ].filter(Boolean);
    return { source: `${parts.join(" · ")} (정적 분석)`, payload: fieldsToNullMap(merged) };
  }
  return null;
}

function outputCandidates(node: GraphNode): IoCandidates {
  const attrs = (node.attributes ?? {}) as Record<string, unknown>;
  const dtoName = attrs.responseDtoName ?? (node.type === "response_dto" ? attrs.dtoName : null);
  const statuses = Array.isArray(attrs.statusCandidates)
    ? (attrs.statusCandidates as unknown[]).map(String)
    : [];
  const dtoFields = Array.isArray(attrs.fields) ? (attrs.fields as Array<Record<string, unknown>>) : [];
  if (dtoFields.length > 0) {
    return {
      source: `${String(dtoName ?? "DTO")} 필드 (정적 분석)`,
      payload: fieldsToNullMap(dtoFields.map((f, i) => String(f.name ?? `field_${i}`))),
    };
  }
  if (dtoName || statuses.length > 0) {
    const payload: Record<string, unknown> = {};
    if (dtoName) payload.responseType = String(dtoName);
    if (statuses.length > 0) payload.statusCandidates = statuses;
    payload.body = null;
    return { source: "Backend 분석 응답 타입 · 상태 후보 (필드 목록 미추출)", payload };
  }
  return null;
}

/** Absolute workspace paths are noise in the console — keep the tail only. */
function shortenRef(value: string): string {
  if (!value.includes("/")) return value;
  const parts = value.split("/").filter(Boolean);
  if (parts.length <= 3) return value;
  return `…/${parts.slice(-3).join("/")}`;
}

function formatOperation(node: GraphNode, runtime?: NodeRuntime): string {
  if (runtime?.operation && Object.keys(runtime.operation).length > 0) {
    return JSON.stringify(runtime.operation, null, 2);
  }
  const attrs = node.attributes ?? {};
  const method = String(runtime?.method || attrs.method || attrs.httpMethod || "POST").toUpperCase();
  const path = String(attrs.path || attrs.endpoint || attrs.url || node.name || "/api");
  const opName = String(attrs.operationName || node.name || "ApiCall")
    .replace(/[^a-zA-Z0-9_]/g, "_")
    .replace(/^(\d)/, "_$1");
  const isApi =
    node.type === "frontend_api_call" ||
    node.type === "backend_endpoint" ||
    node.type === "service";
  if (!isApi) {
    return JSON.stringify(
      {
        kind: "browser",
        stepId: attrs.scenarioStepId || node.id,
        action: attrs.action || node.type,
        target: attrs.target || null,
      },
      null,
      2,
    );
  }
  return JSON.stringify({ kind: "http", operation: opName, method, path }, null, 2);
}

function layoutGraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
  primaryPath: string[],
  branch: string,
  cols: number,
): LaidOut[] {
  if (nodes.length === 0) return [];
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  let spine = primaryPath.filter((id) => nodeMap.has(id));
  const spineOnlyBindings =
    spine.length > 0 && spine.every((id) => nodeMap.get(id)?.type === "binding");
  if (spine.length === 0 || spineOnlyBindings) {
    const order = [
      "screen",
      "frontend_api_call",
      "backend_endpoint",
      "request_dto",
      "response_dto",
      "service",
      "route_transition",
      "binding",
    ];
    const rebuilt: string[] = [];
    for (const t of order) {
      for (const n of nodes) {
        if (n.type === t && !rebuilt.includes(n.id)) rebuilt.push(n.id);
      }
    }
    if (rebuilt.length > 0) spine = rebuilt;
  }
  if (spine.length === 0) spine = nodes.map((n) => n.id);

  // Reading order: spine first, then edge successors, then remaining nodes.
  const order: string[] = [];
  const seen = new Set<string>();
  const push = (id: string) => {
    if (seen.has(id) || !nodeMap.has(id)) return;
    seen.add(id);
    order.push(id);
  };
  spine.forEach(push);

  const branchEdges = edges.filter(
    (e) => e.condition && e.condition !== "happy_path" && e.condition !== branch,
  );
  for (const edge of [...edges, ...branchEdges]) push(edge.to);
  for (const node of nodes) {
    if (node.type === "binding") continue;
    push(node.id);
  }

  // Wrap the chain into rows so a long A→API→B path stays inside the viewport
  const perRow = Math.max(MIN_COLS, cols);
  const placed = order.map((id, index) => {
    const node = nodeMap.get(id)!;
    const row = Math.floor(index / perRow);
    const col = index % perRow;
    const h = node.type === "screen" ? NODE_H_SCREEN : NODE_H;
    return {
      id,
      node,
      x: PAD + col * (NODE_W + GAP_X),
      y: PAD + row * ROW_H + (NODE_H_SCREEN - h) / 2,
      w: NODE_W,
      h,
      lane: row,
    } satisfies LaidOut;
  });

  return placed;
}

function FlowNodePanel({
  graph,
  selected,
  runtime,
  busy,
  onSave,
  onRetry,
}: {
  graph: GraphSummary | null;
  selected: GraphNode | null;
  runtime?: NodeRuntime;
  busy: boolean;
  onSave: (nodeId: string, input: Record<string, unknown>, output: Record<string, unknown>) => Promise<void>;
  onRetry: (nodeId: string, input: Record<string, unknown>) => Promise<void>;
}) {
  const [editInput, setEditInput] = useState("{}");
  const [editOutput, setEditOutput] = useState("{}");
  const [localErr, setLocalErr] = useState<string | null>(null);

  useEffect(() => {
    if (!selected) return;
    setEditInput(JSON.stringify(runtime?.input ?? selected.attributes?.sampleInput ?? {}, null, 2));
    setEditOutput(
      JSON.stringify(runtime?.output ?? selected.attributes?.sampleOutput ?? {}, null, 2),
    );
  }, [selected?.id, runtime]);

  if (!selected) {
    return (
      <div className="right-panel">
        <p className="panel-kicker">의존관계 그래프</p>
        <h3 className="panel-title">단계를 선택하세요</h3>
        <ul className="panel-lines">
          <li>{graph?.graphId ?? "그래프 선택"}</li>
          <li>단계 {graph?.nodeCount ?? 0}개</li>
        </ul>
        <p className="panel-note">
          예: [로그인 시작] → [아이디 입력] → [패스워드 입력] → [결과 확인]. 클릭 시 INPUT/OUTPUT을 봅니다.
        </p>
      </div>
    );
  }

  const stepTitle = flowStepLabel(
    selected.type,
    selected.name,
    String(selected.attributes?.role ?? ""),
  );

  return (
    <div className="right-panel">
      <p className="panel-kicker">GraphQL I/O</p>
      <h3 className="panel-title">{stepTitle}</h3>
      <ul className="panel-lines">
        <li>기술명 {selected.name}</li>
        <li>유형 {typeKo(selected.type)}</li>
        <li>상태 {statusKo(runtime?.status)}</li>
      </ul>
      {runtime?.errorMessage && (
        <p className="outcome-reason outcome-be_error">{runtime.errorMessage}</p>
      )}
      <label className="io-label">
        Variables (Input)
        <textarea className="io-textarea" rows={5} value={editInput} onChange={(e) => setEditInput(e.target.value)} />
      </label>
      <label className="io-label">
        Response (Output)
        <textarea className="io-textarea" rows={5} value={editOutput} onChange={(e) => setEditOutput(e.target.value)} />
      </label>
      {localErr && <p className="error-inline">{localErr}</p>}
      <div className="row-actions" style={{ marginTop: 8 }}>
        <button
          type="button"
          className="action-btn action-btn-edit"
          disabled={busy}
          onClick={() => {
            try {
              void onSave(
                selected.id,
                JSON.parse(editInput) as Record<string, unknown>,
                JSON.parse(editOutput) as Record<string, unknown>,
              );
              setLocalErr(null);
            } catch {
              setLocalErr("JSON 형식을 확인하세요.");
            }
          }}
        >
          입출력 저장
        </button>
        <button
          type="button"
          className="action-btn action-btn-analyze"
          disabled={busy}
          onClick={() => {
            try {
              void onRetry(selected.id, JSON.parse(editInput) as Record<string, unknown>);
              setLocalErr(null);
            } catch {
              setLocalErr("INPUT JSON 형식을 확인하세요.");
            }
          }}
        >
          재시도
        </button>
      </div>
    </div>
  );
}

function inferStatus(node: GraphNode): NodeRuntime["status"] {
  const vs = String(node.verificationStatus || "").toLowerCase();
  if (vs.includes("fail") || vs.includes("error")) return "failure";
  if (Number(node.confidence ?? 0) >= 0.85) return "success";
  return "unknown";
}

function statusKo(status?: string | null) {
  if (status === "success") return "성공";
  if (status === "failure") return "실패";
  if (status === "warning") return "확인 필요";
  if (status === "pending") return "대기";
  return "미확인";
}

function typeKo(type: string) {
  const map: Record<string, string> = {
    screen: "화면",
    input: "입력",
    event: "이벤트",
    validation: "검증",
    frontend_api_call: "FE API",
    backend_endpoint: "BE API",
    request_dto: "Request",
    response_dto: "Response",
    service: "Service",
    route_transition: "이동",
    binding: "바인딩",
  };
  return map[type] || type;
}

function labelKo(label: string) {
  const map: Record<string, string> = {
    happy_path: "정상 경로",
    triggers: "트리거",
    calls: "호출",
    navigates_to: "화면 이동",
    binds_to: "바인딩",
    contains: "포함",
  };
  return map[label] || label;
}

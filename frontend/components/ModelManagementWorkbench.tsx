"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "../lib/apiClient";
import type { CsvRow } from "../lib/csv";
import { formatDateTime } from "../lib/datetime";
import { useTableSelection } from "../lib/tableSelection";
import { Breadcrumbs } from "./Breadcrumbs";
import { CommonDataTable } from "./CommonDataTable";
import { PageShell } from "./PageShell";
import { matchesQuery, ScreenSearch } from "./ScreenSearch";
import {
  TableBulkDeleteForm,
  confirmBulkDelete,
} from "./TableBulkDeleteForm";
import { Button } from "./ui";
import type { ModelCapability as Capability } from "./ModelSelectionDialog";

type ModelProfile = {
  id: string;
  displayName: string;
  provider: string;
  endpoint: string;
  apiBasePath: string;
  modelsPath: string;
  modelId: string;
  deploymentType: "internal" | "external";
  capabilities: Capability[];
  contextWindow: number;
  supportsStructuredOutput: boolean;
  supportsTools: boolean;
  enabled: boolean;
  qualityScore: number;
  costScore: number;
  speedScore: number;
  reliabilityScore: number;
  healthStatus: "unknown" | "up" | "degraded" | "down";
  lastHealthAt?: string | null;
  healthLatencyMs?: number | null;
  lastError?: string | null;
  discoveredModels: string[];
  hasApiKey: boolean;
  createdAt: string;
  updatedAt: string;
};

type ModelForm = Omit<ModelProfile, "id" | "healthStatus" | "lastHealthAt" | "healthLatencyMs" | "lastError" | "discoveredModels" | "hasApiKey" | "createdAt" | "updatedAt"> & { apiKey: string };

const EMPTY: ModelForm = {
  displayName: "",
  provider: "openai-compatible",
  endpoint: "http://127.0.0.1:11434",
  apiBasePath: "/v1",
  modelsPath: "/v1/models",
  modelId: "",
  deploymentType: "internal",
  capabilities: ["chat", "code"],
  contextWindow: 32768,
  supportsStructuredOutput: true,
  supportsTools: false,
  enabled: true,
  qualityScore: 70,
  costScore: 70,
  speedScore: 70,
  reliabilityScore: 70,
  apiKey: "",
};

const CAPABILITIES: Capability[] = ["chat", "code", "vision", "embedding", "tools", "image_generation"];

const OPENAI_PRESETS: Record<"gpt-5" | "gpt-image-2", Partial<ModelForm>> = {
  "gpt-5": {
    displayName: "OpenAI · GPT-5 고급 추론·Vision",
    provider: "openai",
    endpoint: "https://api.openai.com",
    apiBasePath: "/v1",
    modelsPath: "/v1/models",
    modelId: "gpt-5",
    deploymentType: "external",
    capabilities: ["chat", "code", "vision", "tools"],
    contextWindow: 400000,
    supportsStructuredOutput: true,
    supportsTools: true,
    qualityScore: 98,
    costScore: 30,
    speedScore: 62,
    reliabilityScore: 95,
  },
  "gpt-image-2": {
    displayName: "OpenAI · GPT Image 2 생성·편집",
    provider: "openai",
    endpoint: "https://api.openai.com",
    apiBasePath: "/v1",
    modelsPath: "/v1/models",
    modelId: "gpt-image-2",
    deploymentType: "external",
    capabilities: ["image_generation"],
    contextWindow: 32768,
    supportsStructuredOutput: false,
    supportsTools: false,
    qualityScore: 96,
    costScore: 32,
    speedScore: 82,
    reliabilityScore: 92,
  },
};

function healthLabel(status: ModelProfile["healthStatus"]) {
  return { up: "정상", degraded: "주의", down: "연결 실패", unknown: "미확인" }[status];
}

export function ModelManagementWorkbench() {
  const [models, setModels] = useState<ModelProfile[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ModelForm>(EMPTY);

  const load = useCallback(async () => {
    const response = await apiFetch("/api/models", { cache: "no-store" });
    if (!response.ok) throw new Error("모델 목록을 불러오지 못했습니다");
    setModels((await response.json()) as ModelProfile[]);
  }, []);

  useEffect(() => {
    load().catch((error: Error) => setMessage(error.message)).finally(() => setLoading(false));
  }, [load]);

  const visible = useMemo(
    () => models.filter((item) => matchesQuery(query, item.displayName, item.modelId, item.endpoint, item.provider, ...item.capabilities)),
    [models, query],
  );
  const editingModel = useMemo(
    () => models.find((item) => item.id === editingId) ?? null,
    [editingId, models],
  );
  const selection = useTableSelection(visible.map((item) => item.id));

  function openCreate() {
    setEditingId(null);
    setForm(EMPTY);
    setMessage(null);
    setDrawerOpen(true);
  }

  function openPreset(id: keyof typeof OPENAI_PRESETS) {
    setEditingId(null);
    setForm({ ...EMPTY, ...OPENAI_PRESETS[id], apiKey: "" });
    setMessage(null);
    setDrawerOpen(true);
  }

  function openEdit(item: ModelProfile) {
    setEditingId(item.id);
    setForm({
      displayName: item.displayName,
      provider: item.provider,
      endpoint: item.endpoint,
      apiBasePath: item.apiBasePath,
      modelsPath: item.modelsPath,
      modelId: item.modelId,
      deploymentType: item.deploymentType,
      capabilities: item.capabilities,
      contextWindow: item.contextWindow,
      supportsStructuredOutput: item.supportsStructuredOutput,
      supportsTools: item.supportsTools,
      enabled: item.enabled,
      qualityScore: item.qualityScore,
      costScore: item.costScore,
      speedScore: item.speedScore,
      reliabilityScore: item.reliabilityScore,
      apiKey: "",
    });
    setDrawerOpen(true);
  }

  async function save() {
    if (!form.displayName.trim() || !form.modelId.trim() || !form.endpoint.trim()) {
      setMessage("표시명, 모델 ID, Endpoint를 입력하세요.");
      return;
    }
    setBusy(true);
    try {
      const payload: Partial<ModelForm> = { ...form };
      if (editingId && !form.apiKey) delete payload.apiKey;
      const response = await apiFetch(editingId ? `/api/models/${editingId}` : "/api/models", {
        method: editingId ? "PATCH" : "POST",
        body: JSON.stringify(payload),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "모델 저장 실패");
      const health = await apiFetch(`/api/models/${body.id}/health-check`, { method: "POST" });
      const checked = health.ok ? ((await health.json()) as ModelProfile) : (body as ModelProfile);
      const credentialStatus = checked.hasApiKey
        ? "API Key가 시스템 보안 저장소에 안전하게 저장되었습니다."
        : checked.deploymentType === "external"
          ? "API Key가 등록되지 않았습니다."
          : "";
      setMessage(
        checked.healthStatus === "up"
          ? `「${checked.displayName}」 저장과 Health Check가 완료되었습니다.${credentialStatus ? ` ${credentialStatus}` : ""}`
          : `모델은 저장했지만 Health Check 결과가 ${healthLabel(checked.healthStatus)}입니다.${credentialStatus ? ` ${credentialStatus}` : ""}`,
      );
      setDrawerOpen(false);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "모델 저장 실패");
    } finally {
      setBusy(false);
    }
  }

  async function healthCheck(id: string) {
    setBusy(true);
    try {
      const response = await apiFetch(`/api/models/${id}/health-check`, { method: "POST" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Health Check 실패");
      setMessage(`Health Check · ${healthLabel(body.healthStatus)}${body.healthLatencyMs != null ? ` · ${body.healthLatencyMs}ms` : ""}`);
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Health Check 실패");
    } finally {
      setBusy(false);
    }
  }

  async function deleteSelected() {
    if (!confirmBulkDelete("모델", selection.selectedIds.length)) return;
    setBusy(true);
    try {
      await Promise.all(selection.selectedIds.map((id) => apiFetch(`/api/models/${id}`, { method: "DELETE" })));
      selection.clear();
      setMessage("선택한 모델을 삭제했습니다.");
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function importCsv(rows: CsvRow[]) {
    setBusy(true);
    try {
      for (const row of rows) {
        const endpoint = String(row.endpoint || "").trim();
        const modelId = String(row.modelId || "").trim();
        if (!endpoint || !modelId) throw new Error("CSV에는 endpoint와 modelId가 필요합니다");
        const capabilities = String(row.capabilities || "chat,code").split(/[|,]/).map((item) => item.trim()).filter((item): item is Capability => CAPABILITIES.includes(item as Capability));
        const response = await apiFetch("/api/models", {
          method: "POST",
          body: JSON.stringify({ ...EMPTY, displayName: row.displayName || modelId, endpoint, modelId, capabilities }),
        });
        if (!response.ok) throw new Error(`${modelId} 등록 실패`);
      }
      setMessage(`${rows.length}개 모델을 가져왔습니다. API Key는 보안상 CSV로 가져오지 않습니다.`);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function previewSelection() {
    setBusy(true);
    try {
      const response = await apiFetch("/api/agent-monitor/selection-preview", {
        method: "POST",
        body: JSON.stringify({ workflowId: "wf_scenario_dsl", aiPolicy: "balanced" }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "선택 미리보기 실패");
      setMessage(`모델·Skill 선택 미리보기 ${body.traceId}를 남겼습니다. Agent 모니터링에서 후보 점수와 제외 사유를 확인하세요.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "선택 미리보기 실패");
    } finally {
      setBusy(false);
    }
  }

  return (
    <PageShell
      testId="model-management-page"
      header={
        <div className="content-header">
          <div>
            <Breadcrumbs trail={[{ label: "콘솔" }, { label: "관리" }, { label: "모델 관리" }]} />
            <h2>모델 관리</h2>
            <p className="muted" style={{ marginTop: 6 }}>
              OpenAI 호환 Endpoint를 등록하고 Core가 사용할 실제 capability와 상태를 관리합니다.
            </p>
          </div>
        </div>
      }
    >
      {message && <div className="agent-notice">{message}</div>}
      <CommonDataTable
        rows={visible}
        totalCount={models.length}
        toolbar={
          <>
            <ScreenSearch value={query} onChange={setQuery} placeholder="모델명 · ID · Endpoint · capability" />
            <TableBulkDeleteForm
              embedded
              noun="모델"
              totalCount={visible.length}
              selectedCount={selection.selectedIds.length}
              busy={busy}
              onDelete={deleteSelected}
              onImportCsv={importCsv}
              testId="model-table-bulk-form"
              extraActions={<><Button variant="secondary" size="sm" onClick={previewSelection} disabled={busy}>선택 미리보기</Button><Button variant="secondary" size="sm" onClick={() => openPreset("gpt-5")}>GPT-5 등록</Button><Button variant="secondary" size="sm" onClick={() => openPreset("gpt-image-2")}>GPT Image 2 등록</Button><Button size="sm" onClick={openCreate}>직접 등록</Button></>}
            />
          </>
        }
        rowKey={(item) => item.id}
        testId="model-table"
        loading={loading}
        emptyText="등록된 모델이 없습니다"
        loadingText="모델 목록을 불러오는 중입니다"
        selection={{
          selected: selection.checked,
          onChange: selection.setChecked,
          label: (item) => `${item.displayName} 선택`,
        }}
        timestamps={{
          createdAt: (item) => item.createdAt,
          updatedAt: (item) => item.updatedAt,
        }}
        columns={[
          {
            key: "model",
            label: "모델",
            sortValue: (item) => item.displayName,
            cell: (item) => <button className="link-btn model-name-btn" onClick={() => openEdit(item)}><strong>{item.displayName}</strong><small>{item.modelId} · {item.contextWindow.toLocaleString()} tokens</small>{item.deploymentType === "external" && <span className={`model-secret-status ${item.hasApiKey ? "is-saved" : "is-missing"}`}>{item.hasApiKey ? "API Key 안전 저장됨" : "API Key 필요"}</span>}</button>,
          },
          {
            key: "endpoint",
            label: "Endpoint",
            sortValue: (item) => item.endpoint,
            cell: (item) => <span className="cell-stack"><code>{item.endpoint}</code><small>{item.modelsPath}</small></span>,
          },
          {
            key: "capability",
            label: "Capability",
            sortValue: (item) => item.capabilities.join(","),
            cell: (item) => <div className="model-capabilities">{item.capabilities.map((capability) => <span key={capability}>{capability}</span>)}</div>,
          },
          {
            key: "deployment",
            label: "배포",
            sortValue: (item) => item.deploymentType,
            cell: (item) => item.deploymentType === "internal" ? "내부망" : "외부",
          },
          {
            key: "status",
            label: "상태",
            sortValue: (item) => item.healthStatus,
            cell: (item) => <><span className={`status-badge status-${item.healthStatus === "up" ? "ok" : item.healthStatus === "down" ? "bad" : "warn"}`}>{healthLabel(item.healthStatus)}</span><small className="table-subline">{formatDateTime(item.lastHealthAt)}</small></>,
          },
          {
            key: "score",
            label: "선택 점수",
            sortValue: (item) => item.qualityScore + item.costScore + item.speedScore + item.reliabilityScore,
            cell: (item) => <span className="model-score">품질 {item.qualityScore} · 비용 {item.costScore}<small>속도 {item.speedScore} · 신뢰 {item.reliabilityScore}</small></span>,
          },
        ]}
        actions={(item) => <><Button variant="secondary" size="sm" onClick={() => healthCheck(item.id)} disabled={busy}>Health Check</Button><Button variant="secondary" size="sm" onClick={() => openEdit(item)}>수정</Button></>}
      />
      {drawerOpen && (
        <div className="schedule-drawer-layer" data-testid="model-drawer">
          <button className="schedule-drawer-scrim" aria-label="모델 창 닫기" onClick={() => setDrawerOpen(false)} />
          <aside className="schedule-drawer model-drawer">
            <header className="schedule-drawer-head"><div><span className="eyebrow">MODEL REGISTRY</span><h2>{editingId ? "모델 수정" : "모델 등록"}</h2><p>연결 정보를 저장한 뒤 모델 목록 Health Check를 수행합니다.</p></div><Button variant="secondary" onClick={() => setDrawerOpen(false)}>닫기</Button></header>
            <div className="schedule-drawer-body model-register-layout">
              <div className="model-register-form">
              <div className="model-preset-row"><span>빠른 입력</span><Button variant="secondary" size="sm" onClick={() => setForm({ ...form, ...OPENAI_PRESETS["gpt-5"] })}>GPT-5</Button><Button variant="secondary" size="sm" onClick={() => setForm({ ...form, ...OPENAI_PRESETS["gpt-image-2"] })}>GPT Image 2</Button></div>
              <section className="schedule-form-section"><h3>연결 정보</h3><div className="schedule-form-grid">
                <label><span>표시명</span><input value={form.displayName} onChange={(event) => setForm({ ...form, displayName: event.target.value })} placeholder="예: 사내 Qwen 32B" /></label>
                <label><span>모델 ID</span><input value={form.modelId} onChange={(event) => setForm({ ...form, modelId: event.target.value })} placeholder="qwen3.6:32b" /></label>
                <label><span>Endpoint</span><input value={form.endpoint} onChange={(event) => setForm({ ...form, endpoint: event.target.value })} placeholder="http://llm.internal:11434" /></label>
                <label><span>Models Path</span><input value={form.modelsPath} onChange={(event) => setForm({ ...form, modelsPath: event.target.value })} placeholder="/v1/models" /></label>
                <label><span>API Key</span><input type="password" value={form.apiKey} onChange={(event) => setForm({ ...form, apiKey: event.target.value })} placeholder={editingModel?.hasApiKey ? "안전 저장됨 · 변경할 때만 입력" : editingId ? "API Key를 입력하세요" : "외부 모델이면 입력"} autoComplete="new-password" /></label>
                <label><span>배포 유형</span><select value={form.deploymentType} onChange={(event) => setForm({ ...form, deploymentType: event.target.value as ModelForm["deploymentType"] })}><option value="internal">내부망</option><option value="external">외부</option></select></label>
              </div></section>
              <section className="schedule-form-section"><h3>Capability와 선택 메타데이터</h3><div className="model-capability-checks">{CAPABILITIES.map((capability) => <label key={capability}><input type="checkbox" checked={form.capabilities.includes(capability)} onChange={(event) => setForm({ ...form, capabilities: event.target.checked ? [...form.capabilities, capability] : form.capabilities.filter((item) => item !== capability) })} />{capability}</label>)}</div><div className="schedule-form-grid three">
                <label><span>Context Window</span><input type="number" value={form.contextWindow} onChange={(event) => setForm({ ...form, contextWindow: Number(event.target.value) })} /></label>
                {(["qualityScore", "costScore", "speedScore", "reliabilityScore"] as const).map((key) => <label key={key}><span>{{ qualityScore: "품질", costScore: "비용 효율", speedScore: "속도", reliabilityScore: "신뢰도" }[key]} 점수</span><input type="number" min="0" max="100" value={form[key]} onChange={(event) => setForm({ ...form, [key]: Number(event.target.value) })} /></label>)}
              </div><div className="model-switches"><label><input type="checkbox" checked={form.supportsStructuredOutput} onChange={(event) => setForm({ ...form, supportsStructuredOutput: event.target.checked })} />Structured Output</label><label><input type="checkbox" checked={form.supportsTools} onChange={(event) => setForm({ ...form, supportsTools: event.target.checked })} />Tool Calling</label><label><input type="checkbox" checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} />선택 후보 활성</label></div></section>
              </div>
              <aside className="model-register-guide">
                <div className="model-guide-robot-wrap"><img src="/dashboard/qa-robot.png" alt="모델 등록을 안내하는 QA 로봇" /></div>
                <div className="model-guide-bubble">
                  <span>이렇게 등록하면 돼요!</span>
                  <h3>{form.modelId === "gpt-image-2" ? "GPT Image 2는 생성·편집용이에요" : form.modelId === "gpt-5" ? "GPT-5는 고급 추론과 화면 이해용이에요" : "연결할 모델의 실제 값을 입력해 주세요"}</h3>
                  <ul>
                    <li><b>Endpoint</b> OpenAI는 <code>https://api.openai.com</code></li>
                    <li><b>Model ID</b> 서버가 제공하는 정확한 ID</li>
                    <li><b>Capability</b> 실제 지원 기능만 선택</li>
                    <li><b>API Key</b> macOS Keychain에 보관하고 화면·API 응답에는 노출하지 않음</li>
                  </ul>
                  <p>화면·PPT 인식은 <b>vision</b>, 새 이미지 만들기는 <b>image_generation</b>으로 구분해 주세요.</p>
                </div>
              </aside>
            </div>
            <footer className="schedule-drawer-foot"><Button variant="secondary" onClick={() => setDrawerOpen(false)}>취소</Button><Button busy={busy} onClick={save}>{editingId ? "저장 후 점검" : "등록 후 점검"}</Button></footer>
          </aside>
        </div>
      )}
    </PageShell>
  );
}

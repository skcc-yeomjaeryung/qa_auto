"use client";

import { useEffect, useMemo, useState } from "react";
import { matchesQuery } from "./ScreenSearch";
import { Button } from "./ui";

export type ModelCapability =
  | "chat"
  | "code"
  | "vision"
  | "embedding"
  | "tools"
  | "image_generation";

export type SelectableModelProfile = {
  id: string;
  displayName: string;
  modelId: string;
  provider: string;
  deploymentType: "internal" | "external";
  capabilities: ModelCapability[];
  contextWindow: number;
  enabled: boolean;
  healthStatus: "unknown" | "up" | "degraded" | "down";
  hasApiKey: boolean;
};

function healthCopy(item: SelectableModelProfile) {
  if (item.deploymentType === "external" && !item.hasApiKey) return "API Key 필요";
  return {
    up: "연결 정상",
    degraded: "연결 주의",
    down: "연결 실패",
    unknown: "점검 전",
  }[item.healthStatus];
}

export function ModelSelectionDialog({
  open,
  roleLabel,
  roleDescription,
  models,
  requiredCapabilities,
  selectedId,
  onSelect,
  onClose,
}: {
  open: boolean;
  roleLabel: string;
  roleDescription: string;
  models: SelectableModelProfile[];
  requiredCapabilities: ModelCapability[];
  selectedId?: string;
  onSelect: (model: SelectableModelProfile) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!open) return;
    setQuery("");
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  const eligible = useMemo(() => {
    const required = new Set(requiredCapabilities);
    return models.filter((item) => (
      item.enabled
      && Array.from(required).every((capability) => item.capabilities.includes(capability))
      && matchesQuery(
        query,
        item.displayName,
        item.modelId,
        item.provider,
        item.deploymentType,
        ...item.capabilities,
      )
    ));
  }, [models, query, requiredCapabilities]);

  if (!open) return null;

  return (
    <div className="model-picker-layer" data-testid="project-model-picker">
      <button className="model-picker-scrim" aria-label="모델 선택 닫기" onClick={onClose} />
      <section className="model-picker-dialog" role="dialog" aria-modal="true" aria-labelledby="model-picker-title">
        <header className="model-picker-head">
          <div>
            <span className="eyebrow">MODEL FOR ROLE</span>
            <h2 id="model-picker-title">{roleLabel} 모델 선택</h2>
            <p>{roleDescription}</p>
          </div>
          <Button variant="secondary" size="sm" onClick={onClose}>닫기</Button>
        </header>
        <div className="model-picker-search">
          <span aria-hidden>⌕</span>
          <input
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="모델명 · 모델 ID · capability 검색"
            aria-label="모델 검색"
          />
        </div>
        <div className="model-picker-required">
          <span>필수 capability</span>
          {requiredCapabilities.map((capability) => <b key={capability}>{capability}</b>)}
        </div>
        <div className="model-picker-list">
          {eligible.length === 0 ? (
            <div className="model-picker-empty">
              <strong>선택할 수 있는 모델이 없습니다.</strong>
              <span>관리 › 모델 관리에서 capability와 Health 상태를 확인하세요.</span>
            </div>
          ) : eligible.map((item) => {
            const unavailable = item.healthStatus === "down" || (item.deploymentType === "external" && !item.hasApiKey);
            return (
              <button
                key={item.id}
                type="button"
                className={`model-picker-item${selectedId === item.id ? " is-selected" : ""}`}
                disabled={unavailable}
                onClick={() => {
                  onSelect(item);
                  onClose();
                }}
              >
                <span className="model-picker-item-main">
                  <strong>{item.displayName}</strong>
                  <small>{item.modelId} · {item.contextWindow.toLocaleString()} tokens</small>
                  <span className="model-picker-caps">
                    {item.capabilities.map((capability) => <i key={capability}>{capability}</i>)}
                  </span>
                </span>
                <span className="model-picker-item-side">
                  <b className={`is-${item.healthStatus}`}>{healthCopy(item)}</b>
                  <small>{item.deploymentType === "internal" ? "사내 모델" : "외부 API"}</small>
                </span>
              </button>
            );
          })}
        </div>
        <footer className="model-picker-foot">
          <span>선택값은 프로젝트에 저장되며 수정 화면에서 언제든 바꿀 수 있습니다.</span>
          <Button variant="secondary" size="sm" onClick={onClose}>취소</Button>
        </footer>
      </section>
    </div>
  );
}

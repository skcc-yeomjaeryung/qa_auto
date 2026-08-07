"use client";

import { useEffect, useState } from "react";

import { ImageLightbox } from "./ImageLightbox";
import { shotLabelKo } from "../lib/evidenceLabels";
import { apiFetch } from "../lib/apiClient";
import { actionToastId, showActionToast } from "../lib/actionToast";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";

type EvidenceItem = {
  name: string;
  relativePath: string;
  url: string;
  stepId?: string;
};

type EvidencePayload = {
  runId: string;
  screenshots: EvidenceItem[];
  snapshots: EvidenceItem[];
  missing_data?: string[];
};

export function EvidenceGallery({
  runId,
  scenarioId,
  /** 값이 바뀔 때마다 다시 조회한다 (실행 중 증적 갱신). */
  reloadToken,
}: {
  runId?: string | null;
  scenarioId?: string | null;
  reloadToken?: string | number;
}) {
  const [payload, setPayload] = useState<EvidencePayload | null>(null);
  const [resolvedRunId, setResolvedRunId] = useState<string | null>(runId || null);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setError(null);
      try {
        let rid = runId || null;
        if (!rid && scenarioId) {
          const res = await apiFetch(`/api/scenarios/${scenarioId}/runs`, { cache: "no-store" });
          if (res.ok) {
            const runs = (await res.json()) as Array<{ runId: string }>;
            rid = runs[0]?.runId || null;
          }
        }
        if (!rid) {
          if (!cancelled) {
            setResolvedRunId(null);
            setPayload(null);
          }
          return;
        }
        setResolvedRunId(rid);
        const ev = await apiFetch(`/api/runs/${rid}/evidence`, { cache: "no-store" });
        if (!ev.ok) throw new Error("증적을 불러오지 못했습니다");
        const data = (await ev.json()) as EvidencePayload;
        if (!cancelled) setPayload(data);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "증적 로드 실패");
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [runId, scenarioId, reloadToken]);

  if (error) {
    return <div className="connect-banner is-warn">{error}</div>;
  }

  if (!resolvedRunId) {
    return (
      <div className="evidence-gallery empty">
        <p className="muted">아직 실행 증적이 없습니다. 「테스트 실행」 후 스크린샷이 여기에 표시됩니다.</p>
        <p className="missing-data-tag">missing_data: screenshots</p>
      </div>
    );
  }

  const shots = payload?.screenshots || [];
  const missing = payload?.missing_data || [];

  async function download(url: string, filename: string) {
    const toastId = actionToastId("evidence-download", filename);
    showActionToast({ id: toastId, title: "증적 다운로드", message: `${filename} 다운로드를 시작했습니다.`, tone: "progress" });
    try {
      const response = await apiFetch(url);
      if (!response.ok) throw new Error("증적 다운로드에 실패했습니다");
      const blob = await response.blob();
      const href = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = href;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(href);
      showActionToast({ id: toastId, title: "증적 다운로드 완료", message: `${filename} 파일을 내려받았습니다.`, tone: "success" });
    } catch (cause) {
      const errorMessage = cause instanceof Error ? cause.message : "증적 다운로드 실패";
      setError(errorMessage);
      showActionToast({ id: toastId, title: "증적 다운로드 실패", message: errorMessage, tone: "error" });
    }
  }

  return (
    <div className="evidence-gallery" data-testid="evidence-gallery">
      <div className="evidence-gallery-head">
        <div>
          <h3>실행 증적 (스크린샷)</h3>
          <span className="muted">run {resolvedRunId} · 이미지를 누르면 원본 크기로 확대됩니다</span>
        </div>
        <button
          type="button"
          className="ghost-btn"
          onClick={() => void download(`/api/runs/${resolvedRunId}/evidence/download`, `${resolvedRunId}-evidence.zip`)}
          data-testid="evidence-download-all"
        >
          현재 증적 ZIP
        </button>
      </div>
      {missing.length > 0 && shots.length === 0 && (
        <p className="missing-data-tag">{missing.join(" · ")}</p>
      )}
      {shots.length === 0 ? (
        <p className="muted">스크린샷 파일이 아직 없습니다. 실행이 끝나면 입력 직후·결과 화면 증적이 쌓입니다.</p>
      ) : (
        <div className="evidence-grid">
          {shots.map((shot, i) => (
            <figure key={shot.relativePath} className="evidence-card">
              <button
                type="button"
                className="evidence-zoom"
                onClick={() => setZoom(i)}
                aria-label={`${shot.name} 크게 보기`}
                data-testid="evidence-zoom"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={`${API}${shot.url}`} alt={shot.name} loading="lazy" />
                <span className="evidence-zoom-hint" aria-hidden>
                  클릭하면 확대
                </span>
              </button>
              <figcaption>
                <div className="evidence-caption-title">
                  <strong>{shotLabelKo(shot.name)}</strong>
                  <button
                    type="button"
                    className="evidence-download-btn"
                    onClick={() => void download(shot.url, shot.name)}
                    data-testid="evidence-download-item"
                  >
                    다운로드
                  </button>
                </div>
                <span className="muted">
                  {shot.name}
                  {shot.stepId ? ` · ${shot.stepId}` : ""}
                </span>
              </figcaption>
            </figure>
          ))}
        </div>
      )}
      {zoom !== null && (
        <ImageLightbox
          images={shots.map((s) => ({
            src: `${API}${s.url}`,
            caption: `${shotLabelKo(s.name)} · ${s.name}${s.stepId ? ` · ${s.stepId}` : ""}`,
          }))}
          index={zoom}
          onIndexChange={setZoom}
          onClose={() => setZoom(null)}
        />
      )}
    </div>
  );
}

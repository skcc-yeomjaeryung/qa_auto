"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "../lib/apiClient";
import { actionToastId, showActionToast } from "../lib/actionToast";
import { formatDateOnly, formatDateTime } from "../lib/datetime";
import { humanizeMissingEvidence } from "../lib/evidenceLabels";

type Artifact = {
  artifactId: string;
  type: string;
  path: string;
  mimeType: string;
  size: number;
  sha256: string;
  masked: boolean;
  stage?: string | null;
};

type Manifest = {
  evidenceId: string;
  runId: string;
  technicalStatus: string;
  reviewStatus: string;
  integrityStatus: "complete" | "partial" | "corrupted";
  storageStatus: "ready" | "write_failed";
  missingData: string[];
  artifacts: Artifact[];
  retentionUntil: string;
  createdAt: string;
};

type RunEvidence = {
  package?: Manifest | null;
  packagePreview?: PackagePreview | null;
};

type PackagePreview = {
  connectionStatus: "complete" | "partial";
  stages: Array<{
    id: string;
    title: string;
    status: "observed" | "partial" | "missing";
    summary: string;
    evidenceCount: number;
  }>;
  rawEvidence: { files: number; screenshots: number; snapshots: number };
  integrity: { status: string; message: string };
  masking: { status: string; message: string };
  missingData: string[];
};

const STAGES = [
  { id: "source", title: "A 입력", types: ["scenario", "source", "input"] },
  { id: "backend", title: "Request · Backend", types: ["network", "backend"] },
  { id: "destination", title: "B 화면 · Assertion", types: ["binding", "screenshot", "snapshot"] },
] as const;

export function EvidencePackageViewer({ runId }: { runId: string }) {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [preview, setPreview] = useState<PackagePreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    const response = await apiFetch(`/api/runs/${runId}/evidence`, {
      cache: "no-store",
    });
    if (!response.ok) throw new Error("증적 정보를 불러오지 못했습니다");
    const data = (await response.json()) as RunEvidence;
    setManifest(data.package || null);
    setPreview(data.packagePreview || null);
    setMessage(null);
  }, [runId]);

  useEffect(() => {
    load().catch((error: Error) => setMessage(error.message));
  }, [load]);

  async function finalize() {
    setBusy(true);
    setMessage(null);
    try {
      const response = await apiFetch(`/api/runs/${runId}/evidence/finalize`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      if (!response.ok) throw new Error("Evidence Package 생성에 실패했습니다");
      setManifest((await response.json()) as Manifest);
      setMessage("현재 실행 artifact를 마스킹·해시 처리해 패키지로 묶었습니다.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "증적 패키지 오류");
    } finally {
      setBusy(false);
    }
  }

  async function downloadPackage() {
    if (!manifest) return;
    const filename = `${manifest.evidenceId}.zip`;
    const toastId = actionToastId("evidence-package-download", manifest.evidenceId);
    showActionToast({ id: toastId, title: "증적 패키지 다운로드", message: `${filename} 다운로드를 시작했습니다.`, tone: "progress" });
    const response = await apiFetch(`/api/evidence/${manifest.evidenceId}/download`);
    if (!response.ok) {
      setMessage("ZIP 다운로드 권한 또는 파일 상태를 확인하세요.");
      showActionToast({ id: toastId, title: "증적 패키지 다운로드 실패", message: "ZIP 다운로드 권한 또는 파일 상태를 확인하세요.", tone: "error" });
      return;
    }
    const blob = await response.blob();
    const href = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = href;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(href);
    showActionToast({ id: toastId, title: "증적 패키지 다운로드 완료", message: `${filename} 파일을 내려받았습니다.`, tone: "success" });
  }

  async function openArtifact(artifact: Artifact) {
    if (!manifest) return;
    const response = await apiFetch(
      `/api/evidence/${manifest.evidenceId}/artifacts/${artifact.artifactId}`,
    );
    if (!response.ok) {
      setMessage("Artifact를 열 수 없습니다.");
      return;
    }
    const blob = await response.blob();
    window.open(URL.createObjectURL(blob), "_blank", "noopener,noreferrer");
  }

  const grouped = useMemo(() => {
    if (!manifest) return new Map<string, Artifact[]>();
    const map = new Map<string, Artifact[]>();
    for (const stage of STAGES) {
      map.set(
        stage.id,
        manifest.artifacts.filter((artifact) => {
          if (artifact.stage === stage.id) return true;
          if (stage.id === "destination" && artifact.stage === "input_completed") return false;
          return (stage.types as readonly string[]).includes(artifact.type);
        }),
      );
    }
    return map;
  }, [manifest]);

  return (
    <section className="evidence-package-viewer" data-testid="evidence-package-viewer">
      <div className="section-heading-row">
        <div>
          <h3 className="section-title">Evidence Package</h3>
          <p className="muted">
            실행에서 수집된 A 화면 입력 → Backend 요청·응답 → B 화면 결과가 서로 연결됐는지 먼저 확인합니다.
          </p>
        </div>
        <div className="inline-actions">
          <button className="ghost-btn" type="button" onClick={finalize} disabled={busy}>
            {busy ? "검증·생성 중…" : manifest ? "마스킹·해시 재검증" : "마스킹·해시 검증 후 패키지 생성"}
          </button>
          {manifest && (
            <button className="primary-btn" type="button" onClick={downloadPackage}>
              ZIP 다운로드
            </button>
          )}
        </div>
      </div>

      {message && <div className="connect-banner">{message}</div>}

      {!manifest ? (
        <div className="evidence-package-preview" data-testid="evidence-package-preview">
          <div className="evidence-manifest-strip">
            <div>
              <span>연결 상태</span>
              <strong className={preview?.connectionStatus === "complete" ? "integrity-complete" : "integrity-partial"}>
                {preview?.connectionStatus === "complete" ? "A→Backend→B 관측" : "연결 일부 관측"}
              </strong>
            </div>
            <div>
              <span>수집 파일</span>
              <strong>{preview?.rawEvidence.files ?? 0}개</strong>
            </div>
            <div>
              <span>무결성</span>
              <strong className="integrity-partial">검증 전</strong>
              <small>{preview?.integrity.message || "패키지 생성 후 SHA-256을 확인합니다"}</small>
            </div>
            <div>
              <span>마스킹</span>
              <strong className="integrity-partial">적용 대기</strong>
              <small>{preview?.masking.message || "패키지 생성 시 민감값을 마스킹합니다"}</small>
            </div>
          </div>

          <div className="evidence-lineage is-preview">
            {(preview?.stages || []).map((stage, index) => (
              <div className={`evidence-stage is-${stage.status}`} key={stage.id}>
                <div className="evidence-stage-head">
                  <span>{index + 1}</span>
                  <strong>{stage.title}</strong>
                  <em>{stage.status === "observed" ? "관측" : stage.status === "partial" ? "일부" : "미수집"}</em>
                </div>
                <p>{stage.summary}</p>
                <small>연결 증적 {stage.evidenceCount}단계</small>
              </div>
            ))}
          </div>

          {(preview?.missingData || []).length > 0 ? (
            <div className="connect-banner is-warn">
              <strong>패키지 생성 전 보강 필요</strong>
              <p>{preview?.missingData.map(humanizeMissingEvidence).join(" · ")}</p>
            </div>
          ) : (
            <div className="connect-banner">
              A→Backend→B 증적이 수집됐습니다. 패키지를 생성하면 마스킹·파일별 SHA-256·보존기한을 확정합니다.
            </div>
          )}
        </div>
      ) : (
        <>
          <div className="evidence-manifest-strip">
            <div>
              <span>무결성</span>
              <strong className={`integrity-${manifest.integrityStatus}`}>
                {integrityLabel(manifest.integrityStatus)}
              </strong>
            </div>
            <div>
              <span>Artifact</span>
              <strong>{manifest.artifacts.length}</strong>
            </div>
            <div>
              <span>마스킹</span>
              <strong>{manifest.artifacts.filter((item) => item.masked).length}</strong>
            </div>
            <div>
              <span>보존기한</span>
              <strong>{formatDateOnly(manifest.retentionUntil)}</strong>
            </div>
            <div>
              <span>수집 시각</span>
              <strong>{formatDateTime(manifest.createdAt)}</strong>
            </div>
          </div>

          {manifest.missingData.length > 0 && (
            <div className="connect-banner is-warn">
              <strong>추가 확인이 필요한 자료</strong>
              <p>{manifest.missingData.map(humanizeMissingEvidence).join(" · ")}</p>
            </div>
          )}

          <div className="evidence-lineage">
            {STAGES.map((stage, index) => (
              <div className="evidence-stage" key={stage.id}>
                <div className="evidence-stage-head">
                  <span>{index + 1}</span>
                  <strong>{stage.title}</strong>
                </div>
                <ul>
                  {(grouped.get(stage.id) || []).map((artifact) => (
                    <li key={artifact.artifactId}>
                      <button type="button" onClick={() => openArtifact(artifact)}>
                        {artifact.path}
                      </button>
                      <small>
                        {formatBytes(artifact.size)} · {artifact.sha256.slice(0, 10)}…
                        {artifact.masked ? " · masked" : ""}
                      </small>
                    </li>
                  ))}
                  {(grouped.get(stage.id) || []).length === 0 && (
                    <li className="muted">수집된 증적이 없습니다.</li>
                  )}
                </ul>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function integrityLabel(status: Manifest["integrityStatus"]) {
  return {
    complete: "무결성 확인 완료",
    partial: "일부 자료 확인 필요",
    corrupted: "무결성 재확인 필요",
  }[status];
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  return `${(value / 1024).toFixed(1)} KB`;
}

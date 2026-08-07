"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch } from "../lib/apiClient";
import { formatDateTime } from "../lib/datetime";

type Assertion = {
  assertionId: string;
  field: string;
  source: string;
  target: string;
  aInput?: unknown;
  frontendRequest?: unknown;
  backendRequest?: unknown;
  backendResponse?: unknown;
  uiValue?: unknown;
  result: "MATCH" | "MISMATCH" | "MISSING_DATA" | "REVIEW_REQUIRED";
  businessReviewRequired: boolean;
  masked: boolean;
  evidence?: {
    screenshotPath?: string | null;
    snapshotPath?: string | null;
    region?: Record<string, unknown> | null;
  };
  missingData: string[];
};

type Validation = {
  runId: string;
  technicalStatus: string;
  businessReviewRequired: boolean;
  assertions: Assertion[];
  missingData: string[];
  createdAt: string;
};

export function BindingAssertionsTable({ runId }: { runId: string }) {
  const [validation, setValidation] = useState<Validation | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await apiFetch(`/api/runs/${runId}/binding-validation`, {
      cache: "no-store",
    });
    if (res.status === 404) {
      setValidation(null);
      setMessage(null);
      return;
    }
    if (!res.ok) throw new Error("바인딩 비교 결과를 불러오지 못했습니다");
    setValidation((await res.json()) as Validation);
    setMessage(null);
  }, [runId]);

  useEffect(() => {
    load().catch((error: Error) => setMessage(error.message));
  }, [load]);

  async function validate() {
    setLoading(true);
    setMessage(null);
    try {
      const res = await apiFetch(`/api/runs/${runId}/validate-bindings`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      if (!res.ok) throw new Error("바인딩 기술 비교를 실행하지 못했습니다");
      setValidation((await res.json()) as Validation);
      setMessage("저장된 실행·Backend·화면 관측 증적을 필드 단위로 비교했습니다.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "바인딩 비교 오류");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section data-testid="binding-assertions">
      <div className="section-heading-row">
        <div>
          <h3 className="section-title">Input ↔ Request ↔ Response ↔ UI</h3>
          <p className="muted">
            기술 비교와 업무 검토 필요를 분리합니다. 최종 품질 판단은 HITL입니다.
          </p>
        </div>
        <button className="ghost-btn" type="button" onClick={validate} disabled={loading}>
          {loading ? "비교 중…" : "기술 비교 실행"}
        </button>
      </div>

      {message && <div className="connect-banner">{message}</div>}

      {validation ? (
        <>
          <div className="run-summary-bar">
            <span
              className={`outcome-pill ${
                validation.technicalStatus === "TECHNICALLY_MATCHED"
                  ? "outcome-success"
                  : "outcome-unknown"
              }`}
            >
              {technicalStatusLabel(validation.technicalStatus)}
            </span>
            <span className="muted">
              {validation.businessReviewRequired ? "고객 검증 필요" : "업무 검토 표시 없음"} ·{" "}
              {formatDateTime(validation.createdAt)}
            </span>
          </div>
          <div className="table-scroll">
            <table className="data-table binding-table">
              <thead>
                <tr>
                  <th>필드</th>
                  <th>A 입력</th>
                  <th>Frontend Request</th>
                  <th>Backend Request</th>
                  <th>Backend Response</th>
                  <th>B 화면</th>
                  <th>자동 비교</th>
                  <th>고객 검증</th>
                  <th>Mismatch 증적</th>
                </tr>
              </thead>
              <tbody>
                {validation.assertions.map((assertion) => (
                  <tr key={assertion.assertionId}>
                    <td>
                      <strong>{assertion.field}</strong>
                      <small className="muted binding-target">{assertion.target}</small>
                    </td>
                    <td>{display(assertion.aInput)}</td>
                    <td>{display(assertion.frontendRequest)}</td>
                    <td>{display(assertion.backendRequest)}</td>
                    <td>{display(assertion.backendResponse)}</td>
                    <td>{display(assertion.uiValue)}</td>
                    <td>
                      <span className={`binding-result is-${assertion.result.toLowerCase()}`}>
                        {resultLabel(assertion.result)}
                      </span>
                      {assertion.missingData.length > 0 && (
                        <small className="muted binding-target">
                          {assertion.missingData.join(", ")}
                        </small>
                      )}
                    </td>
                    <td>{assertion.businessReviewRequired ? "필요" : "—"}</td>
                    <td>
                      {assertion.result === "MISMATCH" && assertion.evidence?.screenshotPath ? (
                        <span title={assertion.evidence.screenshotPath}>
                          {fileName(assertion.evidence.screenshotPath)}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <div className="empty-state compact">
          <p>아직 저장된 바인딩 비교 결과가 없습니다.</p>
          <small>실행 증적이 없으면 값을 추정하지 않고 missing_data로 기록합니다.</small>
        </div>
      )}
    </section>
  );
}

function display(value: unknown) {
  if (value === null || value === undefined || value === "") return "missing_data";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function resultLabel(result: Assertion["result"]) {
  const labels = {
    MATCH: "기술 일치",
    MISMATCH: "불일치",
    MISSING_DATA: "missing_data",
    REVIEW_REQUIRED: "기술 일치 · 검토",
  };
  return labels[result];
}

function technicalStatusLabel(status: string) {
  const labels: Record<string, string> = {
    TECHNICALLY_MATCHED: "기술 일치 관측",
    TECHNICAL_MISMATCH: "기술 불일치 관측",
    PARTIAL: "부분 증적",
    BLOCKED: "기술 진행 불가",
  };
  return labels[status] || status;
}

function fileName(path: string) {
  return path.split("/").pop() || path;
}

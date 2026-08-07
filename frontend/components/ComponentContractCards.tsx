"use client";

type Locator = {
  strategy?: string;
  value?: string;
  name?: string | null;
  stable?: boolean;
};

type InputContract = {
  field: string;
  logicalName?: string;
  required?: boolean;
  type?: string;
  pattern?: string | null;
  locator?: Locator;
  events?: string[];
  recommendationReady?: boolean;
  reviewRequired?: boolean;
  semanticType?: string | null;
};

type OutputContract = {
  field: string;
  responsePath: string;
  uiLocator?: Locator;
  normalize?: string[];
  assertion?: string | null;
  reviewRequired?: boolean;
};

type Warning = {
  kind: string;
  field?: string | null;
  message: string;
};

export type ComponentContractResult = {
  contractId?: string;
  inputs?: InputContract[];
  outputs?: OutputContract[];
  actions?: Array<{ logicalName?: string; events?: string[]; locator?: Locator }>;
  validationMismatches?: Array<Record<string, unknown>>;
  warnings?: Warning[];
  screenshotHooks?: {
    points?: Array<{ id: string; when: string; screen?: string }>;
    maskRegions?: Array<{ id: string; reason: string }>;
  };
};

export function ComponentContractCards({
  contract,
  busy,
  onBuild,
}: {
  contract: ComponentContractResult | null;
  busy?: boolean;
  onBuild: () => void;
}) {
  if (!contract) {
    return (
      <div className="contract-block" data-testid="component-contract-empty">
        <p className="panel-kicker">COMPONENT CONTRACT</p>
        <p className="muted">A/B 입력·Locator·바인딩 계약이 아직 없습니다.</p>
        <button type="button" className="button subtle" disabled={busy} onClick={onBuild}>
          {busy ? "Building…" : "Build contract"}
        </button>
      </div>
    );
  }

  const warnings = contract.warnings ?? [];
  const mismatches = contract.validationMismatches ?? [];
  const inputs = (contract.inputs ?? []).filter((i) => i.required || i.reviewRequired || i.field === "customerId");
  const shownInputs = inputs.length ? inputs : (contract.inputs ?? []).slice(0, 3);

  return (
    <div className="contract-block" data-testid="component-contract-cards">
      <div className="contract-head">
        <p className="panel-kicker">COMPONENT CONTRACT</p>
        <button type="button" className="ghost-btn" disabled={busy} onClick={onBuild}>
          Rebuild
        </button>
      </div>
      <p className="mono-cell muted">{contract.contractId}</p>

      <section className="contract-card" data-testid="contract-card-a">
        <h4>A · Inputs</h4>
        {shownInputs.map((inp) => (
          <div key={inp.field} className="contract-row">
            <strong>{inp.logicalName || inp.field}</strong>
            <span>{inp.required ? "required" : "optional"}</span>
            <span className="muted">{inp.pattern || inp.type || "—"}</span>
            <span className="mono-cell">
              {inp.locator?.strategy}:{inp.locator?.value}
              {inp.locator?.stable === false ? " ⚠" : ""}
            </span>
            <span>{(inp.events ?? []).join(", ") || "—"}</span>
            <span className="muted">
              추천값 {inp.recommendationReady ? "ready" : "pending (Phase 08)"}
            </span>
          </div>
        ))}
        {(contract.actions ?? []).slice(0, 2).map((act, i) => (
          <div key={i} className="contract-row">
            <strong>{act.logicalName || "action"}</strong>
            <span>action</span>
            <span className="mono-cell">
              {act.locator?.strategy}:{act.locator?.value}
            </span>
            <span>{(act.events ?? []).join(", ")}</span>
          </div>
        ))}
      </section>

      <section className="contract-card" data-testid="contract-card-b">
        <h4>B · Bindings</h4>
        {(contract.outputs ?? []).map((out) => (
          <div key={out.field} className="contract-row">
            <strong>{out.field}</strong>
            <span className="mono-cell">{out.responsePath}</span>
            <span className="mono-cell">
              {out.uiLocator?.strategy}:{out.uiLocator?.value}
            </span>
            <span className="muted">{(out.normalize ?? []).join("|") || "—"}</span>
            <span className="muted">{out.assertion || "binding"}</span>
          </div>
        ))}
      </section>

      {(warnings.length > 0 || mismatches.length > 0) && (
        <section className="contract-warn" data-testid="contract-warnings">
          <strong>Warnings</strong>
          <ul>
            {warnings.slice(0, 6).map((w, i) => (
              <li key={i}>
                {w.kind}
                {w.field ? ` · ${w.field}` : ""}: {w.message}
              </li>
            ))}
            {mismatches.slice(0, 4).map((m, i) => (
              <li key={`m-${i}`}>validation_mismatch: {String(m.message || m.field || "diff")}</li>
            ))}
          </ul>
        </section>
      )}

      <p className="muted" style={{ marginTop: 8, fontSize: 11 }}>
        Screenshot preview는 실행(Phase 09) 후 채워집니다. mask={" "}
        {(contract.screenshotHooks?.maskRegions ?? []).length} regions.
      </p>
    </div>
  );
}

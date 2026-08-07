"use client";

type Rec = {
  field: string;
  value?: unknown;
  displayValue?: string | null;
  category: string;
  expectedPath?: string | null;
  rationale?: string;
  selectedByDefault?: boolean;
  reviewRequired?: boolean;
  uncertain?: boolean;
  sources?: Array<{ source?: string; rank?: number; ref?: string | null }>;
};

type Profile = {
  profileId: string;
  name: string;
  status: string;
  version: string;
  caseCount: number;
  categoryCounts?: Record<string, number>;
  result?: {
    policy?: { budget?: number; unresolvedPolicy?: string; excludeDestructive?: boolean };
    cases?: Array<{ caseId: string; category: string; inputs: Record<string, unknown> }>;
  };
};

export function InputRecommendPanel({
  recommendations,
  defaults,
  profiles,
  busy,
  onRecommend,
  onCreateProfile,
  onApprove,
}: {
  recommendations: Rec[] | null;
  defaults: Record<string, unknown> | null;
  profiles: Profile[];
  busy?: boolean;
  onRecommend: () => void;
  onCreateProfile: () => void;
  onApprove: (profileId: string) => void;
}) {
  const byCategory = (recommendations ?? []).reduce<Record<string, Rec[]>>((acc, r) => {
    (acc[r.category] ||= []).push(r);
    return acc;
  }, {});

  return (
    <div className="recommend-block" data-testid="input-recommend-panel">
      <div className="contract-head">
        <p className="panel-kicker">INPUT RECOMMEND</p>
        <button type="button" className="ghost-btn" disabled={busy} onClick={onRecommend}>
          {busy ? "…" : "Recommend"}
        </button>
      </div>

      {!recommendations?.length ? (
        <p className="muted">건별 기본 추천값이 없습니다. Recommend를 실행하세요.</p>
      ) : (
        <>
          <section className="contract-card" data-testid="recommend-defaults">
            <h4>건별 기본값</h4>
            {Object.entries(defaults || {}).map(([k, v]) => (
              <div key={k} className="contract-row">
                <strong>{k}</strong>
                <span className="mono-cell">{String(v === "" ? "(empty)" : v)}</span>
                <span className="muted">auto-selected</span>
              </div>
            ))}
          </section>

          <section className="contract-card" data-testid="recommend-categories">
            <h4>카테고리 추천</h4>
            {Object.entries(byCategory).map(([cat, rows]) => {
              const top = rows[0];
              return (
                <div
                  key={cat}
                  className={`contract-row ${top.uncertain || top.reviewRequired ? "is-uncertain" : ""}`}
                >
                  <strong>{cat}</strong>
                  <span className="mono-cell">
                    {top.displayValue ?? String(top.value === "" ? "(empty)" : top.value)}
                  </span>
                  <span className="muted">{top.expectedPath || "—"}</span>
                  <span className="muted">
                    {(top.sources || []).map((s) => s.source).filter(Boolean).slice(0, 2).join(" · ")}
                  </span>
                  <span className="muted">{top.rationale}</span>
                </div>
              );
            })}
          </section>
        </>
      )}

      <section className="contract-card" data-testid="input-profiles">
        <div className="contract-head">
          <h4 style={{ margin: 0 }}>배치 Input Profile</h4>
          <button type="button" className="ghost-btn" disabled={busy} onClick={onCreateProfile}>
            Create profile
          </button>
        </div>
        {profiles.length === 0 && <p className="muted">승인용 Profile이 없습니다.</p>}
        {profiles.map((p) => (
          <div key={p.profileId} className="contract-row">
            <strong>{p.name}</strong>
            <span className={`status-badge status-${p.status === "APPROVED" ? "success" : "info"}`}>
              {p.status}
            </span>
            <span className="muted">
              v{p.version} · cases {p.caseCount}
              {p.result?.policy?.budget != null ? ` · budget ${p.result.policy.budget}` : ""}
            </span>
            <span className="muted">
              {Object.entries(p.categoryCounts || {})
                .map(([k, v]) => `${k}:${v}`)
                .join(" · ") || "—"}
            </span>
            {p.result?.policy?.excludeDestructive !== false && (
              <span className="muted">destructive 제외</span>
            )}
            {p.status !== "APPROVED" && (
              <button
                type="button"
                className="button subtle"
                disabled={busy}
                onClick={() => onApprove(p.profileId)}
              >
                Approve
              </button>
            )}
          </div>
        ))}
      </section>
    </div>
  );
}

"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Breadcrumbs } from "../../../components/Breadcrumbs";
import { PageShell, PageStickyFooter } from "../../../components/PageShell";
import { ProgressBarType2 } from "../../../components/ProgressBar";
import { ScenarioDetailPanel } from "../../../components/scenarios/ScenarioDetailPanel";
import { journeySteps } from "../../../lib/nav";

const API = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://127.0.0.1:8000";

/** 여정 Type 2 — 건별 테스트 화면에서는 마지막 `테스트실행` 스텝을 강조한다. */
const journey = journeySteps.map((label, idx) => ({
  label,
  status: idx < journeySteps.length - 1 ? ("complete" as const) : ("progressing" as const),
}));

/**
 * 시나리오 단독(딥링크) 화면.
 *
 * 평소 여정은 「테스트 시나리오」 목록의 우측 슬라이드 패널에서 진행하고,
 * 이 화면은 링크·북마크로 한 건만 열었을 때의 폴백이다. 상세 재료는 동일 패널을 쓴다.
 */
export default function ScenarioDetailPage() {
  const params = useParams<{ scenarioId: string }>();
  const scenarioId = params.scenarioId;
  const [setId, setSetId] = useState<string | null>(null);
  const [repositoryName, setRepositoryName] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch(`${API}/api/scenarios/${scenarioId}`, { cache: "no-store" });
        if (!res.ok) return;
        const data = (await res.json()) as Record<string, any>;
        const graphId = data?.graphId || data?.result?.sourceRefs?.graphId;
        if (!graphId) return;
        setSetId(String(graphId));
        const setRes = await fetch(`${API}/api/console/scenario-sets`, { cache: "no-store" });
        if (!setRes.ok) return;
        const sets = (await setRes.json()) as Array<{ setId: string; repositoryName: string }>;
        setRepositoryName(sets.find((s) => s.setId === graphId)?.repositoryName ?? null);
      } catch {
        // 딥링크 폴백 화면 — 그룹 정보가 없어도 상세는 읽을 수 있다
      }
    })();
  }, [scenarioId]);

  const groupHref = setId ? `/scenarios?setId=${encodeURIComponent(setId)}` : "/scenarios";
  const graphHref = setId
    ? `/scenarios?setId=${encodeURIComponent(setId)}&scenarioId=${encodeURIComponent(
        scenarioId,
      )}&view=graph`
    : null;

  return (
    <PageShell
      header={
        <div className="content-header">
          <div>
            <Breadcrumbs
              trail={[
                { label: "콘솔", href: "/" },
                { label: "테스트 시나리오", href: "/scenarios" },
                {
                  label: `${repositoryName ?? "연결 저장소"} 테스트 시나리오 그룹`,
                  href: groupHref,
                },
                { label: "건별 테스트" },
              ]}
            />
            <h2>건별 테스트</h2>
            <p className="muted" style={{ marginTop: 6 }}>
              링크로 열린 단건 화면입니다. 목록과 함께 보려면 그룹 화면으로 이동하세요.
            </p>
          </div>
          <ProgressBarType2 steps={journey} testId="scenario-journey-type2" />
        </div>
      }
      footer={
        <PageStickyFooter
          testId="scenario-detail-footer"
          note="관측·증적만 제공합니다. Pass/Fail는 HITL입니다."
          actions={
            <Link className="ghost-btn" href={groupHref}>
              목록과 함께 보기
            </Link>
          }
        />
      }
    >
      <ScenarioDetailPanel scenarioId={scenarioId} graphHref={graphHref} />
    </PageShell>
  );
}

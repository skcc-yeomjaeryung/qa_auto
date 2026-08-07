import { Suspense } from "react";
import { ScenarioSetWorkbench } from "../../components/scenarios/ScenarioSetWorkbench";

export default function ScenariosPage() {
  return (
    <Suspense
      fallback={
        <section className="table-workspace">
          <div className="content-card">테스트 시나리오 불러오는 중…</div>
        </section>
      }
    >
      <ScenarioSetWorkbench />
    </Suspense>
  );
}

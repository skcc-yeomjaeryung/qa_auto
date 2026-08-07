import { Suspense } from "react";
import { AnalysisWorkbench } from "../../components/AnalysisWorkbench";

export default function AnalysisPage() {
  return (
    <Suspense
      fallback={
        <section className="table-workspace">
          <div className="content-card">분석 목록 불러오는 중…</div>
        </section>
      }
    >
      <AnalysisWorkbench />
    </Suspense>
  );
}

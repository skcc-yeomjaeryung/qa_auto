import { Suspense } from "react";
import { ProjectsWorkbench } from "../../components/ProjectsWorkbench";

export default function ProjectsPage() {
  return (
    <Suspense fallback={<p className="muted" style={{ padding: 12 }}>프로젝트 화면 준비 중…</p>}>
      <ProjectsWorkbench />
    </Suspense>
  );
}

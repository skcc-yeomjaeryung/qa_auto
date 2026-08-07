import { scenarioTitleKo } from "./scenarioLabels";

export type ContextProject = { id: string; name: string };
export type ContextScenario = {
  scenarioId: string;
  projectId?: string | null;
  graphId?: string | null;
  serviceId?: string;
  name?: string;
  businessPath?: string[];
  result?: Record<string, unknown> | null;
};
export type ContextScenarioSet = {
  setId: string;
  graphId?: string | null;
  projectId?: string | null;
  projectName?: string | null;
  repositoryName?: string | null;
};

export type ScenarioRunContext = {
  scenarioId: string;
  scenarioName: string;
  projectId: string;
  projectName: string;
  groupId: string;
  groupName: string;
  businessGroupName: string;
};

export function buildScenarioRunContexts(
  projects: ContextProject[],
  scenarios: ContextScenario[],
  scenarioSets: ContextScenarioSet[],
): Map<string, ScenarioRunContext> {
  const projectById = new Map(projects.map((project) => [project.id, project]));
  const setById = new Map(
    scenarioSets.flatMap((group) => {
      const keys = [group.setId, group.graphId].filter(Boolean) as string[];
      return keys.map((key) => [key, group] as const);
    }),
  );
  const contexts = new Map<string, ScenarioRunContext>();
  for (const scenario of scenarios) {
    const projectId = String(scenario.projectId || "unassigned");
    const project = projectById.get(projectId);
    const graphId = String(
      scenario.graphId ||
        ((scenario.result?.sourceRefs as Record<string, unknown> | undefined)?.graphId ?? "") ||
        `${projectId}:unlinked`,
    );
    const group = setById.get(graphId);
    const projectName = project?.name || group?.projectName || projectId;
    const repositoryName = group?.repositoryName || "테스트 시나리오";
    const businessPath = scenario.businessPath || [];
    contexts.set(scenario.scenarioId, {
      scenarioId: scenario.scenarioId,
      scenarioName: scenarioTitleKo({
        name: scenario.name,
        serviceId: scenario.serviceId,
        result: scenario.result as never,
      }),
      projectId,
      projectName,
      groupId: graphId,
      groupName: `${projectName} · ${repositoryName} 그룹`,
      businessGroupName: businessPath.slice(0, 2).filter(Boolean).join(" › ") || "업무 분류 미지정",
    });
  }
  return contexts;
}

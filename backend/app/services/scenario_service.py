from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from app.agents.platform_runner.adapter import PlatformRunnerAdapter
from app.core.paths import ARTIFACTS_ANALYSIS, REPO_ROOT
from app.services.repository_models import utc_now
from app.services.repository_store import InMemoryPlatformStore
from app.services.project_context_service import ProjectContextService
from app.services.run_service import BrowserRunService
from app.services.runtime_scenario_discovery import discover_runtime_screens
from app.services.scenario_models import (
    ScenarioCreateRequest,
    ScenarioScopedGraph,
    ScenarioSummary,
)
from app.skills.scenario_dsl.script.generate_dsl import dedupe_scenarios, generate_scenarios

logger = logging.getLogger(__name__)


def _scenario_step_flow(
    steps: list[dict], source_nodes: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Turn evidenced Scenario DSL actions into an ordered, readable user flow."""
    by_id = {str(node.get("id")): node for node in source_nodes if node.get("id")}
    screen_by_route = {
        str((node.get("attributes") or {}).get("route")): node
        for node in source_nodes
        if node.get("type") == "screen" and (node.get("attributes") or {}).get("route")
    }
    nodes: list[dict] = []
    edges: list[dict] = []
    current_screen: dict | None = None
    previous_id: str | None = None

    for index, step in enumerate(steps, start=1):
        step_id = str(step.get("id") or f"S{index}")
        action = str(step.get("action") or "step")
        target = step.get("target") if isinstance(step.get("target"), dict) else {}
        request = step.get("request") if isinstance(step.get("request"), dict) else {}
        refs = [
            ref[len("graph:") :]
            for ref in (step.get("evidenceRefs") or [])
            if isinstance(ref, str) and ref.startswith("graph:")
        ]
        source = next((by_id.get(ref) for ref in refs if by_id.get(ref)), None)
        route = str(target.get("route") or "")
        if action == "navigate" and route:
            current_screen = screen_by_route.get(route) or source
        if source is None and action in {"fill", "click", "assert_visible", "assert_absent"}:
            source = current_screen

        node_id = f"scenario-step-{step_id.lower()}"
        node_type = {
            "navigate": "screen",
            "fill": "input",
            "click": "event",
            "wait_for_response": "frontend_api_call",
            "verify_navigation": "screen",
            "verify_binding": "binding",
            "assert_visible": "validation",
            "assert_absent": "validation",
        }.get(action, "event")
        source_attrs = dict((source or {}).get("attributes") or {})
        attributes = {
            **source_attrs,
            "scenarioStepId": step_id,
            "action": action,
            "route": route or source_attrs.get("route"),
            "target": target,
            "request": request,
            "valueFrom": step.get("valueFrom") or step.get("valueRef"),
            "valueStrategy": step.get("valueStrategy"),
            "captureAs": step.get("captureAs"),
            "expect": step.get("expect") if isinstance(step.get("expect"), dict) else {},
            "criterionId": step.get("criterionId"),
            "destructive": bool(step.get("destructive")),
            "evidenceRefs": list(step.get("evidenceRefs") or []),
            "sourceNodeId": (source or {}).get("id"),
        }
        nodes.append(
            {
                "id": node_id,
                "type": node_type,
                "name": _scenario_step_name(step, index),
                "attributes": attributes,
                "evidence": list((source or {}).get("evidence") or []),
                "confidence": float((source or {}).get("confidence") or 0.7),
                "verificationStatus": "scenario-evidenced" if source else "scenario-defined",
            }
        )
        if previous_id:
            edges.append(
                {
                    "id": f"edge-{previous_id}-{node_id}",
                    "from": previous_id,
                    "to": node_id,
                    "type": {
                        "navigate": "navigates_to",
                        "wait_for_response": "calls",
                        "assert_visible": "asserts",
                        "assert_absent": "asserts",
                    }.get(action, "triggers"),
                    "condition": "happy_path",
                    "confidence": float((source or {}).get("confidence") or 0.7),
                    "evidence": list((source or {}).get("evidence") or []),
                }
            )
        previous_id = node_id
    return nodes, edges


def _scenario_step_name(step: dict, index: int) -> str:
    title = str(step.get("title") or "").strip()
    if title:
        return title
    action = str(step.get("action") or "")
    target = step.get("target") if isinstance(step.get("target"), dict) else {}
    request = step.get("request") if isinstance(step.get("request"), dict) else {}
    labels = {
        "navigate": f"{target.get('route') or '대상'} 화면 열기",
        "fill": f"{target.get('value') or target.get('selector') or '화면'} 값 입력",
        "click": f"{target.get('value') or target.get('selector') or '버튼'} 클릭",
        "wait_for_response": f"{request.get('method') or ''} {request.get('path') or ''} 서버 응답 확인".strip(),
        "verify_navigation": f"{(step.get('expect') or {}).get('routePattern') or '다음'} 화면 도착 확인",
        "assert_visible": "화면 구성 표시 확인",
        "assert_absent": "화면 요소 제거 확인",
        "verify_binding": "응답값 화면 반영 확인",
        "assert_invalid": "입력 제약 거부 확인",
    }
    return labels.get(action) or f"{index}. {action or '시나리오 단계'}"


class ScenarioService:
    def __init__(self, store: InMemoryPlatformStore) -> None:
        self.store = store

    def create_from_graph(
        self, graph_id: str, payload: ScenarioCreateRequest | None = None
    ) -> list[ScenarioSummary]:
        payload = payload or ScenarioCreateRequest()
        graph = self.store.get_graph(graph_id)
        if not graph or not graph.result:
            raise LookupError(f"graph not found: {graph_id}")

        out_dir = ARTIFACTS_ANALYSIS / graph_id / "scenarios"
        out_file = out_dir / "scenarios.json"
        out_dir.mkdir(parents=True, exist_ok=True)

        project = self.store.get_project(graph.projectId) if graph.projectId else None
        envs = self.store.list_environments(graph.projectId) if graph.projectId else []
        active_env = next((e for e in envs if e.status.value == "active"), envs[0] if envs else None)
        execution_environment = None
        runtime_discovery: dict = {
            "status": "missing_data",
            "reason": "active execution environment missing",
            "pages": [],
        }
        if active_env:
            account_roles = sorted(
                {
                    account.role
                    for account in self.store.list_execution_accounts(active_env.id)
                    if account.role
                }
            )
            execution_environment = {
                "id": active_env.id,
                "name": active_env.name,
                "frontendBaseUrl": active_env.frontendBaseUrl,
                "backendBaseUrl": active_env.backendBaseUrl,
                "lastHealthStatus": active_env.lastHealthStatus.value
                if hasattr(active_env.lastHealthStatus, "value")
                else str(active_env.lastHealthStatus),
                # LLM에는 권한명과 계정 등록 여부만 전달한다. ID/PASSWORD는 전달 금지.
                "accountRoles": account_roles,
                "hasRegisteredAccount": bool(account_roles),
            }

            try:
                connection = BrowserRunService(self.store)._connection(active_env)
                runtime_discovery = discover_runtime_screens(
                    graph_id=graph_id,
                    graph=dict(graph.result or {}),
                    base_url=active_env.frontendBaseUrl,
                    connection=connection,
                    artifact_dir=ARTIFACTS_ANALYSIS / graph_id / "runtime-discovery",
                )
            except Exception as exc:  # noqa: BLE001 — 정적 분석 생성은 계속 가능해야 한다
                logger.warning("runtime scenario discovery failed graph=%s: %s", graph_id, exc)
                runtime_discovery = {
                    "status": "partial",
                    "reason": str(exc),
                    "pages": [],
                    "missingData": ["runtime_screen_discovery"],
                }

        generation_graph = {
            **dict(graph.result or {}),
            "graphId": graph.graphId,
            "version": graph.version,
            "commitRefs": dict(graph.commitRefs or {}),
            "runtimeDiscovery": runtime_discovery,
        }
        scenario_context_query = " ".join(
            str(value or "")
            for value in [
                payload.serviceId,
                project.name if project else None,
                *[
                    node.get("name")
                    for node in (generation_graph.get("nodes") or [])[:300]
                    if isinstance(node, dict)
                ],
            ]
        )[:12000]
        context_service = ProjectContextService()

        response = PlatformRunnerAdapter().execute(
            "wf_scenario_dsl",
            {
                "projectId": graph.projectId,
                "serviceId": payload.serviceId,
                "interactionGraph": generation_graph,
                "interactionGraphPath": graph.artifactPath,
                "artifactPath": str(out_file.resolve()),
                "projectContextManifestPath": str(context_service.manifest_path(graph.projectId or "unassigned")),
                "scenarioContextQuery": scenario_context_query,
                "projectContext": {
                    "projectId": graph.projectId,
                    "projectName": project.name if project else None,
                    "serviceId": payload.serviceId,
                },
                "executionEnvironment": execution_environment,
            },
        )
        if response.status != "complete" or not response.stepResults:
            raise RuntimeError(response.summary or "scenario workflow failed")
        # Prefer last successful step (narrate); fallback to DSL seed step.
        output: dict = {}
        for step in reversed(response.stepResults):
            candidate = step.get("output") or {}
            if candidate.get("ok") and (candidate.get("result") or {}).get("scenarios"):
                output = candidate
                break
        if not output:
            output = response.stepResults[-1].get("output") or {}
        if not output.get("ok"):
            raise RuntimeError("scenario workflow skill output missing ok=true")

        scenarios = (output.get("result") or {}).get("scenarios") or []
        # 커버리지에 기여하지 않는 중복 케이스는 근거 기반 규칙으로만 정리한다.
        # 프로젝트 선택 모델 호출은 wf_scenario_dsl 안에서만 수행해야 Agent Trace와
        # 사용량 영수증이 일치한다. 전역 기본 모델을 이 저장 단계에서 다시 호출하지 않는다.
        scenarios = dedupe_scenarios(scenarios)
        # 생성기가 서로 다른 근거 경로에 같은 caseId를 부여한 경우 저장 단계에서
        # 같은 scenarioId를 두 번 반환하지 않는다. 더 많은 단계·근거를 가진 후보를 보존한다.
        unique_by_case: dict[str, dict] = {}
        without_case: list[dict] = []
        for scenario in scenarios:
            case_id = str(scenario.get("caseId") or "")
            if not case_id:
                without_case.append(scenario)
                continue
            current = unique_by_case.get(case_id)
            score = (
                len(scenario.get("steps") or []),
                len(scenario.get("evidenceIndex") or []),
                len(str(scenario.get("name") or "")),
            )
            current_score = (
                len((current or {}).get("steps") or []),
                len((current or {}).get("evidenceIndex") or []),
                len(str((current or {}).get("name") or "")),
            )
            if current is None or score > current_score:
                unique_by_case[case_id] = scenario
        scenarios = [*unique_by_case.values(), *without_case]
        hierarchy: dict[str, dict] = {}
        existing_by_case: dict[str, ScenarioSummary] = {}
        for existing in self.store.list_scenarios(graph.projectId):
            existing_case = str((existing.result or {}).get("caseId") or "")
            # 같은 프로젝트·caseId 재생성은 새 행을 쌓지 않고 최신 초안을 갱신한다.
            # Graph ID는 최신 근거로 교체되며, 과거 Graph artifact는 그대로 보존된다.
            if existing_case:
                current = existing_by_case.get(existing_case)
                if current is None or str(existing.createdAt or "") > str(current.createdAt or ""):
                    existing_by_case[existing_case] = existing
        saved: list[ScenarioSummary] = []
        for scn in scenarios:
            classification = hierarchy.get(str(scn.get("scenarioId"))) or self._fallback_business_path(scn)
            scn["businessHierarchy"] = {
                "path": classification["path"],
                "assignedRole": classification["assignedRole"],
                "source": classification["source"],
            }
            scn["accountRoleEvidence"] = {
                "availableRoles": (execution_environment or {}).get("accountRoles") or [],
                "credentialValuesExcluded": True,
            }
            case_id = str(scn.get("caseId") or "")
            previous = existing_by_case.get(case_id) if case_id else None
            scenario_id = previous.scenarioId if previous else scn.get("scenarioId") or f"SCN-{uuid4().hex[:8]}"
            scn["scenarioId"] = scenario_id
            summary = ScenarioSummary(
                scenarioId=scenario_id,
                serviceId=scn.get("serviceId") or payload.serviceId,
                projectId=graph.projectId,
                graphId=graph_id,
                name=scn.get("name") or scn.get("serviceLabelKo") or "",
                version=str(scn.get("version") or "1"),
                status=scn.get("status") or "DRAFT",
                artifactPath=output.get("artifactPath") or str(out_file),
                unresolvedCount=len(scn.get("unresolved") or []),
                createdAt=scn.get("generatedAt") or utc_now().isoformat(),
                businessPath=classification["path"],
                assignedRole=classification["assignedRole"],
                result=scn,
            )
            saved.append(self.store.save_scenario(summary))
        return saved

    @staticmethod
    def _fallback_business_path(scenario: dict) -> dict:
        name = str(scenario.get("name") or scenario.get("scenarioId") or "시나리오")
        evidence = " ".join(
            str(value or "")
            for value in [
                name,
                scenario.get("serviceId"),
                (scenario.get("source") or {}).get("route"),
                (scenario.get("request") or {}).get("path"),
            ]
        ).lower()
        if any(token in evidence for token in ("login", "auth", "signin", "로그인", "인증")):
            levels = ["인증·접근", "로그인 담당", name]
        elif any(token in evidence for token in ("deposit", "입금")):
            levels = ["금융 거래", "입금 담당", name]
        elif any(token in evidence for token in ("payment", "transfer", "결제", "이체", "송금")):
            levels = ["금융 거래", "송금 담당", name]
        elif any(token in evidence for token in ("query", "search", "list", "detail", "조회", "customer")):
            levels = ["고객 업무", "조회 담당", name]
        else:
            levels = ["공통 업무", "기타 담당", name]
        return {"path": levels, "assignedRole": levels[1], "source": "deterministic_code_evidence"}

    def list_scenarios(
        self, project_id: str | None = None, service_id: str | None = None
    ) -> list[ScenarioSummary]:
        stored = list(self.store.list_scenarios(project_id=project_id, service_id=service_id))
        # Historical repeated generation created a new Graph and UUID for the same
        # project/case on every retry. Keep old IDs addressable, but show only the
        # latest project-level revision in Console lists and dashboard counts.
        latest: dict[str, ScenarioSummary] = {}
        for row in stored:
            case_id = str((row.result or {}).get("caseId") or "") if isinstance(row.result, dict) else ""
            key = f"{row.projectId or 'unlinked'}::{case_id or row.scenarioId}"
            current = latest.get(key)
            if current is None or str(row.createdAt or "") > str(current.createdAt or ""):
                latest[key] = row
        rows = list(latest.values())
        enriched: list[ScenarioSummary] = []
        for row in rows:
            classification = self._fallback_business_path(
                {**dict(row.result or {}), "scenarioId": row.scenarioId, "name": row.name, "serviceId": row.serviceId}
            )
            generic_path = list(row.businessPath or [])[:2] == ["공통 업무", "기타 담당"]
            if row.businessPath and not generic_path:
                enriched.append(row)
                continue
            # Historical generators put payment in common work. Reclassify only
            # generic paths so explicit/user classifications remain untouched.
            enriched.append(
                row.model_copy(
                    update={
                        "businessPath": classification["path"],
                        "assignedRole": classification["assignedRole"],
                    }
                )
            )
        return enriched

    def get(self, scenario_id: str) -> ScenarioSummary | None:
        return self.store.get_scenario(scenario_id)

    def delete(self, scenario_id: str) -> bool:
        return self.store.delete_scenario(scenario_id)

    def delete_many(self, scenario_ids: list[str]) -> dict:
        if not scenario_ids:
            raise ValueError("scenarioIds required")
        removed = self.store.delete_scenarios(scenario_ids)
        return {
            "status": "complete" if removed == len(scenario_ids) else "partial",
            "removed": removed,
            "requested": len(scenario_ids),
            "message": f"시나리오 {removed}건을 삭제했습니다.",
        }

    def scoped_graph(self, scenario_id: str) -> ScenarioScopedGraph:
        """시나리오 한 건의 의존관계 그래프(부분집합)를 만든다.

        근거는 시나리오 DSL에 이미 기록된 것만 쓴다.
        - `steps[].evidenceRefs` 의 `graph:<nodeId>`
        - `evidenceIndex[].nodeId`

        seed 노드와 그 1-hop 이웃만 남기고, 양 끝이 모두 남은 엣지만 유지한다.
        seed가 없으면 노드를 추정해 채우지 않고 `missingData`로 알린다.
        """
        scenario = self.store.get_scenario(scenario_id)
        if not scenario:
            raise LookupError(f"scenario not found: {scenario_id}")
        result = dict(scenario.result or {})
        graph_id = scenario.graphId or (result.get("sourceRefs") or {}).get("graphId")
        graph = self.store.get_graph(str(graph_id)) if graph_id else None
        if not graph_id or not graph or not graph.result:
            # 근거가 되는 그래프를 찾을 수 없으면 노드를 추정해 채우지 않는다
            reason = "scenario_graph_link" if not graph_id else "source_graph"
            logger.info(
                "scenario scoped graph unavailable scenario=%s graph=%s reason=%s",
                scenario_id,
                graph_id,
                reason,
            )
            return ScenarioScopedGraph(
                graphId=f"{graph_id or 'unlinked'}::{scenario_id}",
                projectId=scenario.projectId,
                serviceId=scenario.serviceId,
                status="missing_data",
                unresolvedCount=scenario.unresolvedCount,
                result={"nodes": [], "edges": []},
                scopedScenarioId=scenario_id,
                scopedScenarioName=scenario.name or str(result.get("name") or ""),
                sourceGraphId=str(graph_id) if graph_id else None,
                missingData=[reason],
            )

        nodes = [n for n in (graph.result.get("nodes") or []) if isinstance(n, dict)]
        edges = [e for e in (graph.result.get("edges") or []) if isinstance(e, dict)]
        node_ids = {str(n.get("id")) for n in nodes if n.get("id")}

        scenario_steps = [step for step in (result.get("steps") or []) if isinstance(step, dict)]
        seeds: set[str] = set()
        for step in scenario_steps:
            if not isinstance(step, dict):
                continue
            for ref in step.get("evidenceRefs") or []:
                if isinstance(ref, str) and ref.startswith("graph:"):
                    candidate = ref[len("graph:") :]
                    if candidate in node_ids:
                        seeds.add(candidate)
        for item in result.get("evidenceIndex") or []:
            if isinstance(item, dict):
                candidate = str(item.get("nodeId") or "")
                if candidate in node_ids:
                    seeds.add(candidate)

        has_executable_steps = any(str(step.get("action") or "") for step in scenario_steps)
        if has_executable_steps:
            # User flow is the executable scenario, not a coarse one-hop source graph.
            # Each DSL action becomes a visible fragment while keeping the referenced
            # source node's evidence and confidence.
            scoped_nodes, scoped_edges = _scenario_step_flow(scenario_steps, nodes)
            primary_path = [str(node.get("id")) for node in scoped_nodes]
            branches = [{"id": "happy_path", "label": "정상 경로", "condition": "happy_path"}]
            missing_data = [
                f"scenario_step_evidence:{step.get('id') or index + 1}"
                for index, step in enumerate(scenario_steps)
                if not any(
                    isinstance(ref, str) and ref.startswith("graph:")
                    for ref in (step.get("evidenceRefs") or [])
                )
            ]
        else:
            scoped: set[str] = set(seeds)
            for edge in edges:
                source = str(edge.get("from") or "")
                target = str(edge.get("to") or "")
                if source in seeds and target in node_ids:
                    scoped.add(target)
                if target in seeds and source in node_ids:
                    scoped.add(source)

            scoped_nodes = [n for n in nodes if str(n.get("id")) in scoped]
            scoped_edges = [
                e
                for e in edges
                if str(e.get("from") or "") in scoped and str(e.get("to") or "") in scoped
            ]
            scoped_conditions = {
                str(e.get("condition") or "happy_path") for e in scoped_edges
            }
            branches = [
                b
                for b in (graph.branches or [])
                if str((b or {}).get("condition") or "happy_path") in scoped_conditions
            ]
            primary_path = [nid for nid in (graph.primaryPath or []) if nid in scoped]
            missing_data = [] if seeds else ["scenario_graph_refs"]
        scoped_result = {
            "nodes": scoped_nodes,
            "edges": scoped_edges,
            "figmaRef": graph.result.get("figmaRef") or {},
            "scopedFrom": {"graphId": str(graph_id), "scenarioId": scenario_id},
        }
        logger.info(
            "scenario scoped graph scenario=%s graph=%s seeds=%s nodes=%s edges=%s",
            scenario_id,
            graph_id,
            len(seeds),
            len(scoped_nodes),
            len(scoped_edges),
        )
        return ScenarioScopedGraph(
            graphId=f"{graph_id}::{scenario_id}",
            projectId=graph.projectId,
            repositorySetId=graph.repositorySetId,
            frontendAnalysisId=graph.frontendAnalysisId,
            backendAnalysisId=graph.backendAnalysisId,
            mappingSetId=graph.mappingSetId,
            serviceId=scenario.serviceId or graph.serviceId,
            status=graph.status,
            artifactPath=graph.artifactPath,
            version=graph.version,
            commitRefs=graph.commitRefs,
            nodeCount=len(scoped_nodes),
            edgeCount=len(scoped_edges),
            primaryPath=primary_path,
            branches=branches,
            unresolvedCount=scenario.unresolvedCount,
            createdAt=graph.createdAt,
            result=scoped_result,
            scopedScenarioId=scenario_id,
            scopedScenarioName=scenario.name or str(result.get("name") or ""),
            sourceGraphId=str(graph_id),
            seedNodeIds=sorted(seeds),
            missingData=missing_data,
        )

    def validate(self, scenario_id: str) -> dict:
        item = self.store.get_scenario(scenario_id)
        if not item:
            raise LookupError(f"scenario not found: {scenario_id}")
        schema_path = (
            REPO_ROOT / "packages" / "contracts" / "schemas" / "scenario_dsl.schema.json"
        )
        from jsonschema import Draft202012Validator

        schema = __import__("json").loads(schema_path.read_text(encoding="utf-8"))
        # serviceId is additive; strip before strict validate if needed
        body = dict(item.result or {})
        body.pop("serviceId", None)
        body.pop("projectId", None)
        body.pop("unresolved", None)
        body.pop("evidenceIndex", None)
        body.pop("generatedAt", None)
        Draft202012Validator(schema).validate(body)
        return {"scenarioId": scenario_id, "valid": True}

    def add_version(self, scenario_id: str) -> ScenarioSummary:
        item = self.store.get_scenario(scenario_id)
        if not item:
            raise LookupError(f"scenario not found: {scenario_id}")
        try:
            ver = int(item.version)
        except ValueError:
            ver = 1
        next_ver = str(ver + 1)
        result = dict(item.result or {})
        result["version"] = next_ver
        updated = item.model_copy(update={"version": next_ver, "result": result})
        return self.store.save_scenario(updated)

    def diff(self, scenario_id: str, from_ver: str, to_ver: str) -> dict:
        item = self.store.get_scenario(scenario_id)
        if not item:
            raise LookupError(f"scenario not found: {scenario_id}")
        return {
            "scenarioId": scenario_id,
            "from": from_ver,
            "to": to_ver,
            "note": "in-memory store keeps latest version only",
            "currentVersion": item.version,
            "changed": from_ver != to_ver,
        }

from __future__ import annotations

import logging

from app.services.analysis_models import BackendAnalysisRequest, FrontendAnalysisRequest
from app.services.api_mapping import ApiMappingService
from app.services.api_mapping_models import ApiMappingCreateRequest
from app.services.backend_analysis import BackendAnalysisService
from app.services.frontend_analysis import FrontendAnalysisService
from app.services.interaction_graph import InteractionGraphService
from app.services.interaction_graph_models import InteractionGraphCreateRequest
from app.services.repository_store import InMemoryPlatformStore
from app.services.component_contract_service import ComponentContractService
from app.services.input_recommend_models import RecommendInputsRequest
from app.services.input_recommend_service import InputRecommendService
from app.services.scenario_models import PipelineRequest, PipelineResult, ScenarioCreateRequest
from app.services.scenario_service import ScenarioService

logger = logging.getLogger(__name__)


class AnalyzeToScenariosPipeline:
    """FE→BE→map→graph→scenarios→contracts→recommend one-shot (observational; no Pass/Fail)."""

    def __init__(self, store: InMemoryPlatformStore) -> None:
        self.store = store
        self.fe = FrontendAnalysisService(store)
        self.be = BackendAnalysisService(store)
        self.map = ApiMappingService(store)
        self.graph = InteractionGraphService(store)
        self.scenarios = ScenarioService(store)
        self.contracts = ComponentContractService(store)
        self.recommend = InputRecommendService(store)

    def run(self, project_id: str, payload: PipelineRequest | None = None) -> PipelineResult:
        payload = payload or PipelineRequest()
        project = self.store.get_project(project_id)
        if not project:
            raise ValueError("project not found")

        steps: list[dict] = []
        fe_id = be_id = map_id = graph_id = None
        scenario_ids: list[str] = []

        try:
            reused_fe = (
                self.store.get_analysis(payload.frontendAnalysisId)
                if payload.frontendAnalysisId
                else None
            )
            if reused_fe and reused_fe.status == "complete":
                fe = reused_fe
                fe_id = fe.id
                steps.append(
                    {
                        "step": "frontend_analyze",
                        "status": "reused",
                        "id": fe.id,
                    }
                )
            else:
                fe = self.fe.run(FrontendAnalysisRequest(projectId=project_id))
                fe_id = fe.id
                steps.append(
                    {
                        "step": "frontend_analyze",
                        "status": fe.status,
                        "id": fe.id,
                        "error": fe.error,
                    }
                )
                if fe.status != "complete":
                    raise RuntimeError(fe.error or "frontend analysis incomplete")
        except Exception as exc:  # noqa: BLE001
            # Fallback: reuse BE workspace for FE probe when role-split repos are absent
            be_hint = (
                self.store.get_analysis(payload.backendAnalysisId)
                if payload.backendAnalysisId
                else None
            )
            workspace = be_hint.workspacePath if be_hint else None
            if workspace:
                try:
                    fe = self.fe.run(
                        FrontendAnalysisRequest(
                            projectId=project_id,
                            repositorySetId=be_hint.repositorySetId if be_hint else None,
                            workspacePath=workspace,
                            commitSha=be_hint.commitSha if be_hint else None,
                        )
                    )
                    fe_id = fe.id
                    steps.append(
                        {
                            "step": "frontend_analyze",
                            "status": fe.status,
                            "id": fe.id,
                            "error": fe.error,
                            "note": "fallback workspace from backend analysis",
                        }
                    )
                    if fe.status != "complete":
                        raise RuntimeError(fe.error or "frontend analysis incomplete")
                except Exception as fe_exc:  # noqa: BLE001
                    steps.append({"step": "frontend_analyze", "status": "error", "error": str(fe_exc)})
                    return PipelineResult(
                        projectId=project_id,
                        serviceId=payload.serviceId,
                        status="partial",
                        steps=steps,
                        message=f"frontend analysis failed: {fe_exc}",
                    )
            else:
                steps.append({"step": "frontend_analyze", "status": "error", "error": str(exc)})
                return PipelineResult(
                    projectId=project_id,
                    serviceId=payload.serviceId,
                    status="partial",
                    steps=steps,
                    message=f"frontend analysis failed: {exc}",
                )

        try:
            reused_be = (
                self.store.get_analysis(payload.backendAnalysisId)
                if payload.backendAnalysisId
                else None
            )
            if reused_be and reused_be.status == "complete":
                be = reused_be
                be_id = be.id
                steps.append(
                    {
                        "step": "backend_analyze",
                        "status": "reused",
                        "id": be.id,
                    }
                )
            else:
                be = self.be.run(BackendAnalysisRequest(projectId=project_id))
                be_id = be.id
                steps.append(
                    {
                        "step": "backend_analyze",
                        "status": be.status,
                        "id": be.id,
                        "error": be.error,
                    }
                )
                if be.status != "complete":
                    raise RuntimeError(be.error or "backend analysis incomplete")
        except Exception as exc:  # noqa: BLE001
            steps.append({"step": "backend_analyze", "status": "error", "error": str(exc)})
            return PipelineResult(
                projectId=project_id,
                serviceId=payload.serviceId,
                status="partial",
                steps=steps,
                frontendAnalysisId=fe_id,
                message=f"backend analysis failed: {exc}",
            )

        try:
            mapping = self.map.create_for_project(
                project_id,
                ApiMappingCreateRequest(frontendAnalysisId=fe_id, backendAnalysisId=be_id),
            )
            map_id = mapping.mappingSetId
            steps.append({"step": "api_map", "status": "complete", "id": map_id})
        except Exception as exc:  # noqa: BLE001
            steps.append({"step": "api_map", "status": "error", "error": str(exc)})
            return PipelineResult(
                projectId=project_id,
                serviceId=payload.serviceId,
                status="partial",
                steps=steps,
                frontendAnalysisId=fe_id,
                backendAnalysisId=be_id,
                message=f"api map failed: {exc}",
            )

        try:
            graph = self.graph.create_for_project(
                project_id,
                InteractionGraphCreateRequest(
                    frontendAnalysisId=fe_id,
                    backendAnalysisId=be_id,
                    mappingSetId=map_id,
                ),
            )
            graph_id = graph.graphId
            # stamp serviceId
            graph = graph.model_copy(
                update={
                    "serviceId": payload.serviceId,
                    "result": {**(graph.result or {}), "serviceId": payload.serviceId},
                }
            )
            self.store.save_graph(graph)
            steps.append(
                {
                    "step": "interaction_graph",
                    "status": "complete",
                    "id": graph_id,
                    "nodes": graph.nodeCount,
                    "edges": graph.edgeCount,
                }
            )
        except Exception as exc:  # noqa: BLE001
            steps.append({"step": "interaction_graph", "status": "error", "error": str(exc)})
            return PipelineResult(
                projectId=project_id,
                serviceId=payload.serviceId,
                status="partial",
                steps=steps,
                frontendAnalysisId=fe_id,
                backendAnalysisId=be_id,
                mappingSetId=map_id,
                message=f"graph failed: {exc}",
            )

        try:
            created = self.scenarios.create_from_graph(
                graph_id, ScenarioCreateRequest(serviceId=payload.serviceId)
            )
            scenario_ids = [c.scenarioId for c in created]
            steps.append(
                {"step": "scenario_dsl", "status": "complete", "ids": scenario_ids, "count": len(scenario_ids)}
            )
        except Exception as exc:  # noqa: BLE001
            steps.append({"step": "scenario_dsl", "status": "error", "error": str(exc)})
            return PipelineResult(
                projectId=project_id,
                serviceId=payload.serviceId,
                status="partial",
                steps=steps,
                frontendAnalysisId=fe_id,
                backendAnalysisId=be_id,
                mappingSetId=map_id,
                graphId=graph_id,
                message=f"scenario failed: {exc}",
            )

        contract_ids: list[str] = []
        try:
            for sid in scenario_ids:
                contract = self.contracts.build_for_scenario(sid)
                contract_ids.append(contract.contractId)
            steps.append(
                {
                    "step": "component_contract",
                    "status": "complete",
                    "ids": contract_ids,
                    "count": len(contract_ids),
                }
            )
        except Exception as exc:  # noqa: BLE001
            steps.append({"step": "component_contract", "status": "error", "error": str(exc)})
            return PipelineResult(
                projectId=project_id,
                serviceId=payload.serviceId,
                status="partial",
                steps=steps,
                frontendAnalysisId=fe_id,
                backendAnalysisId=be_id,
                mappingSetId=map_id,
                graphId=graph_id,
                scenarioIds=scenario_ids,
                message=f"component contract failed: {exc}",
            )

        recommendation_ids: list[str] = []
        try:
            for sid in scenario_ids:
                rec = self.recommend.recommend(
                    sid, RecommendInputsRequest(seed=42, buildProfile=False)
                )
                recommendation_ids.append(rec.recommendationId)
            steps.append(
                {
                    "step": "input_recommend",
                    "status": "complete",
                    "ids": recommendation_ids,
                    "count": len(recommendation_ids),
                }
            )
        except Exception as exc:  # noqa: BLE001
            steps.append({"step": "input_recommend", "status": "error", "error": str(exc)})
            return PipelineResult(
                projectId=project_id,
                serviceId=payload.serviceId,
                status="partial",
                steps=steps,
                frontendAnalysisId=fe_id,
                backendAnalysisId=be_id,
                mappingSetId=map_id,
                graphId=graph_id,
                scenarioIds=scenario_ids,
                contractIds=contract_ids,
                message=f"input recommend failed: {exc}",
            )

        # Journey Type 2: pipeline produced scenarios → create+list observable
        self.store.update_project_journey(
            project_id,
            scenario_create="complete",
            scenario_list="complete" if scenario_ids else "pending",
        )

        return PipelineResult(
            projectId=project_id,
            serviceId=payload.serviceId,
            status="complete",
            steps=steps,
            frontendAnalysisId=fe_id,
            backendAnalysisId=be_id,
            mappingSetId=map_id,
            graphId=graph_id,
            scenarioIds=scenario_ids,
            contractIds=contract_ids,
            recommendationIds=recommendation_ids,
            message="analyze-to-scenarios pipeline finished (observation only)",
        )

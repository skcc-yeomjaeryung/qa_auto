from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from app.agents.platform_runner.adapter import PlatformRunnerAdapter
from app.core.paths import ARTIFACTS_ANALYSIS, REPO_ROOT
from app.services.component_contract_models import (
    ComponentContractBuildRequest,
    ComponentContractSummary,
)
from app.services.repository_models import utc_now
from app.services.repository_store import InMemoryPlatformStore
from app.skills.component_contract.script.build_contract import build_contract

logger = logging.getLogger(__name__)

DEFAULT_ADAPTER = (
    REPO_ROOT / "packages" / "adapter-sdk" / "examples" / "ui-adapter.customer-search.json"
)


class ComponentContractService:
    def __init__(self, store: InMemoryPlatformStore) -> None:
        self.store = store

    def build_for_scenario(
        self,
        scenario_id: str,
        payload: ComponentContractBuildRequest | None = None,
    ) -> ComponentContractSummary:
        payload = payload or ComponentContractBuildRequest()
        scenario = self.store.get_scenario(scenario_id)
        if not scenario:
            raise LookupError(f"scenario not found: {scenario_id}")

        fe, be, graph, fe_id, be_id = self._resolve_analyses(
            scenario.projectId,
            scenario.graphId,
            payload.frontendAnalysisId,
            payload.backendAnalysisId,
        )
        if not fe:
            raise RuntimeError("frontend analysis required for component contract")

        # The bundled adapter is a customer-search textbook asset.  Applying it to a
        # multi-service project leaks unrelated customer fields into every scenario.
        graph_summary = self.store.get_graph(scenario.graphId) if scenario.graphId else None
        graph_service_id = (
            graph_summary.serviceId if graph_summary else str(graph.get("serviceId") or "")
        )
        customer_search_textbook = (
            scenario.serviceId == "customer-search" or graph_service_id == "customer-search"
        )
        adapter_path = payload.adapterPath or (
            str(DEFAULT_ADAPTER) if customer_search_textbook else ""
        )
        out_dir = ARTIFACTS_ANALYSIS / (scenario.graphId or "no-graph") / "contracts"
        out_file = out_dir / f"{scenario_id}.component-contract.json"
        out_dir.mkdir(parents=True, exist_ok=True)

        response = PlatformRunnerAdapter().execute(
            "wf_component_contract",
            {
                "projectId": scenario.projectId,
                "scenarioId": scenario_id,
                "serviceId": payload.serviceId or scenario.serviceId,
                "frontendAnalysis": fe,
                "backendAnalysis": be,
                "interactionGraph": graph,
                "scenarioDefinition": (
                    scenario.result if not customer_search_textbook else None
                ),
                "adapterPath": adapter_path,
                "artifactPath": str(out_file.resolve()),
            },
        )
        if response.status != "complete" or not response.stepResults:
            # Deterministic fallback without Hub (tests / partial hub)
            logger.warning("component_contract workflow incomplete; using direct builder")
            result = build_contract(
                fe,
                be,
                graph=graph or {},
                adapter=self._load_adapter(adapter_path),
                scenario_id=scenario_id,
                service_id=payload.serviceId or scenario.serviceId,
                project_id=scenario.projectId,
                scenario=(scenario.result if not customer_search_textbook else None),
            )
            out_file.write_text(
                __import__("json").dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return self._save(result, scenario_id, scenario, str(out_file), fe_id, be_id)

        output = response.stepResults[0].get("output") or {}
        if not output.get("ok"):
            raise RuntimeError("component_contract skill output missing ok=true")
        result = output.get("result") or {}
        artifact = output.get("artifactPath") or str(out_file)
        return self._save(result, scenario_id, scenario, artifact, fe_id, be_id)

    def get_for_scenario(self, scenario_id: str) -> ComponentContractSummary | None:
        return self.store.get_contract_by_scenario(scenario_id)

    def build_direct(
        self,
        frontend: dict,
        backend: dict | None = None,
        *,
        graph: dict | None = None,
        adapter_path: str | None = None,
        scenario_id: str | None = None,
        service_id: str = "customer-search",
        project_id: str | None = None,
    ) -> dict:
        from app.skills.component_contract.script.build_contract import _load_adapter

        return build_contract(
            frontend,
            backend or {},
            graph=graph or {},
            adapter=_load_adapter(adapter_path or str(DEFAULT_ADAPTER)),
            scenario_id=scenario_id,
            service_id=service_id,
            project_id=project_id,
        )

    def _save(
        self,
        result: dict,
        scenario_id: str,
        scenario,
        artifact: str,
        fe_id: str | None,
        be_id: str | None,
    ) -> ComponentContractSummary:
        summary = ComponentContractSummary(
            contractId=result.get("contractId") or f"CC-{uuid4().hex[:12]}",
            scenarioId=scenario_id,
            serviceId=result.get("serviceId") or scenario.serviceId,
            projectId=scenario.projectId,
            graphId=scenario.graphId,
            artifactPath=artifact,
            inputCount=len(result.get("inputs") or []),
            outputCount=len(result.get("outputs") or []),
            warningCount=len(result.get("warnings") or []),
            mismatchCount=len(result.get("validationMismatches") or []),
            createdAt=result.get("generatedAt") or utc_now().isoformat(),
            result=result,
        )
        # stamp analysis ids into sourceRefs for trace
        refs = dict(summary.result.get("sourceRefs") or {})
        if fe_id:
            refs["frontendAnalysisId"] = fe_id
        if be_id:
            refs["backendAnalysisId"] = be_id
        summary.result["sourceRefs"] = refs
        return self.store.save_contract(summary)

    def _resolve_analyses(
        self,
        project_id: str | None,
        graph_id: str | None,
        fe_id: str | None,
        be_id: str | None,
    ) -> tuple[dict, dict, dict, str | None, str | None]:
        graph = self.store.get_graph(graph_id) if graph_id else None
        if graph:
            fe_id = fe_id or graph.frontendAnalysisId
            be_id = be_id or graph.backendAnalysisId

        fe_an = self.store.get_analysis(fe_id) if fe_id else None
        be_an = self.store.get_analysis(be_id) if be_id else None

        if not fe_an and project_id:
            for item in self.store.list_analyses(project_id):
                if item.role == "frontend" and item.status == "complete":
                    fe_an = item
                    fe_id = item.id
                    break
        if not be_an and project_id:
            for item in self.store.list_analyses(project_id):
                if item.role == "backend" and item.status == "complete":
                    be_an = item
                    be_id = item.id
                    break

        fe = dict(fe_an.result) if fe_an and fe_an.result else {}
        be = dict(be_an.result) if be_an and be_an.result else {}
        graph_body = dict(graph.result) if graph and graph.result else {}
        return fe, be, graph_body, fe_id, be_id

    @staticmethod
    def _load_adapter(path: str) -> dict:
        from app.skills.component_contract.script.build_contract import _load_adapter

        return _load_adapter(path)

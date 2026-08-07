from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from app.agents.platform_runner.adapter import PlatformRunnerAdapter
from app.core.paths import ARTIFACTS_ANALYSIS, REPO_ROOT
from app.services.interaction_graph_models import (
    EDGE_TYPES,
    EdgeCreateRequest,
    EdgePatchRequest,
    InteractionGraphCreateRequest,
    InteractionGraphSummary,
)
from app.skills.interaction_graph.script.compose_graph import find_paths
from app.services.repository_models import utc_now
from app.services.repository_store import InMemoryPlatformStore

logger = logging.getLogger(__name__)


class InteractionGraphService:
    """Resolve FE/BE/map artifacts, then run Hub Workflow (no graph logic here)."""

    def __init__(self, store: InMemoryPlatformStore) -> None:
        self.store = store

    def create_for_project(
        self, project_id: str, payload: InteractionGraphCreateRequest
    ) -> InteractionGraphSummary:
        project = self.store.get_project(project_id)
        if not project:
            raise ValueError("project not found")

        fe_path, fe_id = self._resolve_analysis(
            project_id,
            role="frontend",
            analysis_id=payload.frontendAnalysisId,
            explicit_path=payload.frontendAnalysisPath,
        )
        be_path, be_id = self._resolve_analysis(
            project_id,
            role="backend",
            analysis_id=payload.backendAnalysisId,
            explicit_path=payload.backendAnalysisPath,
        )
        map_path, map_id = self._resolve_mapping(
            project_id,
            mapping_set_id=payload.mappingSetId,
            explicit_path=payload.apiMappingPath,
        )

        graph_id = f"IG-{uuid4().hex[:12]}"
        out_file = ARTIFACTS_ANALYSIS / graph_id / "interaction-graph.json"
        out_file.parent.mkdir(parents=True, exist_ok=True)

        response = PlatformRunnerAdapter().execute(
            "wf_interaction_graph",
            {
                "projectId": project_id,
                "repositorySetId": project.repositorySetId,
                "frontendAnalysisId": fe_id,
                "backendAnalysisId": be_id,
                "mappingSetId": map_id,
                "frontendAnalysisPath": str(fe_path),
                "backendAnalysisPath": str(be_path),
                "apiMappingPath": str(map_path),
                "graphId": graph_id,
                "artifactPath": str(out_file.resolve()),
            },
        )
        if response.status != "complete" or not response.stepResults:
            raise RuntimeError(response.summary or "interaction graph workflow failed")

        output = response.stepResults[0].get("output") or {}
        if not output.get("ok"):
            raise RuntimeError("interaction_graph skill output missing ok=true")

        result = output.get("result") or {}
        service_id = str(result.get("serviceId") or "customer-search")
        result.setdefault("serviceId", service_id)
        summary = InteractionGraphSummary(
            graphId=result.get("graphId") or graph_id,
            projectId=project_id,
            repositorySetId=result.get("repositorySetId") or project.repositorySetId,
            frontendAnalysisId=fe_id,
            backendAnalysisId=be_id,
            mappingSetId=map_id,
            serviceId=service_id,
            status="complete",
            artifactPath=output.get("artifactPath") or str(out_file),
            version=str(result.get("version") or "1"),
            commitRefs=dict(result.get("commitRefs") or {}),
            nodeCount=int(output.get("nodeCount") or len(result.get("nodes") or [])),
            edgeCount=int(output.get("edgeCount") or len(result.get("edges") or [])),
            primaryPath=list(result.get("primaryPath") or []),
            branches=_dedupe_branches(list(result.get("branches") or [])),
            unresolvedCount=len(result.get("unresolved") or []),
            createdAt=result.get("generatedAt") or utc_now().isoformat(),
            result={**result, "branches": _dedupe_branches(list(result.get("branches") or []))},
        )
        return self.store.save_graph(summary)

    def list_graphs(self, project_id: str | None = None) -> list[InteractionGraphSummary]:
        return [_with_deduped_branches(g) for g in self.store.list_graphs(project_id)]

    def get_graph(self, graph_id: str) -> InteractionGraphSummary | None:
        item = self.store.get_graph(graph_id)
        return _with_deduped_branches(item) if item else None

    def delete_graph(self, graph_id: str) -> bool:
        return self.store.delete_graph(graph_id)

    def delete_graphs(self, graph_ids: list[str]) -> dict:
        removed = self.store.delete_graphs(graph_ids)
        return {
            "status": "deleted",
            "removed": removed,
            "requested": len(graph_ids),
            "message": f"플로우 그래프 {removed}건 삭제",
        }

    def _graph_parts(self, graph_id: str) -> tuple[InteractionGraphSummary, dict, list[dict], set[str]]:
        item = self.store.get_graph(graph_id)
        if not item or not item.result:
            raise LookupError(f"graph not found: {graph_id}")
        result = dict(item.result)
        edges = list(result.get("edges") or [])
        nodes = {n.get("id") for n in (result.get("nodes") or []) if n.get("id")}
        return item, result, edges, nodes

    def _save_edges(
        self, item: InteractionGraphSummary, result: dict, edges: list[dict]
    ) -> InteractionGraphSummary:
        result["edges"] = edges
        return self.store.save_graph(
            item.model_copy(update={"result": result, "edgeCount": len(edges)})
        )

    def _find_edge(
        self,
        edges: list[dict],
        *,
        edge_id: str | None,
        from_id: str | None = None,
        old_to: str | None = None,
    ) -> dict:
        for edge in edges:
            if edge_id and edge.get("id") == edge_id:
                return edge
            if from_id and old_to and edge.get("from") == from_id and edge.get("to") == old_to:
                return edge
        raise ValueError("edge not found")

    def patch_edge(
        self,
        graph_id: str,
        edge_id: str,
        payload: EdgePatchRequest,
    ) -> InteractionGraphSummary:
        """Retarget and/or re-condition one edge. Human edits are marked, not hidden."""
        item, result, edges, nodes = self._graph_parts(graph_id)
        edge = self._find_edge(edges, edge_id=edge_id)
        new_to = payload.resolved_to()
        if new_to:
            if new_to not in nodes:
                raise ValueError(f"target node missing_data: {new_to}")
            edge["to"] = new_to
        if payload.type:
            if payload.type not in EDGE_TYPES:
                raise ValueError(f"unsupported edge type: {payload.type}")
            edge["type"] = payload.type
        if payload.clearCondition:
            edge["condition"] = None
        elif payload.condition is not None:
            edge["condition"] = payload.condition
        edge["editedBy"] = "human"
        edge["rewiredAt"] = utc_now()
        return self._save_edges(item, result, edges)

    def rewire_edge(
        self,
        graph_id: str,
        *,
        edge_id: str | None = None,
        from_id: str | None = None,
        old_to: str | None = None,
        new_to: str,
        condition: str | None = None,
    ) -> InteractionGraphSummary:
        """Rewire A→B to A→C in graph result (deterministic). Does not invent nodes."""
        item, result, edges, nodes = self._graph_parts(graph_id)
        if new_to not in nodes:
            raise ValueError(f"target node missing_data: {new_to}")
        edge = self._find_edge(edges, edge_id=edge_id, from_id=from_id, old_to=old_to)
        edge["to"] = new_to
        if condition is not None:
            edge["condition"] = condition
        edge["editedBy"] = "human"
        edge["rewiredAt"] = utc_now()
        return self._save_edges(item, result, edges)

    def delete_edge(self, graph_id: str, edge_id: str) -> InteractionGraphSummary:
        """Disconnect an edge. Nodes stay — only the relation is removed."""
        item, result, edges, _ = self._graph_parts(graph_id)
        remaining = [e for e in edges if e.get("id") != edge_id]
        if len(remaining) == len(edges):
            raise ValueError("edge not found")
        return self._save_edges(item, result, remaining)

    def create_edge(
        self, graph_id: str, payload: EdgeCreateRequest
    ) -> InteractionGraphSummary:
        """Connect two existing nodes by hand. Confidence stays low — a person asserted it."""
        item, result, edges, nodes = self._graph_parts(graph_id)
        if payload.from_ not in nodes:
            raise ValueError(f"source node missing_data: {payload.from_}")
        if payload.to not in nodes:
            raise ValueError(f"target node missing_data: {payload.to}")
        if payload.from_ == payload.to:
            raise ValueError("self edge not allowed")
        if payload.type not in EDGE_TYPES:
            raise ValueError(f"unsupported edge type: {payload.type}")
        if any(
            e.get("from") == payload.from_
            and e.get("to") == payload.to
            and e.get("type") == payload.type
            for e in edges
        ):
            raise ValueError("edge already exists")
        base = f"edge-manual-{payload.type}"
        suffix = 1
        eid = base
        taken = {e.get("id") for e in edges}
        while eid in taken:
            suffix += 1
            eid = f"{base}-{suffix}"
        edges.append(
            {
                "id": eid,
                "from": payload.from_,
                "to": payload.to,
                "type": payload.type,
                "condition": payload.condition,
                "dataMappings": [],
                # Human assertion, not a code-derived fact — stays below the 0.70
                # unresolved threshold until execution observes it.
                "confidence": 0.5,
                "evidence": [],
                "editedBy": "human",
                "createdAt": utc_now(),
            }
        )
        return self._save_edges(item, result, edges)

    def find_paths(self, graph_id: str, from_id: str, to_id: str) -> dict:
        item = self.store.get_graph(graph_id)
        if not item:
            raise LookupError(f"graph not found: {graph_id}")
        paths = find_paths(item.result or {}, from_id, to_id)
        return {
            "graphId": graph_id,
            "from": from_id,
            "to": to_id,
            "paths": paths,
            "count": len(paths),
        }

    def _resolve_mapping(
        self,
        project_id: str,
        *,
        mapping_set_id: str | None,
        explicit_path: str | None,
    ) -> tuple[Path, str | None]:
        if explicit_path:
            path = self._resolve_file(explicit_path)
            return path, mapping_set_id

        if mapping_set_id:
            item = self.store.get_mapping_set(mapping_set_id)
            if not item:
                raise ValueError(f"mapping set not found: {mapping_set_id}")
            if not item.artifactPath:
                raise ValueError(f"mapping set artifact missing: {mapping_set_id}")
            path = Path(item.artifactPath).resolve()
            if not path.is_file():
                raise ValueError(f"mapping artifact missing: {path}")
            return path, mapping_set_id

        candidates = list(self.store.list_mapping_sets(project_id))
        if not candidates:
            raise ValueError(
                "no api mapping for project — run Map FE↔BE APIs first or pass mappingSetId/path"
            )
        item = sorted(candidates, key=lambda m: m.createdAt or "", reverse=True)[0]
        path = Path(str(item.artifactPath)).resolve()
        if not path.is_file():
            raise ValueError(f"mapping artifact missing: {path}")
        return path, item.mappingSetId

    def _resolve_analysis(
        self,
        project_id: str,
        *,
        role: str,
        analysis_id: str | None,
        explicit_path: str | None,
    ) -> tuple[Path, str | None]:
        if explicit_path:
            return self._resolve_file(explicit_path), analysis_id

        if analysis_id:
            item = self.store.get_analysis(analysis_id)
            if not item or item.role != role:
                raise ValueError(f"{role} analysis not found: {analysis_id}")
            if item.status != "complete" or not item.artifactPath:
                raise ValueError(f"{role} analysis not complete: {analysis_id}")
            path = Path(item.artifactPath).resolve()
            if not path.is_file():
                raise ValueError(f"{role} artifact missing: {path}")
            return path, analysis_id

        candidates = [
            a
            for a in self.store.list_analyses(project_id)
            if a.role == role and a.status == "complete" and a.artifactPath
        ]
        if not candidates:
            raise ValueError(
                f"no complete {role} analysis for project — run analysis first or pass ids/paths"
            )
        item = sorted(candidates, key=lambda a: a.createdAt, reverse=True)[0]
        path = Path(str(item.artifactPath)).resolve()
        if not path.is_file():
            raise ValueError(f"{role} artifact missing: {path}")
        return path, item.id

    def _resolve_file(self, explicit_path: str) -> Path:
        path = Path(explicit_path).expanduser().resolve()
        if not path.is_file():
            alt = (REPO_ROOT / explicit_path).resolve()
            path = alt if alt.is_file() else path
        if not path.is_file():
            raise ValueError(f"file not found: {explicit_path}")
        return path


def _dedupe_branches(branches: list) -> list:
    seen: set[str] = set()
    out: list = []
    for b in branches:
        if not isinstance(b, dict):
            continue
        bid = str(b.get("id") or b.get("condition") or "")
        if not bid or bid in seen:
            continue
        seen.add(bid)
        out.append(b)
    return out


def _with_deduped_branches(item):
    branches = _dedupe_branches(list(item.branches or []))
    result = dict(item.result or {})
    if result:
        result["branches"] = _dedupe_branches(list(result.get("branches") or branches))
    return item.model_copy(update={"branches": branches, "result": result})

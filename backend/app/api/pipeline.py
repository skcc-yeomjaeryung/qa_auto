from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import get_platform_store
from app.services.pipeline import AnalyzeToScenariosPipeline
from app.services.scenario_models import PipelineRequest, PipelineResult

router = APIRouter(prefix="/api", tags=["pipeline"])


@router.post(
    "/projects/{project_id}/pipeline/analyze-to-scenarios",
    response_model=PipelineResult,
)
def run_analyze_to_scenarios(
    project_id: str, payload: PipelineRequest | None = None
) -> PipelineResult:
    try:
        return AnalyzeToScenariosPipeline(get_platform_store()).run(
            project_id, payload or PipelineRequest()
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

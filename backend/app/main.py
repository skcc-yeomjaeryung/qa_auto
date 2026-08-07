from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.api.analyses import router as analyses_router
from app.api.api_mappings import router as api_mappings_router
from app.api.auth_guard import UserHeaderGuard
from app.api.binding_validation import router as binding_validation_router
from app.api.batches import router as batches_router
from app.api.console import router as console_router
from app.api.dashboard import router as dashboard_router
from app.api.environments import router as environments_router
from app.api.evidence import router as evidence_router
from app.api.flows import router as flows_router
from app.api.interaction_graphs import router as interaction_graphs_router
from app.api.pipeline import router as pipeline_router
from app.api.projects import router as projects_router
from app.api.project_context import router as project_context_router
from app.api.repository_sets import router as repository_sets_router
from app.api.runs import router as runs_router
from app.api.run_reports import router as run_reports_router
from app.api.scenario_runs import router as scenario_runs_router
from app.api.scenarios import router as scenarios_router
from app.api.schedules import router as schedules_router
from app.api.component_contracts import router as component_contracts_router
from app.api.input_profiles import router as input_profiles_router
from app.api.telemetry import router as telemetry_router
from app.api.models import router as models_router
from app.api.agent_monitor import router as agent_monitor_router
from app.core.bootstrap import bootstrap_runtime, get_runtime
from app.api.deps import get_platform_store
from app.services.schedule_service import start_schedule_coordinator, stop_schedule_coordinator

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    bootstrap_runtime()
    start_schedule_coordinator(get_platform_store)
    try:
        yield
    finally:
        stop_schedule_coordinator()


app = FastAPI(title="AI_TEST Control Plane", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(UserHeaderGuard)


@app.get("/health", tags=["health"])
def health() -> dict:
    runtime = get_runtime()
    return {
        "status": "ok",
        "service": "qa-auto-backend",
        "version": "1.0.0",
        "hubCounts": {
            "workflows": runtime.workflows.count(),
            "skills": runtime.skills.count(),
            "capabilities": runtime.capabilities.count(),
            "agents": runtime.agents.count(),
            "models": len(runtime.models.list()),
        },
    }


@app.get("/metrics", include_in_schema=False, response_class=PlainTextResponse)
def metrics() -> str:
    """Prometheus scrape endpoint for real provider calls, not model selections."""
    return get_runtime().events.prometheus_metrics()


app.include_router(runs_router)
app.include_router(run_reports_router)
app.include_router(batches_router)
app.include_router(schedules_router)
app.include_router(dashboard_router)
app.include_router(scenario_runs_router)
app.include_router(telemetry_router)
app.include_router(binding_validation_router)
app.include_router(evidence_router)
app.include_router(projects_router)
app.include_router(project_context_router)
app.include_router(environments_router)
app.include_router(repository_sets_router)
app.include_router(analyses_router)
app.include_router(api_mappings_router)
app.include_router(interaction_graphs_router)
app.include_router(scenarios_router)
app.include_router(component_contracts_router)
app.include_router(input_profiles_router)
app.include_router(pipeline_router)
app.include_router(flows_router)
app.include_router(console_router)
app.include_router(models_router)
app.include_router(agent_monitor_router)

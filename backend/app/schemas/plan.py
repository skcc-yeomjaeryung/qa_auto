from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.models.contracts import ModelDecision


class PlanStep(BaseModel):
    stepId: str
    agent: str | None = None
    skill: str
    tool: str
    dependsOn: list[str] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    requiredCapability: str | None = None
    selectionReason: str | None = None
    modelDecision: ModelDecision | None = None


class Plan(BaseModel):
    schemaVersion: str = "plan/v2"
    planId: str
    workflowId: str
    steps: list[PlanStep]


class RunExecuteRequest(BaseModel):
    workflowId: str = "wf_health_smoke"
    inputs: dict[str, Any] = Field(default_factory=dict)


class RunExecuteResponse(BaseModel):
    status: str
    plan: Plan
    stepResults: list[dict[str, Any]] = Field(default_factory=list)
    summary: str
    reviewNotes: list[str] = Field(default_factory=list)

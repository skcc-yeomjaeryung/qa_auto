from __future__ import annotations

from app.core.models.contracts import (
    AiPolicy,
    CandidateEvaluation,
    ModelDecision,
    ModelRequirement,
)
from app.core.models.registry import ModelRegistry
from app.core.prompts import PromptCatalog


POLICY_WEIGHTS: dict[str, dict[str, float]] = {
    "auto": {"quality": 0.35, "reliability": 0.30, "speed": 0.20, "cost": 0.15},
    "cost_saver": {"quality": 0.15, "reliability": 0.20, "speed": 0.20, "cost": 0.45},
    "balanced": {"quality": 0.30, "reliability": 0.30, "speed": 0.20, "cost": 0.20},
    "highest_quality": {"quality": 0.55, "reliability": 0.30, "speed": 0.10, "cost": 0.05},
    "internal_only": {"quality": 0.35, "reliability": 0.35, "speed": 0.20, "cost": 0.10},
}


class ModelSelector:
    """Deterministic, auditable policy engine. It never exposes hidden model reasoning."""

    def __init__(self, registry: ModelRegistry, prompts: PromptCatalog | None = None) -> None:
        self.registry = registry
        self.prompts = prompts or PromptCatalog()

    def select(
        self,
        requirement: ModelRequirement,
        policy: AiPolicy = "auto",
        *,
        preferred_model_profile_id: str | None = None,
        selection_role: str | None = None,
    ) -> ModelDecision:
        _, prompt_metadata = self.prompts.render(
            "agent_roles/model_advisor_system.md",
            "작업 요구사항: {requirements}\n선택 정책: {policy}\n후보는 Core의 하드 필터를 통과한 ID만 허용됩니다.",
            requirements=requirement.model_dump_json(),
            policy=policy,
        )
        weights = POLICY_WEIGHTS[policy]
        evaluations: list[CandidateEvaluation] = []
        ranked: list[tuple[float, str]] = []
        required = set(requirement.capabilities)
        for item in self.registry.list():
            reasons: list[str] = []
            if not item.enabled:
                reasons.append("disabled")
            if item.deploymentType == "external" and not item.hasApiKey:
                reasons.append("external model credential is not loaded")
            if policy == "internal_only" and item.deploymentType != "internal":
                reasons.append("external model excluded by internal_only policy")
            missing = required.difference(item.capabilities)
            if missing:
                reasons.append(f"missing capabilities: {', '.join(sorted(missing))}")
            if item.contextWindow < requirement.minimumContext:
                reasons.append(f"context window {item.contextWindow} < {requirement.minimumContext}")
            if requirement.structuredOutput and not item.supportsStructuredOutput:
                reasons.append("structured output unsupported")
            if requirement.tools and not item.supportsTools:
                reasons.append("tool calling unsupported")
            if item.healthStatus == "down":
                reasons.append("health check is down")
            eligible = not reasons
            score: float | None = None
            if eligible:
                score = (
                    item.qualityScore * weights["quality"]
                    + item.reliabilityScore * weights["reliability"]
                    + item.speedScore * weights["speed"]
                    + item.costScore * weights["cost"]
                )
                if item.healthStatus == "unknown":
                    score -= 5
                    reasons.append("health unknown: score penalty -5")
                elif item.healthStatus == "degraded":
                    score -= 15
                    reasons.append("health degraded: score penalty -15")
                if requirement.qualityProfile in {"scenario_generation", "evidence_review"}:
                    score += item.qualityScore * 0.05
                    reasons.append("quality-sensitive task bonus applied")
                ranked.append((score, item.id))
            evaluations.append(
                CandidateEvaluation(
                    modelProfileId=item.id,
                    displayName=item.displayName,
                    modelId=item.modelId,
                    eligible=eligible,
                    score=round(score, 2) if score is not None else None,
                    reasons=reasons,
                )
            )
        if preferred_model_profile_id:
            preferred_eval = next(
                (item for item in evaluations if item.modelProfileId == preferred_model_profile_id),
                None,
            )
            if preferred_eval is None or not preferred_eval.eligible:
                reason = (
                    "등록 목록에서 찾을 수 없습니다."
                    if preferred_eval is None
                    else " · ".join(preferred_eval.reasons) or "요구조건을 충족하지 않습니다."
                )
                return ModelDecision(
                    route="deterministic_fallback",
                    policy=policy,
                    selectionMode="manual",
                    selectionRole=selection_role,
                    decisionSummary=(
                        f"{selection_role or '지정'} 역할의 고정 모델을 사용할 수 없어 규칙 기반 경로로 전환했습니다: {reason}"
                    ),
                    candidates=evaluations,
                    promptVersion=prompt_metadata.version,
                )
            selected = self.registry.require(preferred_model_profile_id)
            return ModelDecision(
                route="model",
                policy=policy,
                selectedModelProfileId=selected.id,
                selectedDisplayName=selected.displayName,
                selectedModelId=selected.modelId,
                selectionMode="manual",
                selectionRole=selection_role,
                decisionSummary=(
                    f"프로젝트에서 {selection_role or '해당'} 역할로 고정한 {selected.displayName}을 선택했습니다."
                ),
                candidates=evaluations,
                promptVersion=prompt_metadata.version,
            )
        if not ranked:
            if not requirement.allowDeterministicFallback:
                raise RuntimeError("no eligible model and deterministic fallback is disabled")
            return ModelDecision(
                route="deterministic_fallback",
                policy=policy,
                selectionRole=selection_role,
                decisionSummary="필수 capability·상태·배포 정책을 모두 충족한 모델이 없어 규칙 기반 경로를 선택했습니다.",
                candidates=evaluations,
                promptVersion=prompt_metadata.version,
            )
        ranked.sort(key=lambda row: (-row[0], row[1]))
        selected = self.registry.require(ranked[0][1])
        return ModelDecision(
            route="model",
            policy=policy,
            selectedModelProfileId=selected.id,
            selectedDisplayName=selected.displayName,
            selectedModelId=selected.modelId,
            selectionRole=selection_role,
            decisionSummary=(
                f"{policy} 정책의 capability·context·health 필터를 통과한 후보 중 "
                f"가중 점수가 가장 높은 {selected.displayName}을 선택했습니다."
            ),
            candidates=evaluations,
            promptVersion=prompt_metadata.version,
        )

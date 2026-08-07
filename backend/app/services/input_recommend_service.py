from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from app.agents.platform_runner.adapter import PlatformRunnerAdapter
from app.core.paths import ARTIFACTS_ANALYSIS, REPO_ROOT
from app.services.input_recommend_models import (
    GenerateCasesRequest,
    InputProfileApproveRequest,
    InputProfileCreateRequest,
    InputProfileSummary,
    RecommendInputsRequest,
    RecommendationSummary,
)
from app.services.repository_models import utc_now
from app.services.repository_store import InMemoryPlatformStore
from app.skills.input_recommend.script.recommend import (
    build_input_profile,
    generate_profile_cases,
    recommend_inputs,
)

logger = logging.getLogger(__name__)

CATALOG_ROOT = REPO_ROOT / "packages" / "test-data-catalog"


class InputRecommendService:
    def __init__(self, store: InMemoryPlatformStore) -> None:
        self.store = store

    def recommend(
        self, scenario_id: str, payload: RecommendInputsRequest | None = None
    ) -> RecommendationSummary:
        payload = payload or RecommendInputsRequest()
        scenario = self.store.get_scenario(scenario_id)
        if not scenario:
            raise LookupError(f"scenario not found: {scenario_id}")

        contract_summary = None
        if payload.contractId:
            contract_summary = self.store.get_contract(payload.contractId)
        if not contract_summary:
            contract_summary = self.store.get_contract_by_scenario(scenario_id)
        if not contract_summary or not contract_summary.result:
            # auto-build contract if missing
            from app.services.component_contract_service import ComponentContractService

            contract_summary = ComponentContractService(self.store).build_for_scenario(scenario_id)

        fe, be = self._analyses_for_scenario(scenario)
        out_dir = ARTIFACTS_ANALYSIS / (scenario.graphId or "no-graph") / "recommendations"
        out_file = out_dir / f"{scenario_id}.recommend.json"
        out_dir.mkdir(parents=True, exist_ok=True)

        response = PlatformRunnerAdapter().execute(
            "wf_input_recommend",
            {
                "projectId": scenario.projectId,
                "scenarioId": scenario_id,
                "serviceId": scenario.serviceId,
                "componentContract": contract_summary.result,
                "frontendAnalysis": fe,
                "backendAnalysis": be,
                "catalogRoot": str(CATALOG_ROOT),
                "seed": payload.seed,
                "buildProfile": payload.buildProfile,
                "budget": payload.budget,
                "unresolvedPolicy": payload.unresolvedPolicy,
                "profileName": payload.profileName or f"{scenario.serviceId} profile",
                "artifactPath": str(out_file.resolve()),
            },
        )

        if response.status == "complete" and response.stepResults:
            output = response.stepResults[0].get("output") or {}
            if output.get("ok") and output.get("result"):
                result = self._scope_to_scenario(output["result"], scenario)
                summary = self._save_recommendation(result, scenario, str(out_file))
                self._mark_contract_recommendation_ready(contract_summary)
                if payload.buildProfile and output.get("profile"):
                    self._save_profile(output["profile"], scenario)
                elif payload.buildProfile:
                    profile = build_input_profile(
                        result,
                        scenario_id=scenario_id,
                        name=payload.profileName or f"{scenario.serviceId} profile",
                        budget=payload.budget,
                        unresolved_policy=payload.unresolvedPolicy,
                        seed=payload.seed,
                    )
                    self._save_profile(profile, scenario)
                return summary

        # Direct fallback
        result = recommend_inputs(
            contract=contract_summary.result,
            frontend=fe,
            backend=be,
            catalog_root=CATALOG_ROOT,
            service_id=scenario.serviceId,
            scenario_id=scenario_id,
            project_id=scenario.projectId,
            seed=payload.seed,
        )
        result = self._scope_to_scenario(result, scenario)
        out_file.write_text(
            __import__("json").dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary = self._save_recommendation(result, scenario, str(out_file))
        self._mark_contract_recommendation_ready(contract_summary)
        if payload.buildProfile:
            profile = build_input_profile(
                result,
                scenario_id=scenario_id,
                name=payload.profileName or f"{scenario.serviceId} profile",
                budget=payload.budget,
                unresolved_policy=payload.unresolvedPolicy,
                seed=payload.seed,
            )
            self._save_profile(profile, scenario)
        return summary

    @staticmethod
    def _scope_to_scenario(result: dict, scenario) -> dict:
        """Pin a generated profile to this Scenario DSL's exact case variant.

        The common recommender describes a field's broad catalogue.  A generated
        below-minimum/maximum/required case must not be overwritten by the happy-path
        recommendation, and runtime-observation strategies must remain runtime-bound.
        """
        scoped = dict(result)
        body = dict(scenario.result or {})
        defaults = dict(scoped.get("defaults") or {})
        recommendations = list(scoped.get("recommendations") or [])
        variant = dict(body.get("caseVariant") or {})
        variant_key = str(variant.get("key") or "")
        variant_category = str(variant.get("category") or "boundary")
        if variant_key == "required_missing":
            variant_category = "missing_required"
        elif variant_category in {"validation", "business_error"}:
            variant_category = "boundary"

        for field, value in dict(body.get("inputDefaults") or {}).items():
            recommendations = [
                item for item in recommendations if str(item.get("field") or "") != str(field)
            ]
            defaults[str(field)] = value
            recommendations.insert(
                0,
                {
                    "field": str(field),
                    "value": value,
                    "displayValue": "(empty)" if value == "" else str(value),
                    "category": variant_category,
                    "expectedPath": "browser_validation"
                    if variant.get("validationOnly")
                    else "business_observation",
                    "rationale": "Scenario DSL의 분석 제약으로 고정된 케이스 입력값",
                    "sources": [
                        {
                            "source": "scenario_case_variant",
                            "rank": 1,
                            "ref": f"scenario.inputDefaults.{field}",
                            "detail": variant_key or "scenario default",
                        }
                    ],
                    "selectedByDefault": True,
                    "reviewRequired": False,
                    "uncertain": False,
                    "masked": False,
                },
            )

        for field, strategy in dict(body.get("inputStrategies") or {}).items():
            recommendations = [
                item for item in recommendations if str(item.get("field") or "") != str(field)
            ]
            defaults.pop(str(field), None)
            recommendations.insert(
                0,
                {
                    "field": str(field),
                    "value": None,
                    "displayValue": "실행 직전 화면 관측값",
                    "category": variant_category,
                    "expectedPath": "runtime_observation",
                    "rationale": "실행 직전 DOM에서 관측한 값으로 계산합니다.",
                    "sources": [
                        {
                            "source": "scenario_case_variant",
                            "rank": 1,
                            "ref": f"scenario.inputStrategies.{field}",
                            "detail": str(strategy),
                        }
                    ],
                    "selectedByDefault": True,
                    "reviewRequired": False,
                    "uncertain": False,
                    "masked": False,
                    "omitFromProfile": True,
                },
            )

        scoped["defaults"] = defaults
        scoped["recommendations"] = recommendations
        return scoped

    def get_recommendation(self, scenario_id: str) -> RecommendationSummary | None:
        return self.store.get_recommendation_by_scenario(scenario_id)

    def list_profiles(self, scenario_id: str) -> list[InputProfileSummary]:
        return list(self.store.list_profiles(scenario_id=scenario_id))

    def create_profile(
        self, scenario_id: str, payload: InputProfileCreateRequest | None = None
    ) -> InputProfileSummary:
        payload = payload or InputProfileCreateRequest()
        scenario = self.store.get_scenario(scenario_id)
        if not scenario:
            raise LookupError(f"scenario not found: {scenario_id}")
        rec = self.store.get_recommendation_by_scenario(scenario_id)
        if not rec:
            rec = self.recommend(
                scenario_id,
                RecommendInputsRequest(seed=payload.seed, buildProfile=False),
            )
        profile = build_input_profile(
            rec.result,
            scenario_id=scenario_id,
            name=payload.name,
            budget=payload.budget,
            categories=payload.categories,
            unresolved_policy=payload.unresolvedPolicy,
            seed=payload.seed,
        )
        if payload.overrides:
            profile = self._with_override_case(profile, dict(payload.overrides))
        return self._save_profile(profile, scenario)

    def _with_override_case(self, profile: dict, overrides: dict) -> dict:
        """사용자 수정값을 첫 Case로 고정한다. HITL 검토 대상으로 표시한다."""
        body = dict(profile)
        cases = list(body.get("cases") or [])
        base_inputs = dict((cases[0].get("inputs") if cases else {}) or {})
        base_inputs.update(overrides)
        cases.insert(
            0,
            {
                "caseId": f"CASE-USER-{len(cases) + 1}",
                "category": "user_override",
                "inputs": base_inputs,
                "expectedPath": (cases[0].get("expectedPath") if cases else None),
                "reviewRequired": True,
                "origin": "console_interactive_override",
            },
        )
        body["cases"] = cases
        counts = dict(body.get("categoryCounts") or {})
        counts["user_override"] = counts.get("user_override", 0) + 1
        body["categoryCounts"] = counts
        return body

    def approve_profile(
        self, profile_id: str, payload: InputProfileApproveRequest | None = None
    ) -> InputProfileSummary:
        payload = payload or InputProfileApproveRequest()
        item = self.store.get_profile(profile_id)
        if not item:
            raise LookupError(f"profile not found: {profile_id}")
        body = dict(item.result)
        body["status"] = "APPROVED"
        body["approvedAt"] = utc_now().isoformat()
        body["approvedBy"] = payload.approvedBy
        # bump version on approve if already approved before
        try:
            ver = int(str(body.get("version") or "1"))
        except ValueError:
            ver = 1
        if item.status == "APPROVED":
            ver += 1
        body["version"] = str(ver)
        updated = item.model_copy(
            update={
                "status": "APPROVED",
                "version": str(ver),
                "approvedAt": body["approvedAt"],
                "approvedBy": payload.approvedBy,
                "result": body,
            }
        )
        return self.store.save_profile(updated)

    def generate_cases(
        self, profile_id: str, payload: GenerateCasesRequest | None = None
    ) -> InputProfileSummary:
        payload = payload or GenerateCasesRequest()
        item = self.store.get_profile(profile_id)
        if not item:
            raise LookupError(f"profile not found: {profile_id}")
        rec = None
        if item.recommendationId:
            rec = self.store.get_recommendation(item.recommendationId)
        if not rec and item.scenarioId:
            rec = self.store.get_recommendation_by_scenario(item.scenarioId)
        if not rec:
            raise RuntimeError("recommendation missing for profile")

        policy = dict((item.result or {}).get("policy") or {})
        budget = int(payload.budget or policy.get("budget") or 8)
        unresolved = str(payload.unresolvedPolicy or policy.get("unresolvedPolicy") or "reviewRequired")
        seed = int(payload.seed or policy.get("seed") or 42)
        categories = payload.categories or policy.get("categories")
        cases, counts = generate_profile_cases(
            rec.result,
            budget=budget,
            categories=categories,
            unresolved_policy=unresolved,
            seed=seed,
        )
        body = dict(item.result)
        body["cases"] = cases
        body["categoryCounts"] = counts
        body["policy"] = {
            **policy,
            "budget": budget,
            "unresolvedPolicy": unresolved,
            "seed": seed,
            "categories": categories or policy.get("categories"),
        }
        # regenerate keeps DRAFT unless already approved — stay same status
        updated = item.model_copy(
            update={
                "caseCount": len(cases),
                "categoryCounts": counts,
                "result": body,
            }
        )
        return self.store.save_profile(updated)

    def _mark_contract_recommendation_ready(self, contract_summary) -> None:
        if not contract_summary or not contract_summary.result:
            return
        body = dict(contract_summary.result)
        body["recommendationReady"] = True
        updated = contract_summary.model_copy(update={"result": body})
        self.store.save_contract(updated)

    def _save_recommendation(
        self, result: dict, scenario, artifact: str
    ) -> RecommendationSummary:
        summary = RecommendationSummary(
            recommendationId=result.get("recommendationId") or f"REC-{uuid4().hex[:8]}",
            scenarioId=scenario.scenarioId,
            serviceId=scenario.serviceId,
            projectId=scenario.projectId,
            contractId=result.get("contractId"),
            artifactPath=artifact,
            defaultCount=len(result.get("defaults") or {}),
            recommendationCount=len(result.get("recommendations") or []),
            createdAt=result.get("generatedAt") or utc_now().isoformat(),
            result=result,
        )
        return self.store.save_recommendation(summary)

    def _save_profile(self, profile: dict, scenario) -> InputProfileSummary:
        summary = InputProfileSummary(
            profileId=profile.get("profileId") or f"IP-{uuid4().hex[:12]}",
            scenarioId=scenario.scenarioId,
            serviceId=scenario.serviceId,
            projectId=scenario.projectId,
            name=profile.get("name") or "",
            version=str(profile.get("version") or "1"),
            status=profile.get("status") or "DRAFT",
            caseCount=len(profile.get("cases") or []),
            categoryCounts=dict(profile.get("categoryCounts") or {}),
            recommendationId=profile.get("recommendationId"),
            approvedAt=profile.get("approvedAt"),
            approvedBy=profile.get("approvedBy"),
            createdAt=profile.get("createdAt") or utc_now().isoformat(),
            result=profile,
        )
        return self.store.save_profile(summary)

    def _analyses_for_scenario(self, scenario) -> tuple[dict, dict]:
        fe: dict = {}
        be: dict = {}
        graph = self.store.get_graph(scenario.graphId) if scenario.graphId else None
        if graph:
            if graph.frontendAnalysisId:
                an = self.store.get_analysis(graph.frontendAnalysisId)
                if an:
                    fe = dict(an.result or {})
            if graph.backendAnalysisId:
                an = self.store.get_analysis(graph.backendAnalysisId)
                if an:
                    be = dict(an.result or {})
        if scenario.projectId:
            if not fe:
                for item in self.store.list_analyses(scenario.projectId):
                    if item.role == "frontend" and item.status == "complete":
                        fe = dict(item.result or {})
                        break
            if not be:
                for item in self.store.list_analyses(scenario.projectId):
                    if item.role == "backend" and item.status == "complete":
                        be = dict(item.result or {})
                        break
        return fe, be

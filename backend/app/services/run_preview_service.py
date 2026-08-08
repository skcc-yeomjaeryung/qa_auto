"""Phase 13 — 건별 실행 전 확인 요약 (Run Preview).

전체 입력 폼을 펼치지 않고도 사용자가 "무엇이 자동 확정됐고 무엇만 확인하면 되는지"를
판단할 수 있도록 시나리오·Contract·추천 Input을 하나의 요약으로 join한다.
근거 없는 값은 추정하지 않고 missing_data로 남긴다.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.schemas.interactive_run import (
    InputConfidence,
    PlanStage,
    RunPreview,
    RunPreviewApi,
    RunPreviewField,
    RunPreviewPreviousRun,
    RunPreviewRequest,
    RunPreviewScreen,
    RunPreviewStep,
)
from app.services.environment_service import EnvironmentService
from app.services.repository_models import utc_now
from app.services.repository_store import InMemoryPlatformStore
from app.skills.browser_execute.script.execute_run import resolve_dsl_steps
from app.skills.input_recommend.script.recommend import is_sensitive_field, synthesize_value

logger = logging.getLogger(__name__)

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
DESTRUCTIVE_TOKENS = (
    "delete",
    "remove",
    "drop",
    "transfer",
    "withdraw",
    "payment",
    "deposit",
    "삭제",
    "송금",
    "출금",
    "이체",
)

_A_INPUT_ACTIONS = {"navigate", "fill", "blur", "press", "select", "check"}
_REQUEST_ACTIONS = {"submit", "click", "wait_for_response", "verify_response"}
# 사용자가 값을 넣어야 하는 step 종류. 이 step이 없는 시나리오(화면 구성 확인 등)는
# 입력값을 요구하지 않는다 — Contract 전체 입력을 끌어오면 테스터에게 거짓 숙제가 된다.
_INPUT_STEP_ACTIONS = {"fill", "type", "select", "check", "uncheck", "upload", "press"}


def _stage_for_action(action: str) -> PlanStage:
    lowered = (action or "").lower()
    if lowered in _A_INPUT_ACTIONS:
        return "a_input"
    if lowered in _REQUEST_ACTIONS:
        return "request"
    return "b_ui"


def _step_description(step: dict[str, Any]) -> str:
    action = str(step.get("action") or "")
    target = step.get("target") if isinstance(step.get("target"), dict) else {}
    expect = step.get("expect") if isinstance(step.get("expect"), dict) else {}
    if action == "navigate":
        return f"A 화면 진입 ({target.get('route') or 'missing_data'})"
    if action == "fill":
        return f"입력 {target.get('value') or 'missing_data'}"
    if action in {"click", "submit"}:
        return f"이벤트 발생 {target.get('value') or 'missing_data'}"
    if action == "wait_for_response":
        return "Backend 응답 대기"
    if action == "verify_response":
        return "응답 관측"
    if action == "verify_navigation":
        return f"B 화면 이동 관측 ({expect.get('routePattern') or 'missing_data'})"
    if action == "verify_binding":
        return "B 화면 바인딩 관측"
    return action or "missing_data"


def _locator_text(locator: Any) -> str | None:
    if not isinstance(locator, dict):
        return None
    strategy = locator.get("strategy") or locator.get("kind")
    value = locator.get("value") or locator.get("selector")
    if not value:
        return None
    return f"{strategy}={value}" if strategy else str(value)


def _loose_key(name: str) -> str:
    return re.sub(r"[^a-z0-9가-힣]", "", str(name).lower())


def _step_input_targets(dsl: dict[str, Any]) -> set[str]:
    """입력 step이 지목한 locator/필드 문자열 집합."""
    targets: set[str] = set()
    for step in resolve_dsl_steps(dsl):
        if str(step.get("action") or "").lower() not in _INPUT_STEP_ACTIONS:
            continue
        target = step.get("target") if isinstance(step.get("target"), dict) else {}
        for key in ("value", "selector", "field", "name"):
            raw = target.get(key)
            if raw:
                targets.add(str(raw).strip().lower())
    return targets


def _needs_input(dsl: dict[str, Any]) -> bool:
    return bool(dsl.get("inputs")) or bool(_step_input_targets(dsl))


_PLACEHOLDER_VALUES = {"", "없음", "n/a", "na", "-", "missing_data", "none", "null"}


def _has_request(raw: Any) -> bool:
    """생성기가 넣는 「없음」 placeholder를 실제 호출로 오인하지 않는다."""
    if not isinstance(raw, dict) or not raw:
        return False
    method = str(raw.get("method") or "").strip().lower()
    path = str(raw.get("path") or raw.get("url") or "").strip().lower()
    return bool(method and method not in _PLACEHOLDER_VALUES) or bool(
        path and path not in _PLACEHOLDER_VALUES
    )


def _expects_server_call(dsl: dict[str, Any]) -> bool:
    """시나리오가 서버 호출을 관측하려는지 — step 근거로만 판단한다."""
    if _has_request(dsl.get("request")):
        return True
    for step in resolve_dsl_steps(dsl):
        if _has_request(step.get("request")):
            return True
        if str(step.get("action") or "").lower() in {
            "submit",
            "wait_for_response",
            "verify_response",
            "verify_binding",
        }:
            return True
    return False


def _matches_target(contract_input: dict[str, Any], targets: set[str]) -> bool:
    names = {
        str(contract_input.get(key) or "").strip().lower()
        for key in ("field", "logicalName", "name")
    }
    locator = contract_input.get("locator") if isinstance(contract_input.get("locator"), dict) else {}
    locator_value = str(locator.get("value") or locator.get("selector") or "").strip().lower()
    if locator_value and locator_value in targets:
        return True
    for target in targets:
        stripped = target.lstrip("#.").strip()
        if stripped and stripped in names:
            return True
    return False


class RunPreviewService:
    def __init__(self, store: InMemoryPlatformStore) -> None:
        self.store = store
        self.env_service = EnvironmentService(store)

    def build(
        self, scenario_id: str, payload: RunPreviewRequest | None = None
    ) -> RunPreview:
        payload = payload or RunPreviewRequest()
        scenario = self.store.get_scenario(scenario_id)
        if not scenario:
            raise LookupError(f"scenario not found: {scenario_id}")

        dsl = dict(scenario.result or {})
        contract = self.store.get_contract_by_scenario(scenario_id)
        contract_body = dict(contract.result or {}) if contract else {}
        recommendation = self._recommendation(scenario_id, payload.refreshRecommendation)
        profile = self._profile(scenario_id, payload.inputProfileId)

        missing: list[str] = []
        fields = self._fields(
            dsl=dsl,
            contract_body=contract_body,
            recommendation=recommendation,
            profile=profile,
            reuse_inputs=self._reuse_inputs(payload.reuseFromRunId),
            missing=missing,
        )
        expected_apis = self._expected_apis(dsl, contract_body, missing)
        destructive, reasons = self._destructive(dsl, expected_apis)

        base_url, env = self.env_service.resolve_base_url(
            environment_id=payload.environmentId,
            project_id=scenario.projectId,
            explicit_base_url=None,
        )

        source = dsl.get("source") if isinstance(dsl.get("source"), dict) else {}
        destination = dsl.get("destination") if isinstance(dsl.get("destination"), dict) else {}
        screen_a = contract_body.get("screenA") if isinstance(contract_body.get("screenA"), dict) else {}
        screen_b = contract_body.get("screenB") if isinstance(contract_body.get("screenB"), dict) else {}
        if not source and not screen_a:
            missing.append("aScreen — 시나리오 source 화면 정보 없음")
        if not destination and not screen_b:
            missing.append("bScreen — 후속 화면 정보 없음")

        planned = [
            RunPreviewStep(
                stepId=str(step.get("id") or f"S{idx + 1}"),
                action=str(step.get("action") or ""),
                stage=_stage_for_action(str(step.get("action") or "")),
                target=_locator_text(step.get("target"))
                or (step.get("target") or {}).get("route"),
                description=_step_description(step),
            )
            for idx, step in enumerate(resolve_dsl_steps(dsl))
        ]

        return RunPreview(
            scenarioId=scenario_id,
            scenarioName=scenario.name or dsl.get("name") or "",
            scenarioVersion=str(scenario.version or "1"),
            scenarioStatus=str(scenario.status or dsl.get("status") or "DRAFT"),
            projectId=scenario.projectId,
            serviceId=scenario.serviceId,
            aScreen=RunPreviewScreen(
                screen=str(source.get("screen") or screen_a.get("name") or "missing_data"),
                route=source.get("route") or screen_a.get("route"),
            ),
            bScreen=RunPreviewScreen(
                screen=str(destination.get("screen") or screen_b.get("name") or "missing_data"),
                route=screen_b.get("route"),
                routePattern=destination.get("routePattern") or screen_b.get("routePattern"),
            ),
            expectedApis=expected_apis,
            fields=fields,
            reviewFieldCount=sum(
                1 for f in fields if f.confidence in {"review_required", "unresolved"}
            ),
            inferredFieldCount=sum(1 for f in fields if f.confidence == "inferred"),
            destructive=destructive,
            destructiveReasons=reasons,
            dataMutationAllowed=bool(getattr(env, "dataMutationAllowed", False)),
            dataMutationPolicySource=(
                "environment"
                if bool(getattr(env, "dataMutationAllowed", False))
                else "one_time_confirmation"
            ),
            plannedSteps=planned,
            recommendationId=recommendation.recommendationId if recommendation else None,
            inputProfileId=profile.profileId if profile else None,
            inputProfileVersion=profile.version if profile else None,
            inputProfileStatus=profile.status if profile else None,
            commitRefs=dict((dsl.get("sourceRefs") or {}).get("commitRefs") or {}),
            environmentId=env.id if env else payload.environmentId,
            environmentName=env.name if env else None,
            baseUrl=base_url,
            previousRun=self._previous_run(scenario_id),
            unresolved=list(dsl.get("unresolved") or []),
            missingData=sorted(set(missing)),
            generatedAt=utc_now().isoformat(),
        )

    # ------------------------------------------------------------------ helpers

    def _recommendation(self, scenario_id: str, refresh: bool):
        rec = self.store.get_recommendation_by_scenario(scenario_id)
        if rec and not refresh:
            return rec
        try:
            from app.services.input_recommend_service import InputRecommendService

            return InputRecommendService(self.store).recommend(scenario_id)
        except Exception:  # noqa: BLE001 — 추천 실패는 preview를 막지 않는다
            logger.exception("input recommendation unavailable scenario=%s", scenario_id)
            return rec

    def _profile(self, scenario_id: str, profile_id: str | None):
        if profile_id:
            return self.store.get_profile(profile_id)
        profiles = list(self.store.list_profiles(scenario_id=scenario_id))
        approved = [p for p in profiles if p.status == "APPROVED"]
        return (approved or profiles or [None])[0]

    def _reuse_inputs(self, run_id: str | None) -> dict[str, Any]:
        if not run_id:
            return {}
        run = self.store.get_run(run_id)
        return dict(run.inputs or {}) if run else {}

    def _declared_inputs(
        self,
        *,
        dsl: dict[str, Any],
        contract_body: dict[str, Any],
        defaults: dict[str, Any],
        reuse_inputs: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """이 시나리오가 실제로 채우는 입력만 남긴다.

        Contract는 저장소 전체(모든 화면)의 입력을 담고 있어, 그대로 쓰면 「index 화면
        구성 확인」에 회원가입 필드까지 확인 숙제로 붙는다. 우선순위는
        시나리오 DSL 입력 → step이 지목한 Contract 입력 → (입력 step이 있을 때만) 추천 기본값.
        """
        dsl_inputs = [
            {
                "field": item.get("name") or item.get("field"),
                "required": item.get("required", False),
                "locator": item.get("locator"),
                "reviewRequired": item.get("reviewRequired", False),
            }
            for item in (dsl.get("inputs") or [])
            if item.get("name") or item.get("field")
        ]
        if dsl_inputs:
            return dsl_inputs

        targets = _step_input_targets(dsl)
        if targets:
            # step이 지목한 입력 + Contract가 필수라고 본 입력만 남긴다. 필수 입력은 이 실행에서
            # 비어 있게 되므로 확인 대상으로 알려주는 편이 맞다.
            scoped = [
                item
                for item in (contract_body.get("inputs") or [])
                if _matches_target(item, targets) or bool(item.get("required"))
            ]
            if scoped:
                return scoped
            return [{"field": name, "required": True} for name in (defaults or reuse_inputs or {})]
        return []

    def _fields(
        self,
        *,
        dsl: dict[str, Any],
        contract_body: dict[str, Any],
        recommendation,
        profile,
        reuse_inputs: dict[str, Any],
        missing: list[str],
    ) -> list[RunPreviewField]:
        rec_body = dict(recommendation.result or {}) if recommendation else {}
        defaults = dict(rec_body.get("defaults") or {})
        by_field: dict[str, list[dict[str, Any]]] = {}
        seen_candidates: set[tuple[str, str, str]] = set()
        for cand in rec_body.get("recommendations") or []:
            field_name = str(cand.get("field") or "")
            key = (field_name, str(cand.get("value")), str(cand.get("category")))
            if key in seen_candidates:
                continue
            seen_candidates.add(key)
            by_field.setdefault(field_name, []).append(cand)
        by_field_loose: dict[str, list[dict[str, Any]]] = {}
        for field_name, items in by_field.items():
            by_field_loose.setdefault(_loose_key(field_name), []).extend(items)

        profile_case = {}
        if profile:
            cases = (profile.result or {}).get("cases") or []
            if cases:
                profile_case = dict(cases[0].get("inputs") or {})

        declared = self._declared_inputs(
            dsl=dsl, contract_body=contract_body, defaults=defaults, reuse_inputs=reuse_inputs
        )
        if not declared and _needs_input(dsl):
            missing.append("inputs — Contract·시나리오에 입력 정의가 없습니다")

        fields: list[RunPreviewField] = []
        seen_fields: set[str] = set()
        for item in declared:
            name = str(item.get("field") or item.get("name") or "")
            if not name or name in seen_fields:
                continue
            seen_fields.add(name)
            # DSL은 id(username), Contract는 라벨(Username)을 쓰는 경우가 있어 느슨히도 맞춰본다.
            candidates = by_field.get(name) or by_field_loose.get(_loose_key(name)) or []
            chosen = next(
                (c for c in candidates if c.get("selectedByDefault")),
                candidates[0] if candidates else None,
            )
            value = reuse_inputs.get(
                name, profile_case.get(name, defaults.get(name, (chosen or {}).get("value")))
            )
            synthesized = bool((chosen or {}).get("synthesized")) and value == (chosen or {}).get(
                "value"
            )
            rationale = (chosen or {}).get("rationale")
            masked_override = False
            if value in (None, ""):
                # 코드에 값 근거가 없어도 테스터에게 빈 칸을 떠넘기지 않는다.
                # 필드 정의(이름·타입·enum)로 실행 가능한 합성값을 만들고 합성임을 라벨링한다.
                made = synthesize_value(
                    {**item, "field": name},
                    scenario_id=dsl.get("scenarioId"),
                    pattern=item.get("pattern"),
                )
                if made:
                    value, rationale = made
                    synthesized = True
                    masked_override = is_sensitive_field(name)
            confidence: InputConfidence = "confirmed"
            if value in (None, ""):
                confidence = "unresolved"
            elif synthesized:
                # 코드에서 값을 찾지 못해 필드 정의로 만든 값 — 실행은 가능하고 수정도 열어둔다.
                confidence = "inferred"
            elif bool(item.get("reviewRequired")) or bool((chosen or {}).get("reviewRequired")):
                confidence = "review_required"
            elif bool((chosen or {}).get("uncertain")):
                confidence = "review_required"
            if confidence == "unresolved":
                missing.append(f"input:{name} — 값을 만들 근거(필드 정의)조차 없습니다")

            source_ref = None
            sources = (chosen or {}).get("sources") or []
            if sources:
                source_ref = str(sources[0].get("source") or "")

            fields.append(
                RunPreviewField(
                    field=name,
                    value=value,
                    displayValue="***"
                    if (masked_override and value not in (None, ""))
                    else (chosen or {}).get("displayValue")
                    or (None if value is None else str(value)),
                    required=bool(item.get("required")),
                    category=(chosen or {}).get("category"),
                    expectedPath=(chosen or {}).get("expectedPath"),
                    locator=_locator_text(item.get("locator")),
                    source="derived_synthetic" if synthesized and not source_ref else source_ref,
                    rationale=rationale,
                    confidence=confidence,
                    synthesized=synthesized,
                    masked=masked_override or bool((chosen or {}).get("masked")),
                    candidates=[
                        {
                            "value": c.get("value"),
                            "displayValue": c.get("displayValue"),
                            "category": c.get("category"),
                            "expectedPath": c.get("expectedPath"),
                            "uncertain": bool(c.get("uncertain")),
                        }
                        for c in candidates[:8]
                    ],
                )
            )
        return fields

    def _expected_apis(
        self, dsl: dict[str, Any], contract_body: dict[str, Any], missing: list[str]
    ) -> list[RunPreviewApi]:
        apis: list[RunPreviewApi] = []
        seen: set[tuple[str, str]] = set()
        for step in dsl.get("steps") or []:
            request = step.get("request") if isinstance(step.get("request"), dict) else {}
            if not request:
                continue
            method = str(request.get("method") or "missing_data").upper()
            path = str(request.get("path") or request.get("url") or "missing_data")
            if (method, path) in seen:
                continue
            seen.add((method, path))
            apis.append(
                RunPreviewApi(stepId=str(step.get("id") or ""), method=method, path=path)
            )
        if not apis:
            for action in contract_body.get("actions") or []:
                request = action.get("request") if isinstance(action.get("request"), dict) else {}
                if not request:
                    continue
                method = str(request.get("method") or "missing_data").upper()
                path = str(request.get("path") or "missing_data")
                if (method, path) in seen:
                    continue
                seen.add((method, path))
                apis.append(RunPreviewApi(stepId=str(action.get("id") or ""), method=method, path=path))
        # 화면 구성 확인처럼 서버를 부르지 않는 시나리오는 「호출 근거 없음」이 결함이 아니다.
        if not apis and _expects_server_call(dsl):
            missing.append("expectedApis — 시나리오·Contract에 Backend 호출 근거가 없습니다")
        return apis

    def _destructive(
        self, dsl: dict[str, Any], apis: list[RunPreviewApi]
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        for api in apis:
            if api.method in MUTATING_METHODS:
                reasons.append(f"{api.method} {api.path} — 상태 변경 호출")
            if any(token in api.path.lower() for token in DESTRUCTIVE_TOKENS):
                reasons.append(f"{api.path} — 파괴적 경로 토큰 포함")
        name = f"{dsl.get('name') or ''} {dsl.get('description') or ''}".lower()
        for token in DESTRUCTIVE_TOKENS:
            if token in name:
                reasons.append(f"시나리오 명칭에 '{token}' 포함")
                break
        deduped = sorted(set(reasons))
        return bool(deduped), deduped

    def _previous_run(self, scenario_id: str) -> RunPreviewPreviousRun | None:
        runs = [
            run
            for run in self.store.list_runs(scenario_id=scenario_id)
            if run.inputs
        ]
        if not runs:
            return None
        latest = sorted(runs, key=lambda r: r.createdAt or "", reverse=True)[0]
        return RunPreviewPreviousRun(
            runId=latest.runId,
            status=latest.status,
            inputs=dict(latest.inputs or {}),
            outcomeKind=latest.outcomeKind,
            createdAt=latest.createdAt,
        )

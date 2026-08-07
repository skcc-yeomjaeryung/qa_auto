from __future__ import annotations

from app.services.console_models import ScenarioGenerateRequest, TestDataScenarioRow
from app.services.console_service import ConsoleService
from app.services.repository_models import ProjectCreate, utc_now
from app.services.repository_store import InMemoryPlatformStore
from app.services.scenario_models import PipelineResult, ScenarioSummary
from app.services.scenario_service import ScenarioService


class FakePipeline:
    def __init__(self, store: InMemoryPlatformStore) -> None:
        self.store = store

    def run(self, project_id, _payload):
        self.store.save_scenario(
            ScenarioSummary(
                scenarioId="SCN-AI-BASE",
                projectId=project_id,
                graphId="IG-test",
                serviceId="login",
                name="AI 코드 근거 로그인",
                status="EXECUTABLE",
                createdAt=utc_now().isoformat(),
                result={
                    "scenarioId": "SCN-AI-BASE",
                    "name": "AI 코드 근거 로그인",
                    "source": {"route": "/login"},
                    "request": {"method": "POST", "path": "/login"},
                    "steps": [{"action": "click", "evidenceRefs": ["graph:login-submit"]}],
                },
            )
        )
        return PipelineResult(
            projectId=project_id,
            serviceId="multi",
            status="complete",
            scenarioIds=["SCN-AI-BASE"],
        )


def test_csv_generation_augments_ai_code_scenario_and_keeps_role() -> None:
    store = InMemoryPlatformStore()
    for attr in ("_projects", "_scenarios"):
        getattr(store, attr).clear()
    project = store.create_project(ProjectCreate(name="CSV AI", ownerUserId="TEST"))
    service = ConsoleService(store)
    service.pipeline = FakePipeline(store)  # type: ignore[assignment]
    result = service.generate_scenarios(
        ScenarioGenerateRequest(
            projectId=project.id,
            sourceMode="test_data_csv",
            testDataRows=[
                TestDataScenarioRow(
                    scenarioId="SCN-LOGIN-001",
                    description="관리자 로그인",
                    requestNaturalLanguage="등록된 관리자 계정으로 로그인한다",
                    responseNaturalLanguage="대시보드가 표시된다",
                    role="관리자",
                    businessPath="인증·접근/로그인 담당/관리자 로그인",
                )
            ],
        )
    )
    assert result.scenarioIds == ["SCN-LOGIN-001"]
    scenario = store.get_scenario("SCN-LOGIN-001")
    assert scenario is not None
    assert scenario.status == "REVIEW_REQUIRED"
    assert scenario.businessPath == ["인증·접근", "로그인 담당", "관리자 로그인"]
    assert scenario.assignedRole == "관리자"
    assert scenario.result["testDataSource"]["aiAugmentedFromScenarioId"] == "SCN-AI-BASE"


def test_existing_scenario_receives_three_level_business_tree() -> None:
    store = InMemoryPlatformStore()
    store._scenarios.clear()
    store.save_scenario(
        ScenarioSummary(
            scenarioId="SCN-DEPOSIT",
            serviceId="deposit",
            name="입금 등록",
            result={"request": {"path": "/deposit"}},
        )
    )
    scenario = ScenarioService(store).list_scenarios()[0]
    assert scenario.businessPath == ["금융 거래", "입금 담당", "입금 등록"]

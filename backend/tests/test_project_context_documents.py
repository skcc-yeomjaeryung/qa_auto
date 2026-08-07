from __future__ import annotations

import json
from types import SimpleNamespace

from app.services.project_context_service import ProjectContextRepository, ProjectContextService
from app.skills.project_context_discover.script.discover_context import discover
from app.skills.scenario_dsl.script.generate_dsl import generate_scenarios


def _service(monkeypatch, tmp_path):
    catalog: dict[str, object] = {}
    monkeypatch.setattr("app.services.project_context_service.kv_get", lambda key: catalog.get(key))
    monkeypatch.setattr("app.services.project_context_service.kv_set", lambda key, value: catalog.__setitem__(key, value))
    monkeypatch.setattr(
        "app.services.project_context_service.get_settings",
        lambda: SimpleNamespace(data_dir=str(tmp_path)),
    )
    monkeypatch.setattr(
        ProjectContextService,
        "_model_client",
        lambda self, *args, **kwargs: (
            SimpleNamespace(
                embed_texts=lambda _: None,
                model="test-vlm",
                vision_json=lambda **_: None,
            ),
            "test-vlm",
        ),
    )
    return ProjectContextService(ProjectContextRepository())


def test_csv_upload_extract_embedding_manifest_and_search(monkeypatch, tmp_path):
    service = _service(monkeypatch, tmp_path)
    content = (
        "테스트 시나리오 아이디,테스트 시나리오 설명,요청값,응답값\n"
        "DEPOSIT-E2E-001,입금 후 잔액과 거래내역 확인,입금액 30,잔액 증가와 신규 거래 행\n"
    ).encode("utf-8")
    queued = service.create_upload(
        project_id="PRJ-context",
        owner_user_id="TEST",
        file_name="현업_시나리오.csv",
        content_type="text/csv",
        content=content,
    )
    ready = service.process(queued.id)
    assert ready.status == "ready"
    assert ready.progress == 100
    assert ready.chunkCount == 1
    assert ready.scenarioHintCount == 1
    assert ready.indexBackend and "local_hash_embedding" in ready.indexBackend
    assert service.manifest_path("PRJ-context").is_file()
    result = service.search("PRJ-context", "TEST", "입금 잔액 거래내역")
    assert result.status == "found"
    assert result.chunks[0]["metadata"]["scenarioId"] == "DEPOSIT-E2E-001"
    assert "project_context:" in result.promptContext


def test_context_discovery_skill_found_and_not_found(monkeypatch, tmp_path):
    service = _service(monkeypatch, tmp_path)
    queued = service.create_upload(
        project_id="PRJ-skill",
        owner_user_id="TEST",
        file_name="case.csv",
        content_type="text/csv",
        content=b"scenario_id,description,input,expected\nPAYMENT-E2E-001,send payment journey,amount 10,transaction row\n",
    )
    service.process(queued.id)
    found = discover(
        {
            "projectId": "PRJ-skill",
            "projectContextManifestPath": str(service.manifest_path("PRJ-skill")),
            "scenarioContextQuery": "payment transaction",
        }
    )
    assert found["status"] == "found"
    assert found["documents"][0]["fileName"] == "case.csv"
    missing = discover(
        {
            "projectId": "PRJ-none",
            "projectContextManifestPath": str(tmp_path / "missing.json"),
        }
    )
    assert missing["status"] == "not_found"


def test_scenario_generation_joins_document_candidate_without_inventing_endpoint():
    graph = {
        "graphId": "IG-context",
        "nodes": [
            {
                "id": "screen-deposit",
                "type": "screen",
                "name": "Deposit Funds",
                "attributes": {
                    "route": "/deposit",
                    "uiElements": [{"role": "button", "name": "Deposit"}],
                },
            }
        ],
        "edges": [],
    }
    project_context = {
        "status": "found",
        "documents": [{"id": "CTX-1", "fileName": "deposit.csv", "kind": "scenario_csv", "status": "ready"}],
        "chunks": [
            {
                "id": "CTX-1:row:2",
                "documentId": "CTX-1",
                "fileName": "deposit.csv",
                "text": "입금 화면에서 금액을 입력하고 잔액 증가와 거래내역 신규 행을 확인",
                "metadata": {
                    "kind": "test_case_row",
                    "scenarioHint": "입금 후 잔액 확인",
                    "evidenceRef": "project_context:CTX-1:row:2",
                },
            }
        ],
        "guardrails": ["문서 단독 확정 금지"],
    }
    scenarios = generate_scenarios(graph, project_id="PRJ-context", project_context=project_context)
    assert scenarios
    joined = [item for item in scenarios if item.get("projectContextEvidence")]
    assert joined
    assert joined[0]["projectContextEvidence"][0]["evidenceRef"] == "project_context:CTX-1:row:2"
    assert joined[0]["supportingContext"]["status"] == "joined_candidate"
    assert not any(
        step.get("request", {}).get("path") not in (None, "", "missing_data")
        for step in joined[0].get("steps") or []
    )

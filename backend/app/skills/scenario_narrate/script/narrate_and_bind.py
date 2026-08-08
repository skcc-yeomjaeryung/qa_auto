#!/usr/bin/env python3
"""scenario_narrate / narrate_and_bind — LLM + deterministic Korean narration (D-014)."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

# Allow `python3 script.py` from skill jail and Hub ToolRuntime.
_REPO = Path(__file__).resolve().parents[5]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


_TOKEN_KO: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"customer|고객", re.I), "고객"),
    (re.compile(r"search|조회", re.I), "조회"),
    (re.compile(r"login|signin|auth", re.I), "로그인"),
    (re.compile(r"deposit|입금", re.I), "입금"),
    (re.compile(r"payment|결제|이체|송금", re.I), "송금"),
    (re.compile(r"balance|잔액", re.I), "잔액"),
    (re.compile(r"transaction|거래", re.I), "거래"),
    (re.compile(r"transfer|송금", re.I), "송금"),
    (re.compile(r"account|계좌", re.I), "계좌"),
    (re.compile(r"home|dashboard|main", re.I), "홈"),
    (re.compile(r"signup|register|가입", re.I), "가입"),
]

# ToolRuntime의 전체 제한(180초) 안에서 반드시 결정론 결과까지 작성한다.
# 모델 응답은 품질 보강이며, 일부 batch가 늦어도 Scenario DSL seed 저장을 막지 않는다.
NARRATION_LLM_BUDGET_SECONDS = 140.0
NARRATION_BATCH_TIMEOUT_SECONDS = 40.0
NARRATION_REASONING_TIMEOUT_SECONDS = 125.0
NARRATION_MIN_REMAINING_SECONDS = 6.0


def _service_label_ko(service_id: str, name: str = "") -> str:
    blob = f"{service_id} {name}"
    hits: list[str] = []
    for pat, label in _TOKEN_KO:
        if pat.search(blob) and label not in hits:
            hits.append(label)
    if hits:
        return " ".join(hits[:3])
    cleaned = service_id.replace("-", " ").replace("_", " ").strip()
    return cleaned or "API 시나리오"


def _action_title(action: str, step: dict[str, Any]) -> str:
    a = (action or "").lower()
    target = step.get("target") or {}
    req = step.get("request") or {}
    path = str(req.get("path") or target.get("route") or target.get("value") or "")
    # 세션 선행조건 단계는 왜 하는지가 제목이다 — 결정론 문장을 덮지 않는다 (D-015)
    if (
        step.get("precondition")
        or step.get("sessionCheck")
        or step.get("preserveTitle")
        or step.get("title")
    ):
        preset = str(step.get("title") or "")
        if preset:
            return preset
    if a == "assert_absent":
        sels = target.get("selectors") or []
        hint = ", ".join(str(x) for x in sels[:3]) if isinstance(sels, list) else ""
        return f"동작 후 사라져야 할 요소를 확인합니다{f' ({hint})' if hint else ''}"
    if a == "navigate":
        return f"화면으로 이동 ({path or 'missing_data'})"
    if a == "fill":
        return f"입력값을 채웁니다 ({target.get('value') or 'field'})"
    if a == "click":
        return "버튼을 눌러 다음 단계로 진행합니다"
    if a == "wait_for_response":
        method = str(req.get("method") or "")
        return f"API 응답을 기다립니다 ({method} {path})".strip()
    if a == "verify_binding":
        field = (step.get("expect") or {}).get("field") or target.get("value")
        return f"결과 바인딩을 확인합니다 ({field})"
    if a == "assert_visible":
        sels = target.get("selectors") or []
        hint = ", ".join(str(x) for x in sels[:3]) if isinstance(sels, list) else ""
        return f"UI 구성 표시를 확인합니다{f' ({hint})' if hint else ''}"
    if a == "screenshot":
        return "화면 증적을 저장합니다"
    return "테스트 단계를 수행합니다"


def _seed_request(scn: dict[str, Any]) -> dict[str, Any]:
    existing = scn.get("request")
    if isinstance(existing, dict) and existing:
        return existing
    method, path = "", ""
    for step in scn.get("steps") or []:
        req = step.get("request") or {}
        if req.get("method") or req.get("path"):
            method = str(req.get("method") or method)
            path = str(req.get("path") or path)
            break
    body: dict[str, Any] = {}
    for inp in scn.get("inputs") or []:
        if isinstance(inp, dict) and inp.get("name"):
            body[str(inp["name"])] = "reviewRequired"
    return {
        "method": method or "missing_data",
        "path": path or "missing_data",
        "headers": {"X-Scenario-ID": scn.get("scenarioId") or "missing_data"},
        "body": body or {"missing_data": True},
    }


def _seed_response(scn: dict[str, Any]) -> dict[str, Any]:
    existing = scn.get("response")
    if isinstance(existing, dict) and existing:
        return existing
    bindings: dict[str, Any] = {}
    for step in scn.get("steps") or []:
        if str(step.get("action") or "") == "verify_binding":
            field = (step.get("expect") or {}).get("field")
            if field:
                bindings[str(field)] = "reviewRequired"
    return {
        "status": "reviewRequired",
        "body": bindings or {"missing_data": True},
        "note": "기대값은 HITL 검토 전 reviewRequired",
    }


def _seed_bindings(scn: dict[str, Any]) -> dict[str, Any]:
    existing = scn.get("bindings")
    if isinstance(existing, dict) and existing:
        return existing
    out: dict[str, Any] = {}
    for step in scn.get("steps") or []:
        if str(step.get("action") or "") != "verify_binding":
            continue
        field = (step.get("expect") or {}).get("field")
        target = step.get("target") or {}
        if field:
            out[str(field)] = {
                "locator": target,
                "status": "reviewRequired",
                "evidenceRefs": list(step.get("evidenceRefs") or ["missing_data"]),
            }
    return out or {"missing_data": True}


def _deterministic_enrich(scn: dict[str, Any]) -> dict[str, Any]:
    sid = str(scn.get("serviceId") or "api")
    is_business_journey = bool(scn.get("businessJourney"))
    label = (
        str(scn.get("serviceLabelKo") or "").strip()
        if is_business_journey
        else _service_label_ko(sid, str(scn.get("name") or ""))
    ) or _service_label_ko(sid, str(scn.get("name") or ""))
    case_id = str(scn.get("caseId") or (scn.get("caseAnalysis") or {}).get("caseId") or "")
    test_type = str(scn.get("testType") or (scn.get("caseAnalysis") or {}).get("testType") or "")
    is_ui = "UI" in test_type or "-UI-" in case_id
    steps = list(scn.get("steps") or [])
    narratives = []
    for step in steps:
        narratives.append(
            {
                "stepId": step.get("id") or step.get("stepId"),
                "title": _action_title(str(step.get("action") or ""), step),
                "detail": str(step.get("note") or step.get("description") or ""),
            }
        )
        step["title"] = narratives[-1]["title"]
        if narratives[-1]["detail"] and not step.get("description"):
            step["description"] = narratives[-1]["detail"]
    enriched = dict(scn)
    enriched["serviceLabelKo"] = label
    if is_ui and case_id:
        enriched["name"] = f"{case_id} {label} 화면 구성 확인"
        enriched["description"] = (
            f"{case_id} — UI 구성 관측 초안. Pass/Fail은 HITL이 확정합니다."
        )
        enriched["categoryHints"] = ["UI", "composition"]
        enriched["evidencePlan"] = [
            "대상 화면 진입 후 DOM snapshot (agent-browser)",
            "UI 컨트롤 표시 관측 스크린샷 (agent-browser)",
        ]
    else:
        enriched["name"] = (
            str(scn.get("name") or "").strip()
            if is_business_journey
            else f"{case_id} {label}" if case_id else f"{label} 시나리오"
        )
        enriched["description"] = (
            str(scn.get("description") or "").strip()
            if is_business_journey
            else f"{label} 흐름의 실행 초안입니다. Graph Evidence 기반이며 Pass/Fail은 HITL이 확정합니다."
        )
        enriched["categoryHints"] = list(scn.get("categoryHints") or []) or [
            "E2E",
            "business_journey" if is_business_journey else "happy_path",
        ]
        enriched["evidencePlan"] = [
            "입력 직후 스크린샷 (agent-browser)",
            "후속 결과 화면 스크린샷 (agent-browser)",
            "DOM snapshot · Network 관측 요약",
        ]
    enriched["stepNarratives"] = narratives
    enriched["steps"] = steps
    # Preserve UI case request/response ("없음") — do not reseed missing_data
    if is_ui:
        enriched["request"] = scn.get("request") or {"method": "없음", "path": "없음", "body": "없음"}
        enriched["response"] = scn.get("response") or {"status": "없음", "body": "없음"}
        enriched["bindings"] = scn.get("bindings") or {"connectedApi": "없음"}
    else:
        enriched["request"] = _seed_request(scn)
        enriched["response"] = _seed_response(scn)
        enriched["bindings"] = _seed_bindings(scn)
    # Preserve caseAnalysis / caseId / testType always
    if scn.get("caseAnalysis"):
        enriched["caseAnalysis"] = scn["caseAnalysis"]
    if case_id:
        enriched["caseId"] = case_id
    if test_type:
        enriched["testType"] = test_type
    enriched["narrationMode"] = "deterministic"
    return enriched


def _merge_llm(scn: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    base = _deterministic_enrich(scn)
    if not isinstance(patch, dict):
        return base
    if patch.get("scenarioId") and patch["scenarioId"] != scn.get("scenarioId"):
        return base
    case_id = str(base.get("caseId") or "")
    is_ui = "UI" in str(base.get("testType") or "") or "-UI-" in case_id
    for key in ("serviceLabelKo", "name", "description"):
        val = patch.get(key)
        if not (isinstance(val, str) and val.strip() and "missing_data" not in val):
            continue
        # Do not let LLM erase LOGIN-UI-001 style titles
        if is_ui and key == "name" and case_id and case_id not in val:
            continue
        base[key] = val.strip()
    if is_ui and isinstance(scn.get("caseAnalysis"), dict):
        base["caseAnalysis"] = scn["caseAnalysis"]
    if isinstance(patch.get("categoryHints"), list) and patch["categoryHints"]:
        base["categoryHints"] = [str(x) for x in patch["categoryHints"] if x]
    if isinstance(patch.get("evidencePlan"), list) and patch["evidencePlan"]:
        base["evidencePlan"] = [str(x) for x in patch["evidencePlan"] if x]
    if isinstance(patch.get("unresolvedNotes"), list):
        base["unresolvedNotes"] = [str(x) for x in patch["unresolvedNotes"] if x]
    narratives = patch.get("stepNarratives")
    if isinstance(narratives, list) and narratives:
        by_id = {
            str(n.get("stepId")): n
            for n in narratives
            if isinstance(n, dict) and n.get("stepId")
        }
        steps = list(base.get("steps") or [])
        merged_n = []
        for step in steps:
            sid = str(step.get("id") or step.get("stepId") or "")
            n = by_id.get(sid)
            # 세션 선행조건·세션 확인·화면 트리거 문장은 LLM이 바꾸지 못한다 (D-015)
            if step.get("precondition") or step.get("sessionCheck") or step.get("preserveTitle"):
                merged_n.append(
                    {
                        "stepId": sid,
                        "title": step.get("title") or _action_title(str(step.get("action") or ""), step),
                        "detail": step.get("reason") or step.get("description") or "",
                    }
                )
                continue
            if n and isinstance(n.get("title"), str):
                step["title"] = n["title"]
                if isinstance(n.get("detail"), str):
                    step["description"] = n["detail"]
                merged_n.append({"stepId": sid, "title": n["title"], "detail": n.get("detail") or ""})
            else:
                merged_n.append(
                    {
                        "stepId": sid,
                        "title": step.get("title") or _action_title(str(step.get("action") or ""), step),
                        "detail": step.get("description") or "",
                    }
                )
        base["steps"] = steps
        base["stepNarratives"] = merged_n
    for key in ("request", "response", "bindings"):
        val = patch.get(key)
        if isinstance(val, dict) and val:
            # never invent endpoints — keep seed method/path if LLM emptied them
            merged = dict(base.get(key) or {})
            merged.update({k: v for k, v in val.items() if v not in (None, "")})
            base[key] = merged
    base["narrationMode"] = "llm"
    return base


def _load_scenarios(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("scenarios"), list):
        return [s for s in payload["scenarios"] if isinstance(s, dict)]
    result = payload.get("result") or {}
    if isinstance(result, dict) and isinstance(result.get("scenarios"), list):
        return [s for s in result["scenarios"] if isinstance(s, dict)]
    artifact = payload.get("artifactPath")
    if artifact:
        path = Path(str(artifact)).expanduser().resolve()
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
            if isinstance(data.get("scenarios"), list):
                return [s for s in data["scenarios"] if isinstance(s, dict)]
            if isinstance(data.get("result"), dict) and isinstance(data["result"].get("scenarios"), list):
                return [s for s in data["result"]["scenarios"] if isinstance(s, dict)]
    return []


def _try_llm(
    scenarios: list[dict[str, Any]],
    graph: dict[str, Any] | None,
    *,
    project_context: dict[str, Any] | None = None,
    execution_environment: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], str] | None:
    # 이 도구는 자유 추론보다 짧고 완전한 JSON이 우선이다. 기존 서버 프로세스가
    # ToolRuntime 변경 전에 떠 있어도 subprocess 자체에서 GPT-5 옵션을 보정한다.
    reasoning_model = os.getenv("LLM_MODEL", "").strip().lower().startswith("gpt-5")
    if reasoning_model:
        os.environ.setdefault("LLM_REASONING_EFFORT", "minimal")
        current_max = int(os.getenv("LLM_MAX_TOKENS", "0") or 0)
        os.environ["LLM_MAX_TOKENS"] = str(max(current_max, 8192))
    try:
        from app.core.llm.llm_client import get_llm_client
        from app.core.prompts import PromptCatalog
    except Exception:  # noqa: BLE001
        return None

    system, _ = PromptCatalog().render_system("scenario/narrate_bind_system.md")
    compact = []
    for scn in scenarios[:40]:
        compact.append(
            {
                "scenarioId": scn.get("scenarioId"),
                "serviceId": scn.get("serviceId"),
                "name": scn.get("name"),
                "caseVariant": scn.get("caseVariant"),
                "inputDefaults": scn.get("inputDefaults"),
                "inputStrategies": scn.get("inputStrategies"),
                "coverageMatrix": scn.get("coverageMatrix"),
                "scenarioAugmentation": scn.get("scenarioAugmentation"),
                "steps": [
                    {
                        "stepId": s.get("id"),
                        "action": s.get("action"),
                        "request": s.get("request"),
                        "target": s.get("target"),
                        "expect": s.get("expect"),
                        "evidenceRefs": s.get("evidenceRefs"),
                    }
                    for s in (scn.get("steps") or [])[:12]
                ],
                "inputs": scn.get("inputs") or [],
                "unresolved": scn.get("unresolved") or [],
                "projectContextEvidence": scn.get("projectContextEvidence") or [],
                "supportingContext": scn.get("supportingContext") or {},
            }
        )
    runtime_discovery = (graph or {}).get("runtimeDiscovery")
    runtime_summary: dict[str, Any] = {}
    if isinstance(runtime_discovery, dict):
        runtime_summary = {
            "status": runtime_discovery.get("status"),
            "mode": runtime_discovery.get("mode"),
            "pages": [
                {
                    "route": page.get("route"),
                    "visibleSignals": list(page.get("visibleSignals") or [])[:30],
                    "domControls": list(page.get("domControls") or [])[:30],
                    "safeInteractions": list(page.get("safeInteractions") or [])[:10],
                    "snapshotPath": page.get("snapshotPath"),
                    "screenshotPath": page.get("screenshotPath"),
                }
                for page in (runtime_discovery.get("pages") or [])[:8]
                if isinstance(page, dict)
            ],
            "backendContracts": list(runtime_discovery.get("backendContracts") or [])[:40],
            "missingData": list(runtime_discovery.get("missingData") or []),
        }
    client = get_llm_client()
    common_payload = {
        "graphSummary": {
            "graphId": (graph or {}).get("graphId"),
            "nodeCount": len((graph or {}).get("nodes") or []),
            "edgeCount": len((graph or {}).get("edges") or []),
            "unresolved": (graph or {}).get("unresolved") or [],
            "runtimeDiscovery": runtime_summary,
        },
        "projectContext": project_context or {},
        "executionEnvironment": execution_environment or {},
        "agenticHints": {
            "runner": "agent-browser",
            "evidenceMin": ["screenshot_after_input", "screenshot_result_screen"],
            "noPassFail": True,
        },
    }
    # A 2K output budget cannot safely hold dozens of scenario patches in one
    # JSON object. Small batches prevent truncation and preserve receipts per
    # actual provider call.
    parsed_scenarios: list[dict[str, Any]] = []
    narration_notes: list[str] = []
    deadline = time.monotonic() + NARRATION_LLM_BUDGET_SECONDS
    # GPT-5는 첫 reasoning 응답까지 시간이 더 걸리므로 한 시나리오씩 충분히
    # 기다린다. 빠른 로컬 모델은 기존 3건 batch로 처리한다.
    batch_size = 1 if reasoning_model else 3
    batch_timeout = (
        NARRATION_REASONING_TIMEOUT_SECONDS if reasoning_model else NARRATION_BATCH_TIMEOUT_SECONDS
    )
    for index in range(0, len(compact), batch_size):
        remaining = deadline - time.monotonic()
        if remaining < NARRATION_MIN_REMAINING_SECONDS:
            narration_notes.append(
                "모델 보강 시간 예산이 끝나 남은 시나리오는 코드 근거 규칙으로 완성했습니다."
            )
            break
        user = json.dumps(
            {**common_payload, "scenarios": compact[index : index + batch_size]},
            ensure_ascii=False,
        )
        # 다음 저장 단계가 실행될 여유를 남기며, 단일 provider 지연이 전체 생성을
        # 실패시키지 않도록 batch timeout을 전체 예산보다 작게 제한한다.
        parsed = client.chat_json(
            system=system,
            user=user,
            timeout_s=min(batch_timeout, max(1.0, remaining - 2.0)),
        )
        if not parsed or not isinstance(parsed.get("scenarios"), list):
            continue
        parsed_scenarios.extend(
            item for item in parsed["scenarios"] if isinstance(item, dict)
        )
        if parsed.get("narrationNotes"):
            narration_notes.append(str(parsed["narrationNotes"]))
    if not parsed_scenarios:
        return None
    by_id = {
        str(p.get("scenarioId")): p
        for p in parsed_scenarios
        if isinstance(p, dict) and p.get("scenarioId")
    }
    merged = [
        _merge_llm(scn, by_id[str(scn.get("scenarioId"))])
        if str(scn.get("scenarioId")) in by_id
        else _deterministic_enrich(scn)
        for scn in scenarios
    ]
    if narration_notes:
        for scn in merged:
            scn.setdefault("narrationNotes", " / ".join(narration_notes)[:2000])
    mode = "llm" if len(by_id) == len(scenarios) else "llm_partial"
    return merged, mode


def narrate_scenarios(
    scenarios: list[dict[str, Any]],
    *,
    graph: dict[str, Any] | None = None,
    project_context: dict[str, Any] | None = None,
    execution_environment: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    llm_out = _try_llm(
        scenarios,
        graph,
        project_context=project_context,
        execution_environment=execution_environment,
    )
    if llm_out is not None:
        return llm_out
    return [_deterministic_enrich(s) for s in scenarios], "deterministic"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8") or "{}")
    scenarios = _load_scenarios(payload)
    if not scenarios:
        out = {"ok": False, "error": "scenarios seed missing", "skill": "scenario_narrate"}
        Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print("scenarios seed missing", file=sys.stderr)
        return 2

    graph = None
    if payload.get("interactionGraph"):
        g = payload["interactionGraph"]
        graph = g if isinstance(g, dict) else None
    elif payload.get("interactionGraphPath"):
        try:
            graph = json.loads(
                Path(str(payload["interactionGraphPath"])).expanduser().resolve().read_text(encoding="utf-8")
            )
        except Exception:  # noqa: BLE001
            graph = None

    result_context = (payload.get("result") or {}).get("projectContext") if isinstance(payload.get("result"), dict) else None
    project_context = payload.get("projectContext") if isinstance(payload.get("projectContext"), dict) else (
        result_context if isinstance(result_context, dict) else {
            "projectId": payload.get("projectId"),
            "serviceId": payload.get("serviceId"),
        }
    )
    execution_environment = (
        payload.get("executionEnvironment")
        if isinstance(payload.get("executionEnvironment"), dict)
        else None
    )

    enriched, mode = narrate_scenarios(
        scenarios,
        graph=graph,
        project_context=project_context,
        execution_environment=execution_environment,
    )

    artifact_path = payload.get("artifactPath")
    if artifact_path:
        out_art = Path(str(artifact_path)).expanduser().resolve()
        out_art.parent.mkdir(parents=True, exist_ok=True)
        out_art.write_text(
            json.dumps(
                {
                    "scenarios": enriched,
                    "narrationMode": mode,
                    "executionEnvironment": execution_environment,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    output = {
        "ok": True,
        "skill": "scenario_narrate",
        "tool": "narrate_and_bind",
        "mode": mode,
        "scenarioCount": len(enriched),
        "artifactPath": str(artifact_path) if artifact_path else None,
        "serviceId": payload.get("serviceId") or "multi",
        "result": {
            "scenarios": enriched,
            "serviceId": payload.get("serviceId") or "multi",
            "narrationMode": mode,
        },
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "mode": mode, "count": len(enriched)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Pierce: project register → connect → env → analyze → scenarios → agent-browser runs."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "http://127.0.0.1:8000"
OWNER = "TEST"
REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_BOA = os.getenv(
    "QA_AUTO_BOA_WORKSPACE",
    str(REPO_ROOT / ".data" / "workspaces" / "bank-of-anthos"),
)
CYMBAL = os.getenv("QA_AUTO_CYMBAL_URL", "https://cymbal-bank.fsi.cymbal.dev/")


def req(method: str, path: str, body: dict | None = None, timeout: float = 600.0):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"detail": raw}
        return exc.code, payload


def main() -> int:
    out: dict = {"steps": []}

    code, project = req(
        "POST",
        "/api/projects",
        {
            "name": f"BoA-Cymbal-E2E-{int(time.time()) % 100000}",
            "ownerUserId": OWNER,
            "description": "tags: e2e, bank-of-anthos, cymbal\n관통 검증용 프로젝트",
        },
    )
    out["steps"].append(
        {"step": "create_project", "code": code, "id": project.get("id"), "name": project.get("name")}
    )
    print("PROJECT", code, project.get("id"), project.get("name"))
    if code not in (200, 201):
        _write(out)
        return 1
    pid = project["id"]

    code, connect = req(
        "POST",
        "/api/console/connect",
        {
            "projectId": pid,
            "ownerUserId": OWNER,
            "repositoryName": "bank-of-anthos",
            "sourceType": "local",
            "autoAnalyze": False,
            "repository": {"path": LOCAL_BOA},
        },
        timeout=300,
    )
    out["steps"].append(
        {
            "step": "connect",
            "code": code,
            "repositorySetId": connect.get("repositorySetId"),
            "message": connect.get("message"),
            "detail": connect.get("detail") if code >= 400 else None,
        }
    )
    print("CONNECT", code, connect.get("repositorySetId"), connect.get("message") or connect.get("detail"))
    if code not in (200, 201):
        _write(out)
        return 1
    set_id = connect["repositorySetId"]

    code, env = req(
        "POST",
        f"/api/projects/{pid}/environments",
        {
            "name": "Cymbal Bank (FSI)",
            "frontendBaseUrl": CYMBAL,
            "healthCheckPath": "/",
            "verifyTls": True,
            "accessNotes": "E2E pilot target",
        },
    )
    out["steps"].append(
        {"step": "create_env", "code": code, "id": env.get("id"), "url": env.get("frontendBaseUrl")}
    )
    print("ENV", code, env.get("id"), env.get("frontendBaseUrl"))
    if code not in (200, 201):
        _write(out)
        return 1
    env_id = env["id"]

    code, health = req("POST", f"/api/environments/{env_id}/health-check", {})
    out["steps"].append(
        {
            "step": "health_check",
            "code": code,
            "status": health.get("status"),
            "message": health.get("message"),
            "frontend": health.get("frontend"),
        }
    )
    print("HEALTH", code, health.get("status"), health.get("message"))

    code, analyze = req(
        "POST",
        "/api/console/bulk-analyze",
        {"projectId": pid, "repositorySetIds": [set_id]},
        timeout=600,
    )
    analysis_ids: list[str] = []
    for row in analyze.get("results") or []:
        if row.get("analysisId"):
            analysis_ids.append(str(row["analysisId"]))
        for aid in row.get("analysisIds") or []:
            analysis_ids.append(str(aid))
    analysis_ids = list(dict.fromkeys(analysis_ids))
    out["steps"].append(
        {
            "step": "analyze",
            "code": code,
            "status": analyze.get("status"),
            "message": analyze.get("message"),
            "analysisIds": analysis_ids,
            "results": analyze.get("results"),
        }
    )
    print("ANALYZE", code, analyze.get("status"), "ids", analysis_ids)

    if not analysis_ids:
        _code, catalog = req("GET", f"/api/console/analyses?projectId={pid}")
        if isinstance(catalog, list):
            analysis_ids = [str(c.get("analysisId")) for c in catalog if c.get("analysisId")]
        print("CATALOG fallback", analysis_ids)

    code, gen = req(
        "POST",
        "/api/console/generate-scenarios",
        {"projectId": pid, "analysisIds": analysis_ids},
        timeout=600,
    )
    scenario_ids = list(gen.get("scenarioIds") or [])
    out["steps"].append(
        {
            "step": "generate_scenarios",
            "code": code,
            "status": gen.get("status"),
            "scenarioIds": scenario_ids,
            "message": gen.get("message"),
            "detail": gen.get("detail") if code >= 400 else None,
            "pipelineSteps": gen.get("steps"),
        }
    )
    print(
        "SCENARIOS",
        code,
        gen.get("status"),
        len(scenario_ids),
        scenario_ids[:5],
        gen.get("message") or gen.get("detail"),
    )

    if not scenario_ids:
        _code, scn_list = req("GET", f"/api/scenarios?projectId={pid}")
        if isinstance(scn_list, list):
            scenario_ids = [str(s.get("scenarioId")) for s in scn_list if s.get("scenarioId")]
        print("SCENARIO LIST fallback", len(scenario_ids))

    runs = []
    for sid in scenario_ids[:2]:
        code, run = req(
            "POST",
            f"/api/scenarios/{sid}/runs",
            {
                "consent": True,
                "environmentId": env_id,
                "baseUrl": CYMBAL,
                "inputs": {},
                "headed": False,
            },
            timeout=600,
        )
        entry = {
            "scenarioId": sid,
            "code": code,
            "runId": run.get("runId"),
            "status": run.get("status"),
            "baseUrl": run.get("baseUrl"),
            "environmentId": run.get("environmentId"),
            "screenshotCount": run.get("screenshotCount"),
            "snapshotCount": run.get("snapshotCount"),
            "observationSummary": (run.get("observationSummary") or "")[:500],
            "outcomeKind": run.get("outcomeKind"),
            "missingData": run.get("missingData"),
            "evidenceDir": run.get("evidenceDir"),
            "detail": run.get("detail") if code >= 400 else None,
        }
        runs.append(entry)
        print(
            "RUN",
            sid,
            code,
            run.get("runId"),
            run.get("status"),
            run.get("baseUrl"),
            run.get("screenshotCount"),
            (run.get("observationSummary") or "")[:160],
        )

    out["steps"].append({"step": "runs", "runs": runs})
    out["projectId"] = pid
    out["environmentId"] = env_id
    out["repositorySetId"] = set_id
    out["scenarioIds"] = scenario_ids
    out["runIds"] = [r.get("runId") for r in runs if r.get("runId")]
    _write(out)
    return 0 if scenario_ids and out["runIds"] else 2


def _write(out: dict) -> None:
    dest_dir = REPO_ROOT / "artifacts" / "e2e"
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / "pierce-boa-cymbal-latest.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", path)


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = APP_ROOT.parent
WORKFLOW_HUB = APP_ROOT / "workflow_definitions"
SKILL_HUB = APP_ROOT / "skills"
CAPABILITY_HUB = APP_ROOT / "capability_definitions"
AGENT_SPECS = APP_ROOT / "agents" / "specs"
REPO_ROOT = BACKEND_ROOT.parent
PLAN_SCHEMA = REPO_ROOT / "docs" / "03.계약과예시" / "schemas" / "plan.schema.json"
RUN_REPORT_SCHEMA = REPO_ROOT / "docs" / "03.계약과예시" / "schemas" / "run-report.schema.json"
FRONTEND_ANALYZER_WORKER = BACKEND_ROOT / "workers" / "frontend-analyzer"
BACKEND_ANALYZER_WORKER = BACKEND_ROOT / "workers" / "backend-analyzer"
ARTIFACTS_ANALYSIS = REPO_ROOT / "artifacts" / "analysis"
ARTIFACTS_EVIDENCE = REPO_ROOT / "artifacts" / "evidence"
ARTIFACTS_REPORTS = REPO_ROOT / "artifacts" / "reports"

# QA_AUTO Backend (D-012 SDD)

```text
관리형 Hub  : Workflow YML + Skill(SKILL.md)
실행 Runtime: Router → Planner → Plan JSON → LangGraph → Tool script
```

구조 SSOT: `docs/02.아키텍처/05.BackendSDD구조.md`  
Phase: `00b` … `06.시나리오DSL.md`

```text
GET  /health
POST /api/runs/execute
POST /api/analyses/frontend|backend
POST /api/analyses/{projectId}/api-mappings
POST /api/analyses/{projectId}/interaction-graphs
POST /api/projects/{projectId}/pipeline/analyze-to-scenarios
GET  /api/scenarios · POST /api/interaction-graphs/{id}/scenarios
GET  /api/flows/by-service/{serviceId}
```


동기 CRUD·pin 은 `app/services/`.  
분석·매핑·그래프 사실 추출은 Skill Hub script (services 우회 금지).

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
export WORKSPACE_ROOT=../.data/workspaces   # optional
.venv/bin/pytest -q
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

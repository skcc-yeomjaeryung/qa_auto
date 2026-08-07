# Offline installation notes

```bash
cd frontend && npm install

cd backend && python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]'
cd packages/contracts && npm test
```

분석 대상 FE/BE는 Console에서 Local Path / GitHub URL로 연결합니다. (`sample-targets/` 내장 샘플은 제거됨)

Backend SDD (D-012): Hub + core + LangGraph.  
상세: [`02.아키텍처/05.BackendSDD구조.md`](./02.아키텍처/05.BackendSDD구조.md)

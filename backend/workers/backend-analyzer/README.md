# Backend Analyzer Worker (Python · D-010)

Spring Boot **대상** 저장소를 Python 3.12로 정적 분석한다.  
JVM JavaParser worker는 사용하지 않는다.

Hub Skill SSOT: `backend/app/skills/backend_spring_analyze/` (교보재 few-shot).  
본 패키지는 Skill script가 호출하는 **worker CLI**다.

## Workspace 입력

Phase 01 sync 결과만 읽는다 (analyzer 자체 clone 금지).

## Commands

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m app.cli health
.venv/bin/python -m app.cli analyze /abs/path/to/be \
  --out ../../../artifacts/analysis/be.json --commit <sha>
.venv/bin/pytest
```

## Layout

```text
app/cli.py
app/schemas/backend_analysis.py
app/skills/backend_spring_analyze/script/spring_parse.py  # 파서 본체
```

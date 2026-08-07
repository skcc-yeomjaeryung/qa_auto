# Logging 표준 — AI Hackerton

절대규칙 11절 · `backend/app/utils/logger.py` 공용 로거만 사용.

---

## 원칙

* 파일마다 `logging.basicConfig` / 개별 Formatter·Handler 금지
* `get_logger("nh_hackerton.<module>")` 형태의 계층 이름만 구분
* 구조화 필드는 `log_event(logger, event, **context)` JSON
* `print()` 금지

---

## 권장 필드

```text
session_id, request_id, workflow_id, skill, tool, agent
repo_ref, scenario_id, run_id
decision_summary, selected_reason, evidence_summary
confidence_score, rule_matches
missing_data_keys
```

---

## 금지 저장

```text
chain_of_thought
raw_prompt
비밀번호 · 토큰 · 비밀키
대상 저장소의 불필요 full source dump (필요 시 path/hash만)
```

---

## 감사 관점

- Planner의 Skill 선택 근거(`selected_reason`)는 요약만
- 실행 실패는 stderr 요약 + exit code
- Pass/Fail **최종 확정 이벤트는 사람 액션**으로만 기록

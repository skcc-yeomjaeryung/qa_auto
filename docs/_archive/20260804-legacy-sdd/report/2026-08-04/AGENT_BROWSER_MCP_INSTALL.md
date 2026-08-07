# 보고 — agent-browser MCP 설치 · 활용 분석

작성일: 2026-08-04  
대상: `AI_Hackertorn` (+ NH_AML FE 검증 경로)  
참고: [vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser) ·
[PyTorchKR 정리](https://discuss.pytorch.kr/t/agent-browser-vercel-ai/9125)

---

## 왜 agent-browser인가

우리가 원한 것:

```text
통합 FE: 입력값 관측 → 액션 → 후속 결과 관측 → 스크린샷 evidence
```

| 수단 | 적합? | 이유 |
|---|---|---|
| 공식 `mcp.vercel.com` | ❌ | 배포/로그/문서용. DOM·스크린샷 없음 |
| `next-devtools-mcp` | △ | Next.js 16+ 런타임만. NH_AML(Vite) 비해당 |
| **agent-browser MCP** | ✅ | open/snapshot/fill/click/screenshot 네이티브 |
| Playwright MCP | △ 보완 | 가능하나 토큰·도구면이 큼 |

agent-browser는 상호작용 요소에 `@eN` ref를 부여해 snapshot을 압축하고,
스크린샷·입력·후속 검증을 CLI/MCP로 동일하게 수행한다.

---

## 설치 결과

```text
CLI: /Users/a11123/.local/bin/agent-browser  (v0.33.2)
Chrome: 시스템 Google Chrome 사용 (CfT CDN 인증서 이슈로 managed Chrome 미다운로드)
MCP profile: core,network,react
```

Cursor 설정:

- `~/.cursor/mcp.json`
- `AI_Hackertorn/.cursor/mcp.json`

```json
"agent-browser": {
  "command": "/Users/a11123/.local/bin/agent-browser",
  "args": ["mcp", "--tools", "core,network,react"]
}
```

---

## 기동점검

| 항목 | 결과 |
|---|---|
| stdio initialize | PASS (`agent-browser` 0.33.2) |
| tools/list | 46 tools (open/snapshot/fill/click/screenshot 포함) |
| CLI open example.com | PASS |
| snapshot -i | PASS (ref=e1, e2) |
| screenshot | PASS (`/tmp/agent-browser-healthcheck/example.png`) |
| doctor launch test | PASS (CDN fail만 잔존) |

---

## 한계 (반드시 인지)

1. FE/BE **프로세스 기동**은 agent-browser 책임이 아님 → Shell로 `uvicorn` / `vite` 기동.
2. React 컴포넌트 **소스 기반 시나리오 초안**은 코드 분석 Skill 영역.
   agent-browser는 **실행 중 화면 관측·검증**을 담당.
3. Pass/Fail 최종 확정은 HITL.
4. Cursor reload 후 MCP 패널에서 `agent-browser` ready 확인 필요.
5. PATH: `~/.local/bin` (mcp.json은 절대 경로로 고정).

---

```핵심 내용
agent-browser MCP가 통합 FE DOM·스크린샷 검증의 정답 경로다.
설치·stdio 점검 PASS. 공식 Vercel MCP와 혼동하지 말 것.
```

**요약: agent-browser 설치·MCP 등록·기동점검 완료. FE 입력/후속/스크린샷 검증에 사용 가능하다.**

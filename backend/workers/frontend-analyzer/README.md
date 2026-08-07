# Frontend Analyzer Worker

Phase 02 — TypeScript/React/Next.js static analysis via **ts-morph**.

## Commands

```bash
npm install
npm run health
npm run analyze -- analyze /path/to/fe --out ../../../artifacts/analysis/fe.json --commit <sha>
npm test
```

## Result shape

See `src/types.ts` (`frontend-analysis/v1`): screens, components, inputs, events,
validations, apiCalls, routeTransitions, bindings, existingTests, unresolved, fileHashes.

## Adapters

- React / JSX host elements
- React Router `<Route>` / `navigate` / `Navigate` / `Link`
- Next.js App Router `app/**/page.tsx` · Pages Router `pages/**`
- Zod · React Hook Form register
- fetch · axios · react-query
- Playwright Test parser (Evidence only — runtime engine is agent-browser)

## Extension

Add extractors under `src/analyze.ts` or split adapters; keep
`file/line/extractor/confidence` on every fact. Unresolvable symbols go to `unresolved`.

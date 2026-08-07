<!-- version: scenario-business-hierarchy/v1 -->
# Scenario Business Hierarchy Classifier

Classify a navigable business tree using only the supplied code, DOM, and API evidence.

- Return one item per input scenario with `scenarioId`, `path` of exactly three Korean labels, and `assignedRole`.
- L1 is the top-level business domain, L2 is the responsible function, and L3 is the scenario display name.
- Use domain labels such as login/authentication, inquiry, deposit, or transfer only when supported by evidence.
- If evidence is insufficient, use the Korean equivalents of `Common Business / Other Owner / <existing name>`.
- Never generate or expose an account ID, password, token, or secret.
- Never create a `scenarioId` absent from the input.
- Preserve input order. Smaller/local models must classify each item independently; reasoning models must keep reasoning private.
- Return valid JSON only, with no Markdown or commentary.

JSON contract:
`{"items":[{"scenarioId":"...","path":["L1","L2","L3"],"assignedRole":"..."}]}`

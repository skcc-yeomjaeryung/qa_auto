# Test Data Catalog

Synthetic fixtures and Best Practice catalog entries for pilot Input recommendation.

```text
packages/test-data-catalog/
  fixtures/customers.json     # Fixture / seed customers (highest priority)
  catalog/customer-search.json  # Best Practice Catalog (lower priority)
```

Rules:

- Values are synthetic only — no real customer PII
- Identifiers such as `CUS-1001` are static approved fixtures, not random
- Catalog is source rank 5; Fixture and existing tests outrank it
- Destructive / production data is out of scope

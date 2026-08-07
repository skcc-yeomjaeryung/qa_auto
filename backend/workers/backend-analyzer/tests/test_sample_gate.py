from pathlib import Path

import pytest

from app.skills.backend_spring_analyze.script.spring_parse import analyze_workspace

SAMPLE = Path(__file__).resolve().parents[4] / "sample-targets" / "customer-service-be"


@pytest.mark.skipif(not SAMPLE.is_dir(), reason="built-in sample BE removed")
def test_sample_customer_search_gate():
    result = analyze_workspace(SAMPLE, commit_sha="sample-be")
    assert result.commitSha == "sample-be"

    eps = {(e.method, e.path) for e in result.endpoints}
    assert ("POST", "/api/customers/search") in eps

    req = next(d for d in result.requestDtos if d.name == "CustomerSearchRequest")
    assert any(f.name == "customerId" for f in req.fields)
    assert any(v.field == "customerId" and v.kind in {"NotBlank", "Pattern"} for v in result.validations)

    resp = next(d for d in result.responseDtos if d.name == "CustomerResponse")
    names = {f.name for f in resp.fields}
    assert {"customerId", "customerName", "riskLevel", "status"} <= names

    assert any(s.name in {"CustomerService", "CustomerServiceImpl"} for s in result.services)
    ep = next(e for e in result.endpoints if e.path == "/api/customers/search")
    assert ep.serviceCalls, "controller should call service"
    assert ep.evidence.file and ep.evidence.line >= 1

    assert result.exceptions or any("NOT_FOUND" in s for e in result.endpoints for s in e.statusCandidates)
    assert any(t.framework == "mockmvc" for t in result.existingTests)
    assert result.fileHashes

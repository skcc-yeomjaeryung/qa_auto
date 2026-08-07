from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    file: str
    line: int
    extractor: str
    confidence: float


class Endpoint(BaseModel):
    id: str
    method: str
    path: str
    controller: str
    handlerMethod: str
    requestDto: str | None = None
    responseDto: str | None = None
    serviceCalls: list[str] = Field(default_factory=list)
    statusCandidates: list[str] = Field(default_factory=list)
    evidence: Evidence


class DtoField(BaseModel):
    name: str
    type: str
    jsonName: str | None = None
    required: bool = False
    constraints: dict[str, Any] = Field(default_factory=dict)


class DtoType(BaseModel):
    id: str
    name: str
    kind: str
    fields: list[DtoField] = Field(default_factory=list)
    evidence: Evidence


class ValidationRule(BaseModel):
    id: str
    target: str
    field: str | None = None
    kind: str
    expression: str
    evidence: Evidence


class ServiceEntry(BaseModel):
    id: str
    name: str
    kind: str
    implementsInterface: str | None = None
    methods: list[str] = Field(default_factory=list)
    evidence: Evidence


class ExceptionHandlerEntry(BaseModel):
    id: str
    exceptionType: str
    httpStatus: str | None = None
    handlerClass: str
    evidence: Evidence


class ExistingTest(BaseModel):
    id: str
    framework: str
    file: str
    steps: list[dict[str, str]] = Field(default_factory=list)
    evidence: Evidence


class Unresolved(BaseModel):
    id: str
    kind: str
    symbol: str
    reason: str
    evidence: Evidence


class FileHash(BaseModel):
    path: str
    sha256: str


class BackendAnalysisResult(BaseModel):
    schemaVersion: str = "backend-analysis/v1"
    commitSha: str | None = None
    workspacePath: str
    analyzedAt: str
    endpoints: list[Endpoint] = Field(default_factory=list)
    requestDtos: list[DtoType] = Field(default_factory=list)
    validations: list[ValidationRule] = Field(default_factory=list)
    services: list[ServiceEntry] = Field(default_factory=list)
    responseDtos: list[DtoType] = Field(default_factory=list)
    exceptions: list[ExceptionHandlerEntry] = Field(default_factory=list)
    existingTests: list[ExistingTest] = Field(default_factory=list)
    unresolved: list[Unresolved] = Field(default_factory=list)
    fileHashes: list[FileHash] = Field(default_factory=list)

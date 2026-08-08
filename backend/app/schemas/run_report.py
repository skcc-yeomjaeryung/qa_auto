from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ReportEntity(ContractModel):
    id: str
    name: str


class ReportRequest(ContractModel):
    method: str
    path: str


class ReportScenario(ContractModel):
    id: str
    name: str
    version: str
    serviceId: str
    businessPath: list[str] = Field(default_factory=list)
    sourceRoute: str
    destinationRoute: str
    request: ReportRequest


class ReportExecution(ContractModel):
    technicalStatus: str
    startedAt: str
    endedAt: str
    durationMs: int | None = Field(default=None, ge=0)
    environmentName: str
    browserRunner: str
    progressPercent: int = Field(ge=0, le=100)
    plannedStepCount: int = Field(ge=0)
    completedStepCount: int = Field(ge=0)
    outcomeKind: str
    outcomeSummary: str


class ReportTrace(ContractModel):
    testCaseId: str
    agentTraceId: str
    backendTraceStatus: str
    repositoryUrl: str
    branch: str
    commitSha: str
    inputProfileId: str


class ReportStepObservation(ContractModel):
    stepId: str
    action: str
    status: str
    observation: str
    evidenceRefs: list[str] = Field(default_factory=list)
    missingData: list[str] = Field(default_factory=list)


class ReportAssertion(ContractModel):
    assertionId: str
    field: str
    result: str
    expected: str
    actual: str
    businessReviewRequired: bool = False
    evidenceRefs: list[str] = Field(default_factory=list)
    missingData: list[str] = Field(default_factory=list)


class ReportVerification(ContractModel):
    technicalStatus: str
    businessReviewRequired: bool
    totalCount: int = Field(ge=0)
    matchedCount: int = Field(ge=0)
    mismatchCount: int = Field(ge=0)
    missingCount: int = Field(ge=0)
    reviewRequiredCount: int = Field(ge=0)
    assertions: list[ReportAssertion] = Field(default_factory=list)


class ReportEvidenceArtifact(ContractModel):
    artifactId: str
    type: str
    label: str
    path: str
    mimeType: str
    size: int = Field(ge=0)
    sha256: str
    masked: bool
    stage: str | None = None


class ReportEvidence(ContractModel):
    evidenceId: str
    integrityStatus: str
    storageStatus: str
    screenshotCount: int = Field(ge=0)
    snapshotCount: int = Field(ge=0)
    artifactCount: int = Field(ge=0)
    maskedArtifactCount: int = Field(ge=0)
    retentionUntil: str
    downloadReady: bool
    missingData: list[str] = Field(default_factory=list)
    artifacts: list[ReportEvidenceArtifact] = Field(default_factory=list)


class ReportMissingDataDetail(ContractModel):
    code: str
    label: str
    guidance: str
    section: str


class ReportReview(ContractModel):
    finalDecision: Literal["PENDING_HUMAN_REVIEW"] = "PENDING_HUMAN_REVIEW"
    hitlRequired: Literal[True] = True
    checklist: list[str] = Field(default_factory=list)
    attentionItems: list[str] = Field(default_factory=list)
    guardrail: str


class ReportDiagnosisAction(ContractModel):
    owner: str
    action: str
    reason: str


class ReportDiagnosis(ContractModel):
    outcome: str
    headline: str
    problemSummary: str
    causeCategory: str
    causeSummary: str
    evidence: list[str] = Field(default_factory=list)
    actions: list[ReportDiagnosisAction] = Field(default_factory=list)
    retestCondition: str
    handoffMessage: str
    mode: str
    humanDecisionRequired: Literal[True] = True


class ReportLineage(ContractModel):
    sourceType: str
    sourceId: str
    description: str


class ReportGeneratedBy(ContractModel):
    agentName: Literal["REPORT AGENT"] = "REPORT AGENT"
    workflowId: Literal["wf_run_report"] = "wf_run_report"
    skillName: Literal["run_report"] = "run_report"
    traceId: str
    generatedAt: str


class ReportDownloads(ContractModel):
    html: str
    jsonUrl: str = Field(alias="json")
    evidenceZip: str


class RunReport(ContractModel):
    schemaVersion: Literal["run-report/v1"] = "run-report/v1"
    reportId: str
    runId: str
    title: str
    project: ReportEntity
    scenario: ReportScenario
    execution: ReportExecution
    trace: ReportTrace
    observations: list[ReportStepObservation] = Field(default_factory=list)
    verification: ReportVerification
    evidence: ReportEvidence
    diagnosis: ReportDiagnosis
    review: ReportReview
    sourceLineage: list[ReportLineage] = Field(default_factory=list)
    generatedBy: ReportGeneratedBy
    downloads: ReportDownloads
    missingData: list[str] = Field(default_factory=list)
    missingDataDetails: list[ReportMissingDataDetail] = Field(default_factory=list)


class RunReportGenerateRequest(ContractModel):
    force: bool = False

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


EvidenceIntegrity = Literal["complete", "partial", "corrupted"]
EvidenceStorageStatus = Literal["ready", "write_failed"]


class EvidenceArtifact(BaseModel):
    artifactId: str
    type: str
    path: str
    mimeType: str
    size: int
    sha256: str
    createdAt: str
    masked: bool = False
    stage: str | None = None
    sourcePath: str | None = None


class EvidenceManifest(BaseModel):
    evidenceId: str
    runId: str
    projectId: str | None = None
    ownerUserId: str
    scenario: dict[str, str]
    commitRefs: dict[str, str] = Field(default_factory=dict)
    inputProfile: dict[str, str]
    technicalStatus: str
    reviewStatus: str = "WAITING_FOR_REVIEW"
    correlation: dict[str, str] = Field(default_factory=dict)
    artifacts: list[EvidenceArtifact] = Field(default_factory=list)
    integrityStatus: EvidenceIntegrity
    storageStatus: EvidenceStorageStatus = "ready"
    missingData: list[str] = Field(default_factory=list)
    retentionUntil: str
    createdAt: str


class EvidenceFinalizeRequest(BaseModel):
    retentionDays: int | None = Field(default=None, ge=1, le=3650)


class EvidenceIntegrityReport(BaseModel):
    evidenceId: str
    integrityStatus: EvidenceIntegrity
    verified: int = 0
    corruptedArtifacts: list[str] = Field(default_factory=list)
    missingArtifacts: list[str] = Field(default_factory=list)

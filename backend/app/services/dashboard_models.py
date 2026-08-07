from __future__ import annotations

from pydantic import BaseModel, Field


class DashboardProjectCard(BaseModel):
    projectId: str
    name: str
    description: str | None = None
    repositoryCount: int = 0
    scenarioCount: int = 0
    runCount: int = 0
    createdAt: str | None = None
    lastActivityAt: str | None = None
    latestCommitSha: str | None = None
    analysisChangeCount: int = 0


class DashboardWeeklyPoint(BaseModel):
    date: str
    total: int = 0
    expectedMet: int = 0
    rate: float | None = None


class DashboardRecentRun(BaseModel):
    runId: str
    scenarioId: str
    scenarioName: str
    projectId: str
    projectName: str
    status: str
    outcomeKind: str | None = None
    outcomeSummary: str | None = None
    createdAt: str | None = None
    screenshotCount: int = 0
    snapshotCount: int = 0
    changedFromPrevious: bool = False


class DashboardSummary(BaseModel):
    userId: str
    projectCount: int = 0
    repositoryCount: int = 0
    scenarioCount: int = 0
    runCount: int = 0
    reviewCount: int = 0
    weeklyRate: float | None = None
    previousWeeklyRate: float | None = None
    weeklyDelta: float | None = None
    projects: list[DashboardProjectCard] = Field(default_factory=list)
    weeklySeries: list[DashboardWeeklyPoint] = Field(default_factory=list)
    recentRuns: list[DashboardRecentRun] = Field(default_factory=list)


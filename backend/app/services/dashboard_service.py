from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterable

from app.services.dashboard_models import (
    DashboardProjectCard,
    DashboardRecentRun,
    DashboardSummary,
    DashboardWeeklyPoint,
)
from app.services.repository_store import InMemoryPlatformStore


REVIEW_STATUSES = {"WAITING_FOR_REVIEW", "AUTO_FAILED", "CANCELLED"}
RATE_STATUSES = {"WAITING_FOR_REVIEW", "AUTO_FAILED"}


def _as_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _later(*values: str | None) -> str | None:
    candidates = [value for value in values if _as_datetime(value)]
    return max(candidates, key=lambda value: _as_datetime(value) or datetime.min.replace(tzinfo=timezone.utc), default=None)


def _is_expected_met(run) -> bool:
    if str(getattr(run, "outcomeKind", "") or "").lower() == "success":
        return True
    result = getattr(run, "result", {}) or {}
    verdict = result.get("verdict") if isinstance(result.get("verdict"), dict) else {}
    return str(verdict.get("verdict") or "") == "expected_met"


def _rate(runs: Iterable) -> float | None:
    terminal = [run for run in runs if str(getattr(run, "status", "") or "").upper() in RATE_STATUSES]
    if not terminal:
        return None
    return round(sum(1 for run in terminal if _is_expected_met(run)) / len(terminal) * 100, 1)


class DashboardService:
    def __init__(self, store: InMemoryPlatformStore) -> None:
        self.store = store

    def summary(self, user_id: str, *, now: datetime | None = None) -> DashboardSummary:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        projects = list(self.store.list_projects(owner_user_id=user_id))
        project_ids = {project.id for project in projects}
        project_by_id = {project.id: project for project in projects}
        scenarios = [scenario for scenario in self.store.list_scenarios() if scenario.projectId in project_ids]
        scenario_by_id = {scenario.scenarioId: scenario for scenario in scenarios}
        runs = [
            run
            for run in self.store.list_runs()
            if run.projectId in project_ids
            or (run.scenarioId in scenario_by_id and scenario_by_id[run.scenarioId].projectId in project_ids)
        ]
        analyses = [analysis for analysis in self.store.list_analyses() if analysis.projectId in project_ids]

        sets_by_project = {
            project.id: list(self.store.list_sets_for_project(project.id)) for project in projects
        }
        scenarios_by_project: dict[str, list] = defaultdict(list)
        for scenario in scenarios:
            if scenario.projectId:
                scenarios_by_project[scenario.projectId].append(scenario)
        runs_by_project: dict[str, list] = defaultdict(list)
        for run in runs:
            project_id = run.projectId or getattr(scenario_by_id.get(run.scenarioId), "projectId", None)
            if project_id:
                runs_by_project[project_id].append(run)
        analyses_by_project: dict[str, list] = defaultdict(list)
        for analysis in analyses:
            analyses_by_project[analysis.projectId].append(analysis)

        cards: list[DashboardProjectCard] = []
        for project in projects:
            project_sets = sets_by_project[project.id]
            project_scenarios = scenarios_by_project[project.id]
            project_runs = runs_by_project[project.id]
            project_analyses = sorted(
                analyses_by_project[project.id], key=lambda item: item.createdAt or "", reverse=True
            )
            repository_count = sum(len(item.repositories) for item in project_sets)
            latest_commit = next((item.commitSha for item in project_analyses if item.commitSha), None)

            grouped: dict[tuple[str | None, str], list] = defaultdict(list)
            for analysis in project_analyses:
                grouped[(analysis.repositorySetId, analysis.role)].append(analysis)
            analysis_changes = 0
            for history in grouped.values():
                if len(history) < 2:
                    continue
                latest, previous = history[0], history[1]
                if latest.commitSha != previous.commitSha or (
                    latest.screenCount,
                    latest.componentCount,
                    latest.endpointCount,
                    latest.unresolvedCount,
                ) != (
                    previous.screenCount,
                    previous.componentCount,
                    previous.endpointCount,
                    previous.unresolvedCount,
                ):
                    analysis_changes += 1

            last_activity = str(project.createdAt.isoformat())
            for item in project_scenarios:
                last_activity = _later(last_activity, item.createdAt) or last_activity
            for item in project_runs:
                last_activity = _later(last_activity, item.createdAt) or last_activity
            for item in project_sets:
                synced_at = item.lastSyncedAt.isoformat() if item.lastSyncedAt else None
                last_activity = _later(last_activity, synced_at) or last_activity

            cards.append(
                DashboardProjectCard(
                    projectId=project.id,
                    name=project.name,
                    description=project.description,
                    repositoryCount=repository_count,
                    scenarioCount=len(project_scenarios),
                    runCount=len(project_runs),
                    createdAt=project.createdAt.isoformat(),
                    lastActivityAt=last_activity,
                    latestCommitSha=latest_commit,
                    analysisChangeCount=analysis_changes,
                )
            )
        cards.sort(key=lambda card: card.lastActivityAt or "", reverse=True)

        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        current_start = day_start - timedelta(days=6)
        previous_start = current_start - timedelta(days=7)
        current_runs = [run for run in runs if (created := _as_datetime(run.createdAt)) and current_start <= created <= now]
        previous_runs = [run for run in runs if (created := _as_datetime(run.createdAt)) and previous_start <= created < current_start]
        weekly_rate = _rate(current_runs)
        previous_rate = _rate(previous_runs)
        delta = round(weekly_rate - previous_rate, 1) if weekly_rate is not None and previous_rate is not None else None

        series: list[DashboardWeeklyPoint] = []
        for offset in range(7):
            start = current_start + timedelta(days=offset)
            end = start + timedelta(days=1)
            daily = [run for run in current_runs if (created := _as_datetime(run.createdAt)) and start <= created < end]
            terminal = [run for run in daily if str(run.status or "").upper() in RATE_STATUSES]
            series.append(
                DashboardWeeklyPoint(
                    date=start.date().isoformat(),
                    total=len(terminal),
                    expectedMet=sum(1 for run in terminal if _is_expected_met(run)),
                    rate=_rate(terminal),
                )
            )

        history_by_scenario: dict[str, list] = defaultdict(list)
        for item in sorted(runs, key=lambda row: row.createdAt or "", reverse=True):
            history_by_scenario[item.scenarioId].append(item)
        changed_by_run_id: dict[str, bool] = {}
        for history in history_by_scenario.values():
            for index, item in enumerate(history):
                previous = history[index + 1] if index + 1 < len(history) else None
                changed_by_run_id[item.runId] = bool(
                    previous
                    and (
                        previous.outcomeKind != item.outcomeKind
                        or previous.status != item.status
                    )
                )

        recent_rows: list[DashboardRecentRun] = []
        for run in sorted(runs, key=lambda item: item.createdAt or "", reverse=True):
            scenario = scenario_by_id.get(run.scenarioId)
            project_id = run.projectId or getattr(scenario, "projectId", None)
            project = project_by_id.get(project_id)
            if not project or not scenario:
                continue
            recent_rows.append(
                DashboardRecentRun(
                    runId=run.runId,
                    scenarioId=run.scenarioId,
                    scenarioName=scenario.name or scenario.serviceId or run.scenarioId,
                    projectId=project.id,
                    projectName=project.name,
                    status=run.status,
                    outcomeKind=run.outcomeKind,
                    outcomeSummary=run.outcomeSummary or run.observationSummary,
                    createdAt=run.createdAt,
                    screenshotCount=run.screenshotCount,
                    snapshotCount=run.snapshotCount,
                    changedFromPrevious=changed_by_run_id.get(run.runId, False),
                )
            )
            if len(recent_rows) >= 6:
                break

        return DashboardSummary(
            userId=user_id,
            projectCount=len(projects),
            repositoryCount=sum(card.repositoryCount for card in cards),
            scenarioCount=len(scenarios),
            runCount=len(runs),
            reviewCount=sum(1 for run in runs if str(run.status or "").upper() in REVIEW_STATUSES),
            weeklyRate=weekly_rate,
            previousWeeklyRate=previous_rate,
            weeklyDelta=delta,
            projects=cards,
            weeklySeries=series,
            recentRuns=recent_rows,
        )

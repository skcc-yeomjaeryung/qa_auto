"""Health-check and resolution helpers for ExecutionEnvironment."""

from __future__ import annotations

import logging
import ssl
import time
from typing import Any
from urllib.parse import urljoin

import httpx

from app.services.environment_models import (
    CYMBAL_BANK_PRESET,
    LEGACY_LOCAL_SAMPLE_URLS,
    PILOT_SANDBOX_BASE_URL,
    EnvironmentPreset,
    ExecutionEnvironment,
    HealthCheckResult,
    HealthStatus,
    is_host_allowlisted,
    origin_from_url,
)
from app.services.repository_models import utc_now
from app.services.repository_store import InMemoryPlatformStore

logger = logging.getLogger(__name__)


def list_presets() -> list[EnvironmentPreset]:
    return [
        CYMBAL_BANK_PRESET,
        EnvironmentPreset(
            key="local-vite",
            name="Local Vite (5173)",
            frontendBaseUrl="http://127.0.0.1:5173/",
            backendBaseUrl="http://127.0.0.1:8080/",
            healthCheckPath="/",
            accessNotes="Local sample target (optional).",
        ),
        EnvironmentPreset(
            key="local-console",
            name="Local Console (3000)",
            frontendBaseUrl="http://127.0.0.1:3000/",
            backendBaseUrl="http://127.0.0.1:8000/",
            healthCheckPath="/",
            accessNotes="Platform console — not the Bank of Anthos target.",
        ),
    ]


def _tls_verify(verify_tls: bool) -> Any:
    """검증은 유지하되 OS 신뢰 저장소를 쓴다 (사내 프록시 루트 CA는 certifi에 없다)."""
    if not verify_tls:
        return False
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except Exception:  # noqa: BLE001 — certifi 기본 동작으로 폴백
        return True


def _probe_url(
    url: str,
    *,
    verify_tls: bool,
    timeout_s: float = 8.0,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with httpx.Client(
            follow_redirects=True,
            verify=_tls_verify(verify_tls),
            timeout=timeout_s,
        ) as client:
            res = client.get(url)
        latency_ms = int((time.perf_counter() - started) * 1000)
        ok = 200 <= res.status_code < 500  # 4xx still means host reachable
        return {
            "url": url,
            "reachable": True,
            "statusCode": res.status_code,
            "latencyMs": latency_ms,
            "healthy": 200 <= res.status_code < 400,
            "error": None if ok else f"unexpected status {res.status_code}",
        }
    except httpx.TimeoutException as exc:
        return {
            "url": url,
            "reachable": False,
            "statusCode": None,
            "latencyMs": int((time.perf_counter() - started) * 1000),
            "healthy": False,
            "error": f"timeout: {exc.__class__.__name__}",
        }
    except Exception as exc:  # noqa: BLE001 — surface to caller as health detail
        return {
            "url": url,
            "reachable": False,
            "statusCode": None,
            "latencyMs": int((time.perf_counter() - started) * 1000),
            "healthy": False,
            "error": f"{exc.__class__.__name__}: {exc}"[:300],
        }


def build_health_url(base_url: str, health_path: str) -> str:
    """절대 경로(`/home`)는 origin 기준 — baseUrl에 이미 진입 경로가 붙어도 중복되지 않는다."""
    path = health_path or "/"
    if path.startswith("/"):
        return f"{origin_from_url(base_url)}{path}"
    return urljoin(base_url if base_url.endswith("/") else f"{base_url}/", path)


class EnvironmentService:
    def __init__(self, store: InMemoryPlatformStore) -> None:
        self.store = store

    def health_check(self, environment_id: str) -> HealthCheckResult:
        env = self.store.get_environment(environment_id)
        if not env:
            raise LookupError(f"environment not found: {environment_id}")

        allowlisted = is_host_allowlisted(env.frontendBaseUrl)
        fe_url = build_health_url(env.frontendBaseUrl, env.healthCheckPath)
        fe = _probe_url(fe_url, verify_tls=env.verifyTls)

        be: dict[str, Any] | None = None
        if env.backendBaseUrl:
            be_path = env.healthCheckPath if env.healthCheckPath != "/" else "/health"
            be_url = build_health_url(env.backendBaseUrl, be_path)
            be = _probe_url(be_url, verify_tls=env.verifyTls)

        if fe.get("healthy"):
            status = HealthStatus.up
            message = "Frontend health check 응답을 관측했습니다."
        elif fe.get("reachable"):
            status = HealthStatus.down
            message = "Frontend에 도달했으나 healthy 범위가 아닙니다."
        else:
            status = HealthStatus.error
            message = "Frontend health check에 실패했습니다. 네트워크·VPN·URL을 확인하세요."

        if be is not None and status == HealthStatus.up and not be.get("healthy"):
            status = HealthStatus.down
            message = "Frontend은 응답했으나 Backend health가 비정상입니다."

        if not allowlisted:
            message = f"{message} (host allowlist 외 — 실행 시 추가 확인 필요)"

        detail = {"frontend": fe, "backend": be}
        updated = env.model_copy(
            update={
                "hostAllowlisted": allowlisted,
                "lastHealthStatus": status,
                "lastHealthAt": utc_now(),
                "lastHealthDetail": detail,
                "updatedAt": utc_now(),
            }
        )
        self.store.save_environment(updated)

        logger.info(
            "environment_health_check",
            extra={
                "environmentId": environment_id,
                "status": status.value,
                "frontendStatus": fe.get("statusCode"),
            },
        )

        return HealthCheckResult(
            environmentId=environment_id,
            status=status,
            frontend=fe,
            backend=be,
            checkedAt=updated.lastHealthAt or utc_now(),
            hostAllowlisted=allowlisted,
            message=message,
        )

    def resolve_base_url(
        self,
        *,
        environment_id: str | None,
        project_id: str | None,
        explicit_base_url: str | None,
    ) -> tuple[str, ExecutionEnvironment | None]:
        """Resolve run baseUrl: explicit > environmentId > project default > pilot sandbox."""
        if (
            explicit_base_url
            and explicit_base_url.strip()
            and explicit_base_url.strip() not in LEGACY_LOCAL_SAMPLE_URLS
        ):
            env = self.store.get_environment(environment_id) if environment_id else None
            return explicit_base_url.rstrip("/") + "/", env

        if environment_id:
            env = self.store.get_environment(environment_id)
            if env:
                return env.frontendBaseUrl, env

        if project_id:
            envs = self.store.list_environments(project_id)
            active = [e for e in envs if e.status.value == "active"]
            if active:
                # Prefer cymbal / most recently updated
                active.sort(key=lambda e: e.updatedAt, reverse=True)
                chosen = next(
                    (e for e in active if "cymbal-bank" in e.frontendBaseUrl),
                    active[0],
                )
                return chosen.frontendBaseUrl, chosen

        # 등록된 환경이 없을 때만: 명시 요청값 > 파일럿 샌드박스 기본값
        fallback = (explicit_base_url or "").strip() or PILOT_SANDBOX_BASE_URL
        return fallback if fallback.endswith("/") else f"{fallback}/", None

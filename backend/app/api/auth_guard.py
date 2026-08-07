"""Lightweight request auth gate for Control Plane (pilot).

Requires ``X-User-Id`` on mutating / project-scoped API calls.
Login itself remains FE localStorage (TEST/1); this prevents anonymous API use.

Set ``QA_AUTO_AUTH_GUARD=0`` to disable (pytest / local scripts).
"""
from __future__ import annotations

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Paths that stay open without user header
_PUBLIC_PREFIXES = (
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/environment-presets",
    # Phase 10: sample Spring / adapters push structured logs without Console login
    "/api/test-telemetry",
)


class UserHeaderGuard(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if os.environ.get("QA_AUTO_AUTH_GUARD", "1").lower() in {"0", "false", "off"}:
            return await call_next(request)
        path = request.url.path or ""
        if request.method in {"OPTIONS", "HEAD"}:
            return await call_next(request)
        if any(path == p or path.startswith(p + "/") for p in _PUBLIC_PREFIXES):
            return await call_next(request)
        if path == "/health":
            return await call_next(request)
        # Mutating API calls require logged-in user identity header
        if path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            user = request.headers.get("x-user-id") or request.headers.get("X-User-Id")
            if not user or not str(user).strip():
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": "X-User-Id required — 로그인 후 프로젝트를 할당하세요.",
                        "code": "AUTH_USER_REQUIRED",
                    },
                )
        return await call_next(request)

"""Execution environment models — target FE/BE URLs for real test runs."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.repository_models import utc_now

# Pilot default (CURSOR_REPOSITORY_TEST_AUTOMATION_PROMPT §1 / §21)
CYMBAL_BANK_ORIGIN = "https://cymbal-bank.fsi.cymbal.dev"
# 파일럿 샌드박스 기본 진입 화면 (Bank of Anthos home)
CYMBAL_BANK_HOME_PATH = "/home"
CYMBAL_BANK_FRONTEND_URL = f"{CYMBAL_BANK_ORIGIN}{CYMBAL_BANK_HOME_PATH}"

# 파일럿 기본 실행 대상 — 로컬 sample FE가 아니라 Cymbal Bank 샌드박스다.
# 연결 URL은 origin이다. 진입 화면(/home)은 health path로 따로 둔다.
PILOT_SANDBOX_NAME = "Pilot Sandbox"
PILOT_SANDBOX_BASE_URL = CYMBAL_BANK_ORIGIN
# 구 로컬 sample FE 기본값 — 호출자가 그대로 보내면 환경 해석으로 대체한다.
LEGACY_LOCAL_SAMPLE_URLS = frozenset(
    {
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5173/",
        "http://localhost:5173",
        "http://localhost:5173/",
    }
)

DEFAULT_HOST_ALLOWLIST = frozenset(
    {
        "127.0.0.1",
        "localhost",
        "cymbal-bank.fsi.cymbal.dev",
    }
)


class HealthStatus(str, Enum):
    unknown = "unknown"
    up = "up"
    down = "down"
    error = "error"


class BrowserEngine(str, Enum):
    """실행에 사용할 브라우저. agent-browser 실행기는 chrome/chromium 계열만 구동한다."""

    chrome = "chrome"
    chromium = "chromium"
    edge = "edge"


# 실행기가 실제로 띄울 수 있는 엔진 (그 외 값은 실행 관측에 미지원으로 남긴다)
RUNNABLE_BROWSERS = frozenset({BrowserEngine.chrome, BrowserEngine.chromium, BrowserEngine.edge})

# 파일럿 샌드박스(Bank of Anthos 데모) 공개 데모 계정 — 실고객 계정이 아니다.
PILOT_SANDBOX_LOGIN_ID = "testuser"
PILOT_SANDBOX_LOGIN_PASSWORD = "bankofanthos"


class EnvironmentStatus(str, Enum):
    active = "active"
    disabled = "disabled"
    draft = "draft"


def _normalize_base_url(value: str) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError("URL이 비어 있습니다")
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("URL은 http 또는 https 만 허용됩니다")
    if not parsed.netloc:
        raise ValueError("유효한 host가 없습니다")
    path = parsed.path or "/"
    if path in ("", "/"):
        return f"{parsed.scheme}://{parsed.netloc}/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"

def origin_from_url(url: str) -> str:
    """Scheme+host only — absolute route(`/home`)를 붙일 기준점."""
    raw = url.strip()
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    if not parsed.netloc:
        return url.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}"


def host_from_url(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"http://{url}")
    return (parsed.hostname or "").lower()


def is_host_allowlisted(url: str, allowlist: frozenset[str] = DEFAULT_HOST_ALLOWLIST) -> bool:
    host = host_from_url(url)
    if not host:
        return False
    if host in allowlist:
        return True
    # Permit private/local IPs for pilot sandboxes
    if host.startswith("192.168.") or host.startswith("10."):
        return True
    return False


class ExecutionEnvironmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    frontendBaseUrl: str = Field(min_length=1, max_length=500)
    backendBaseUrl: str | None = Field(default=None, max_length=500)
    healthCheckPath: str = Field(default="/", max_length=200)
    apiBasePath: str | None = Field(default=None, max_length=200)
    https: bool | None = None
    verifyTls: bool = True
    proxy: str | None = Field(default=None, max_length=500)
    accessNotes: str | None = Field(default=None, max_length=1_000)
    testAccountRefKey: str | None = Field(default=None, max_length=120)
    # 연결 브라우저 · 연결 계정 — 실제 로그인 관통 실행에 필요한 최소 정보
    browser: BrowserEngine = BrowserEngine.chrome
    loginId: str | None = Field(default=None, max_length=120)
    loginRole: str = Field(default="관리자", min_length=1, max_length=80)
    # 로그인 비밀번호는 응답·로그·증적에 실리지 않는다 (write-only)
    loginPassword: str | None = Field(default=None, max_length=200, exclude=True)
    # Never accept raw secrets
    testAccountSecret: str | None = Field(default=None, exclude=True)

    @field_validator("frontendBaseUrl")
    @classmethod
    def validate_fe_url(cls, value: str) -> str:
        return _normalize_base_url(value)

    @field_validator("backendBaseUrl")
    @classmethod
    def validate_be_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return _normalize_base_url(value)

    @model_validator(mode="after")
    def derive_https(self) -> ExecutionEnvironmentCreate:
        if self.https is None:
            self.https = self.frontendBaseUrl.startswith("https://")
        if self.testAccountSecret:
            # Accept once then drop — only ref key may persist
            self.testAccountSecret = None
        return self


class ExecutionEnvironmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    frontendBaseUrl: str | None = Field(default=None, max_length=500)
    backendBaseUrl: str | None = Field(default=None, max_length=500)
    healthCheckPath: str | None = Field(default=None, max_length=200)
    apiBasePath: str | None = Field(default=None, max_length=200)
    https: bool | None = None
    verifyTls: bool | None = None
    proxy: str | None = Field(default=None, max_length=500)
    accessNotes: str | None = Field(default=None, max_length=1_000)
    testAccountRefKey: str | None = Field(default=None, max_length=120)
    browser: BrowserEngine | None = None
    loginId: str | None = Field(default=None, max_length=120)
    loginRole: str | None = Field(default=None, min_length=1, max_length=80)
    loginPassword: str | None = Field(default=None, max_length=200, exclude=True)
    status: EnvironmentStatus | None = None

    @field_validator("frontendBaseUrl")
    @classmethod
    def validate_fe_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_base_url(value)

    @field_validator("backendBaseUrl")
    @classmethod
    def validate_be_url(cls, value: str | None) -> str | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return _normalize_base_url(value)


class ExecutionEnvironment(BaseModel):
    id: str
    projectId: str
    name: str
    frontendBaseUrl: str
    backendBaseUrl: str | None = None
    healthCheckPath: str = "/"
    apiBasePath: str | None = None
    https: bool = False
    verifyTls: bool = True
    proxy: str | None = None
    accessNotes: str | None = None
    testAccountRefKey: str | None = None
    browser: BrowserEngine = BrowserEngine.chrome
    loginId: str | None = None
    loginRole: str = "관리자"
    # 비밀번호 값은 저장 모델에 담지 않는다. 등록 여부만 노출한다.
    hasLoginSecret: bool = False
    hostAllowlisted: bool = False
    lastHealthStatus: HealthStatus = HealthStatus.unknown
    lastHealthAt: datetime | None = None
    lastHealthDetail: dict[str, Any] | None = None
    status: EnvironmentStatus = EnvironmentStatus.active
    version: int = 1
    createdAt: datetime = Field(default_factory=utc_now)
    updatedAt: datetime = Field(default_factory=utc_now)


class ExecutionAccountCreate(BaseModel):
    label: str = Field(default="테스트 계정", min_length=1, max_length=80)
    loginId: str = Field(min_length=1, max_length=120)
    loginPassword: str = Field(min_length=1, max_length=200, exclude=True)
    role: str = Field(default="관리자", min_length=1, max_length=80)
    isDefault: bool = False


class ExecutionAccount(BaseModel):
    id: str
    environmentId: str
    label: str
    loginId: str
    role: str
    hasSecret: bool = True
    isDefault: bool = False
    createdAt: datetime = Field(default_factory=utc_now)


class HealthCheckResult(BaseModel):
    environmentId: str
    status: HealthStatus
    frontend: dict[str, Any] = Field(default_factory=dict)
    backend: dict[str, Any] | None = None
    checkedAt: datetime = Field(default_factory=utc_now)
    hostAllowlisted: bool = False
    message: str = ""


class EnvironmentPreset(BaseModel):
    key: str
    name: str
    frontendBaseUrl: str
    backendBaseUrl: str | None = None
    healthCheckPath: str = "/"
    accessNotes: str | None = None
    browser: BrowserEngine = BrowserEngine.chrome
    loginId: str | None = None
    # 프리셋이 제안하는 데모 계정 비밀번호 (공개 데모 계정만)
    loginPassword: str | None = None


CYMBAL_BANK_PRESET = EnvironmentPreset(
    key="cymbal-bank",
    name="Pilot Sandbox (Cymbal Bank)",
    frontendBaseUrl=CYMBAL_BANK_ORIGIN,
    backendBaseUrl=None,
    healthCheckPath=CYMBAL_BANK_HOME_PATH,
    accessNotes="파일럿 기본 대상 (Bank of Anthos 데모). 공개 데모 계정으로 로그인합니다.",
    browser=BrowserEngine.chrome,
    loginId=PILOT_SANDBOX_LOGIN_ID,
    loginPassword=PILOT_SANDBOX_LOGIN_PASSWORD,
)

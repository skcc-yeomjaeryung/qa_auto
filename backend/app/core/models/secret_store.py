from __future__ import annotations

import hmac
import os
from typing import Protocol

import keyring
from keyring.errors import KeyringError, PasswordDeleteError


KEYCHAIN_SERVICE = "qa-auto-model-api-key"


class ModelSecretStore(Protocol):
    def get(self, model_profile_id: str) -> str | None: ...

    def set(self, model_profile_id: str, secret: str) -> None: ...

    def delete(self, model_profile_id: str) -> None: ...


class MemoryModelSecretStore:
    """Test/fallback store. Production macOS uses the login Keychain instead."""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = values if values is not None else {}

    def get(self, model_profile_id: str) -> str | None:
        return self.values.get(model_profile_id)

    def set(self, model_profile_id: str, secret: str) -> None:
        self.values[model_profile_id] = secret

    def delete(self, model_profile_id: str) -> None:
        self.values.pop(model_profile_id, None)


class SystemKeyringModelSecretStore:
    """Persist model credentials in the operating-system credential vault."""

    def get(self, model_profile_id: str) -> str | None:
        try:
            return keyring.get_password(KEYCHAIN_SERVICE, model_profile_id)
        except KeyringError:
            return None

    def set(self, model_profile_id: str, secret: str) -> None:
        if not secret:
            self.delete(model_profile_id)
            return
        try:
            keyring.set_password(KEYCHAIN_SERVICE, model_profile_id, secret)
        except KeyringError as exc:
            raise RuntimeError("시스템 Keychain에 API Key를 저장하지 못했습니다.") from exc
        stored = self.get(model_profile_id)
        if stored is None or not hmac.compare_digest(stored, secret):
            raise RuntimeError("시스템 Keychain 저장값을 확인하지 못했습니다.")

    def delete(self, model_profile_id: str) -> None:
        try:
            keyring.delete_password(KEYCHAIN_SERVICE, model_profile_id)
        except (KeyringError, PasswordDeleteError):
            return


def build_model_secret_store() -> ModelSecretStore:
    forced = os.getenv("QA_AUTO_MODEL_SECRET_STORE", "").strip().lower()
    under_test = bool(os.getenv("PYTEST_CURRENT_TEST"))
    if not under_test and forced != "memory":
        return SystemKeyringModelSecretStore()
    return MemoryModelSecretStore()

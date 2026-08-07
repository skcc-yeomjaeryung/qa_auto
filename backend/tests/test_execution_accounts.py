from __future__ import annotations

from app.services.environment_models import ExecutionAccountCreate, ExecutionEnvironmentCreate
from app.services.repository_models import ProjectCreate
from app.services.repository_store import InMemoryPlatformStore


def test_environment_accounts_keep_role_and_secret_out_of_response() -> None:
    store = InMemoryPlatformStore()
    for attr in (
        "_projects",
        "_environments",
        "_environment_accounts",
        "_env_secrets",
        "_env_account_secrets",
    ):
        getattr(store, attr).clear()
    project = store.create_project(ProjectCreate(name="account roles", ownerUserId="TEST"))
    environment = store.create_environment(
        project.id,
        ExecutionEnvironmentCreate(
            name="DEV",
            frontendBaseUrl="http://127.0.0.1:5173",
            loginId="admin",
            loginPassword="secret-admin",
            loginRole="관리자",
        ),
    )
    default = store.list_execution_accounts(environment.id)
    assert default[0].role == "관리자"
    assert "secret-admin" not in default[0].model_dump_json()

    viewer = store.create_execution_account(
        environment.id,
        ExecutionAccountCreate(
            label="조회 계정",
            loginId="viewer",
            loginPassword="secret-viewer",
            role="조회 담당",
        ),
    )
    assert viewer.role == "조회 담당"
    assert store.get_execution_account_secret(viewer.id) == "secret-viewer"
    assert "secret-viewer" not in viewer.model_dump_json()

    rehydrated = InMemoryPlatformStore()
    assert rehydrated.get_execution_account(viewer.id) is None
    assert rehydrated.get_execution_account_secret(viewer.id) is None

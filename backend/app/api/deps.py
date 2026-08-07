from functools import lru_cache

from app.services.repository_store import InMemoryPlatformStore
from app.services.repository_sync import RepositorySyncService


@lru_cache
def get_platform_store() -> InMemoryPlatformStore:
    return InMemoryPlatformStore()


def get_sync_service() -> RepositorySyncService:
    return RepositorySyncService(get_platform_store())

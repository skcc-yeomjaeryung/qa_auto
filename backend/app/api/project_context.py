from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request

from app.api.deps import get_platform_store
from app.services.project_context_models import ProjectContextDocument, ProjectContextSearchResult
from app.services.project_context_service import ProjectContextService
from app.services.repository_store import InMemoryPlatformStore


router = APIRouter(prefix="/api/projects/{project_id}/context-documents", tags=["project-context"])


def _user(x_user_id: str | None) -> str:
    user = str(x_user_id or "").strip()
    if not user:
        raise HTTPException(status_code=401, detail="로그인 사용자 정보가 필요합니다")
    return user


def _assert_project(project_id: str, user_id: str, store: InMemoryPlatformStore) -> None:
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    if project.ownerUserId and project.ownerUserId != user_id:
        raise HTTPException(status_code=403, detail="할당된 프로젝트의 자료만 관리할 수 있습니다")


@router.get("", response_model=list[ProjectContextDocument])
def list_documents(
    project_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> list[ProjectContextDocument]:
    user = _user(x_user_id)
    _assert_project(project_id, user, store)
    return ProjectContextService().list_documents(project_id, user)


@router.post("", response_model=ProjectContextDocument, status_code=202)
async def upload_document(
    project_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    file_name: str = Query(alias="fileName"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> ProjectContextDocument:
    user = _user(x_user_id)
    _assert_project(project_id, user, store)
    service = ProjectContextService()
    try:
        document = service.create_upload(
            project_id=project_id,
            owner_user_id=user,
            file_name=file_name,
            content_type=request.headers.get("content-type") or "application/octet-stream",
            content=await request.body(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(service.process, document.id)
    return document


@router.delete("/{document_id}", status_code=204)
def delete_document(
    project_id: str,
    document_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> None:
    user = _user(x_user_id)
    _assert_project(project_id, user, store)
    if not ProjectContextService().delete(project_id, document_id, user):
        raise HTTPException(status_code=404, detail="context document not found")


@router.get("/search", response_model=ProjectContextSearchResult)
def search_context(
    project_id: str,
    query: str = Query(default=""),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    store: InMemoryPlatformStore = Depends(get_platform_store),
) -> ProjectContextSearchResult:
    user = _user(x_user_id)
    _assert_project(project_id, user, store)
    return ProjectContextService().search(project_id, user, query)


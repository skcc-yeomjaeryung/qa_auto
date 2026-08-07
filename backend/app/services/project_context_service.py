from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import math
import re
import shutil
import struct
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree

from app.core.bootstrap import get_runtime
from app.core.llm.llm_client import LlmClient
from app.core.models import ModelRequirement, resolve_project_model_binding, resolve_project_policy
from app.core.prompts import PromptCatalog
from app.services.project_context_models import ProjectContextDocument, ProjectContextSearchResult
from app.services.sqlite_persist import kv_get, kv_set
from app.utils.config import get_settings


CATALOG_KEY = "project_context_documents_v1"
MAX_FILE_BYTES = 30 * 1024 * 1024
ALLOWED_SUFFIXES = {".csv", ".pptx", ".ppt"}
_catalog_lock = Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_name(value: str) -> str:
    name = Path(value or "upload").name
    return re.sub(r"[^0-9A-Za-z가-힣._() -]+", "_", name)[:180] or "upload"


def _normalize(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", " ", str(value or "").lower()).strip()


def _tokens(value: str) -> set[str]:
    return {token for token in _normalize(value).split() if len(token) > 1}


def _hash_embedding(text: str, dimensions: int = 384) -> list[float]:
    vector = [0.0] * dimensions
    for token in _tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for offset in range(0, 24, 4):
            index = int.from_bytes(digest[offset : offset + 4], "big") % dimensions
            vector[index] += -1.0 if digest[offset] & 1 else 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


class ProjectContextRepository:
    def _all(self) -> list[dict[str, Any]]:
        raw = kv_get(CATALOG_KEY)
        return list(raw) if isinstance(raw, list) else []

    def list(self, project_id: str | None = None) -> list[ProjectContextDocument]:
        rows = [ProjectContextDocument.model_validate(item) for item in self._all()]
        if project_id:
            rows = [item for item in rows if item.projectId == project_id]
        return sorted(rows, key=lambda item: item.createdAt, reverse=True)

    def get(self, document_id: str) -> ProjectContextDocument | None:
        return next((item for item in self.list() if item.id == document_id), None)

    def save(self, document: ProjectContextDocument) -> ProjectContextDocument:
        with _catalog_lock:
            rows = self._all()
            payload = document.model_dump(mode="json")
            for index, current in enumerate(rows):
                if current.get("id") == document.id:
                    rows[index] = payload
                    break
            else:
                rows.append(payload)
            kv_set(CATALOG_KEY, rows)
        return document

    def delete(self, document_id: str) -> bool:
        with _catalog_lock:
            rows = self._all()
            next_rows = [item for item in rows if item.get("id") != document_id]
            if len(next_rows) == len(rows):
                return False
            kv_set(CATALOG_KEY, next_rows)
            return True


class ProjectContextService:
    def __init__(self, repository: ProjectContextRepository | None = None) -> None:
        self.repository = repository or ProjectContextRepository()
        self.root = Path(get_settings().data_dir) / "project-context"
        self.root.mkdir(parents=True, exist_ok=True)

    def list_documents(self, project_id: str, owner_user_id: str) -> list[ProjectContextDocument]:
        return [item for item in self.repository.list(project_id) if item.ownerUserId == owner_user_id]

    def create_upload(
        self,
        *,
        project_id: str,
        owner_user_id: str,
        file_name: str,
        content_type: str,
        content: bytes,
    ) -> ProjectContextDocument:
        safe_name = _safe_name(file_name)
        suffix = Path(safe_name).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise ValueError("CSV 또는 PPT/PPTX 파일만 업로드할 수 있습니다.")
        if not content:
            raise ValueError("빈 파일은 업로드할 수 없습니다.")
        if len(content) > MAX_FILE_BYTES:
            raise ValueError("파일은 30MB 이하만 업로드할 수 있습니다.")
        document_id = f"CTX-{uuid4().hex[:12]}"
        kind = "scenario_csv" if suffix == ".csv" else "design_ppt"
        created = _now()
        document = ProjectContextDocument(
            id=document_id,
            projectId=project_id,
            ownerUserId=owner_user_id,
            fileName=safe_name,
            contentType=content_type or "application/octet-stream",
            kind=kind,
            status="queued",
            progress=5,
            sizeBytes=len(content),
            createdAt=created,
            updatedAt=created,
        )
        document_dir = self._document_dir(project_id, document_id)
        document_dir.mkdir(parents=True, exist_ok=True)
        (document_dir / safe_name).write_bytes(content)
        self.repository.save(document)
        self._write_manifest(project_id)
        return document

    def process(self, document_id: str) -> ProjectContextDocument:
        document = self.repository.get(document_id)
        if not document:
            raise LookupError("context document not found")
        document_dir = self._document_dir(document.projectId, document.id)
        source = document_dir / document.fileName
        runtime = get_runtime()
        runtime.events.record(
            trace_id=document.id,
            event_type="workflow_started",
            workflow_id="project_context_ingest",
            project_id=document.projectId,
            status="running",
            summary=f"{document.fileName} 보강 자료 처리를 시작했습니다.",
            details={"kind": document.kind, "sizeBytes": document.sizeBytes},
        )
        try:
            document.status = "extracting"
            document.progress = 24
            document.updatedAt = _now()
            self.repository.save(document)
            if document.kind == "scenario_csv":
                chunks, summary, missing = self._extract_csv(source, document)
                mode = "structured_csv"
            else:
                chunks, summary, missing = self._extract_presentation(source, document)
                mode = "pptx_text+vlm_ocr"
            document.status = "embedding"
            document.progress = 68
            document.summary = summary
            document.missingData = missing
            document.processingMode = mode
            document.updatedAt = _now()
            self.repository.save(document)
            index_backend = self._embed_and_index(document, chunks)
            (document_dir / "chunks.json").write_text(
                json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            document.chunkCount = len(chunks)
            document.scenarioHintCount = sum(
                1 for item in chunks if item.get("metadata", {}).get("scenarioHint")
            )
            document.indexBackend = index_backend
            document.status = "partial" if missing else "ready"
            document.progress = 100
            document.updatedAt = _now()
            self.repository.save(document)
            self._write_manifest(document.projectId)
            runtime.events.record(
                trace_id=document.id,
                event_type="workflow_completed",
                workflow_id="project_context_ingest",
                project_id=document.projectId,
                status="complete",
                summary=f"보강 자료 {document.fileName} 처리가 완료되었습니다.",
                details={
                    "status": document.status,
                    "chunkCount": document.chunkCount,
                    "indexBackend": document.indexBackend,
                },
            )
            return document
        except Exception as exc:  # noqa: BLE001 - 상태를 UI에서 확인할 수 있어야 한다
            document.status = "error"
            document.progress = 100
            document.error = str(exc)[:1000]
            document.updatedAt = _now()
            self.repository.save(document)
            self._write_manifest(document.projectId)
            runtime.events.record(
                trace_id=document.id,
                event_type="workflow_failed",
                workflow_id="project_context_ingest",
                project_id=document.projectId,
                status="failed",
                summary=f"보강 자료 {document.fileName} 처리 중 확인이 필요합니다.",
                details={"errorType": type(exc).__name__},
            )
            return document

    def _model_client(
        self,
        project_id: str,
        requirement: ModelRequirement,
        *,
        trace_id: str,
    ) -> tuple[LlmClient | None, str | None]:
        runtime = get_runtime()
        role, preferred_profile_id = resolve_project_model_binding(project_id, requirement)
        policy = resolve_project_policy(project_id)
        decision = runtime.model_selector.select(
            requirement,
            policy,
            preferred_model_profile_id=preferred_profile_id,
            selection_role=role,
        )
        runtime.events.record(
            trace_id=trace_id,
            event_type="model_selected",
            workflow_id="project_context_ingest",
            project_id=project_id,
            status="complete" if decision.route == "model" else "warning",
            summary=decision.decisionSummary,
            details=decision.model_dump(),
        )
        if decision.route != "model" or not decision.selectedModelProfileId:
            return None, None
        profile = runtime.models.require(decision.selectedModelProfileId)
        secret = runtime.models.secret(profile.id)
        if profile.deploymentType == "external" and not secret:
            return None, profile.displayName
        settings = get_settings()

        def record_receipt(receipt: dict[str, Any]) -> None:
            outcome = str(receipt.get("status") or "unknown")
            runtime.events.record(
                trace_id=trace_id,
                event_type=(
                    "model_invocation_completed"
                    if outcome == "completed"
                    else "model_invocation_failed"
                ),
                workflow_id="project_context_ingest",
                project_id=project_id,
                status="complete" if outcome == "completed" else "failed",
                summary=f"{profile.displayName} 실제 호출 {outcome}",
                details={
                    **receipt,
                    "modelProfileId": profile.id,
                    "displayName": profile.displayName,
                    "selectionRole": role,
                },
            )

        return (
            LlmClient(
                base_url=f"{str(profile.endpoint).rstrip('/')}{profile.apiBasePath}",
                model=profile.modelId,
                embedding_model=profile.modelId,
                api_key=secret or "local",
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                enabled=True,
                receipt_callback=record_receipt,
            ),
            profile.displayName,
        )

    def delete(self, project_id: str, document_id: str, owner_user_id: str) -> bool:
        document = self.repository.get(document_id)
        if not document or document.projectId != project_id or document.ownerUserId != owner_user_id:
            return False
        if not self.repository.delete(document_id):
            return False
        target = self._document_dir(project_id, document_id)
        if target.exists():
            shutil.rmtree(target)
        self._write_manifest(project_id)
        return True

    def manifest_path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / "manifest.json"

    def search(self, project_id: str, owner_user_id: str, query: str, limit: int = 8) -> ProjectContextSearchResult:
        documents = [
            item for item in self.list_documents(project_id, owner_user_id)
            if item.status in {"ready", "partial"}
        ]
        if not documents:
            return ProjectContextSearchResult(status="not_found", projectId=project_id, query=query)
        query_tokens = _tokens(query)
        candidates: list[tuple[float, dict[str, Any]]] = []
        for document in documents:
            chunks_path = self._document_dir(project_id, document.id) / "chunks.json"
            if not chunks_path.is_file():
                continue
            for chunk in json.loads(chunks_path.read_text(encoding="utf-8")):
                text = str(chunk.get("text") or "")
                overlap = len(query_tokens & _tokens(text))
                score = overlap / max(1, len(query_tokens))
                if score > 0 or not query_tokens:
                    candidates.append((score, {**chunk, "documentId": document.id, "fileName": document.fileName}))
        candidates.sort(key=lambda item: (item[0], len(str(item[1].get("text") or ""))), reverse=True)
        chunks = [{**item, "score": round(score, 4)} for score, item in candidates[:limit]]
        if not chunks:
            chunks = [
                {
                    "documentId": item.id,
                    "fileName": item.fileName,
                    "text": item.summary or item.fileName,
                    "metadata": {"kind": item.kind},
                    "score": 0.0,
                }
                for item in documents[:limit]
            ]
        prompt_context = "\n\n".join(
            f"[project_context:{item['documentId']}] {item['fileName']}\n{item['text']}" for item in chunks
        )[:16000]
        return ProjectContextSearchResult(
            status="found",
            projectId=project_id,
            query=query,
            documents=[item.model_dump(mode="json") for item in documents],
            chunks=chunks,
            promptContext=prompt_context,
            guardrails=[
                "보조 문서는 테스트 의도 후보이며 코드 Graph·DOM·API 근거와 결합한 내용만 실행 단계로 확정한다.",
                "문서와 코드가 충돌하면 unresolved로 남기고 사람이 확인한다.",
                "Secret·개인정보·근거 없는 selector/endpoint/expected value를 LLM이 생성하지 않는다.",
            ],
        )

    def _extract_csv(
        self, source: Path, document: ProjectContextDocument
    ) -> tuple[list[dict[str, Any]], str, list[str]]:
        raw = source.read_bytes()
        decoded = None
        for encoding in ("utf-8-sig", "cp949", "utf-8"):
            try:
                decoded = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            raise ValueError("CSV 인코딩을 읽을 수 없습니다. UTF-8 또는 CP949로 저장하세요.")
        reader = csv.DictReader(io.StringIO(decoded))
        if not reader.fieldnames:
            raise ValueError("CSV 헤더가 없습니다.")
        aliases = {
            "scenarioId": ("테스트 시나리오 아이디", "시나리오 아이디", "scenario_id", "scenarioid", "id"),
            "description": ("테스트 시나리오 설명", "시나리오 설명", "description", "name"),
            "request": ("요청값", "request", "input", "requestNaturalLanguage"),
            "response": ("응답값", "response", "output", "expected", "responseNaturalLanguage"),
        }
        normalized_headers = {_normalize(header): header for header in reader.fieldnames}

        def value(row: dict[str, str], key: str) -> str:
            for alias in aliases[key]:
                original = normalized_headers.get(_normalize(alias))
                if original and row.get(original):
                    return str(row[original]).strip()
            return ""

        chunks: list[dict[str, Any]] = []
        for row_number, row in enumerate(reader, start=2):
            scenario_id = value(row, "scenarioId")
            description = value(row, "description")
            request = value(row, "request")
            response = value(row, "response")
            if not any((scenario_id, description, request, response)):
                continue
            text = "\n".join(
                part for part in (
                    f"테스트 시나리오 ID: {scenario_id}" if scenario_id else "",
                    f"설명: {description}" if description else "",
                    f"요청/입력: {request}" if request else "",
                    f"기대 응답/결과: {response}" if response else "",
                ) if part
            )
            chunks.append(
                {
                    "id": f"{document.id}:row:{row_number}",
                    "text": text,
                    "metadata": {
                        "kind": "test_case_row",
                        "row": row_number,
                        "scenarioId": scenario_id or None,
                        "scenarioHint": description or scenario_id or None,
                        "description": description or None,
                        "request": request or None,
                        "response": response or None,
                        "evidenceRef": f"project_context:{document.id}:row:{row_number}",
                    },
                }
            )
        if not chunks:
            raise ValueError("CSV에 읽을 수 있는 테스트 시나리오 행이 없습니다.")
        return chunks, f"정형 테스트 시나리오 {len(chunks)}건을 읽었습니다.", []

    def _extract_presentation(
        self, source: Path, document: ProjectContextDocument
    ) -> tuple[list[dict[str, Any]], str, list[str]]:
        if source.suffix.lower() == ".ppt":
            raise ValueError("레거시 .ppt는 안전한 구조 분석이 불가합니다. PowerPoint에서 .pptx로 저장 후 업로드하세요.")
        chunks: list[dict[str, Any]] = []
        missing: list[str] = []
        with zipfile.ZipFile(source) as archive:
            slide_names = sorted(
                (name for name in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)),
                key=lambda name: int(re.search(r"(\d+)", Path(name).stem).group(1)),
            )
            for slide_index, name in enumerate(slide_names, start=1):
                root = ElementTree.fromstring(archive.read(name))
                texts = [str(node.text).strip() for node in root.iter() if node.tag.endswith("}t") and node.text]
                text = "\n".join(item for item in texts if item)
                if text:
                    chunks.append(
                        {
                            "id": f"{document.id}:slide:{slide_index}",
                            "text": text,
                            "metadata": {
                                "kind": "design_slide",
                                "slide": slide_index,
                                "scenarioHint": texts[0] if texts else None,
                                "evidenceRef": f"project_context:{document.id}:slide:{slide_index}",
                            },
                        }
                    )
            media_names = [
                name for name in archive.namelist()
                if name.startswith("ppt/media/") and Path(name).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            ]
            system_prompt, _ = PromptCatalog().render_system("project_context/vlm_ocr_system.md")
            vlm_client, vlm_display_name = self._model_client(
                document.projectId,
                ModelRequirement(
                    capabilities=["chat", "vision"],
                    minimumContext=8192,
                    structuredOutput=True,
                    qualityProfile="evidence_review",
                ),
                trace_id=document.id,
            )
            vlm_count = 0
            for media_index, name in enumerate(media_names[:24], start=1):
                image_bytes = archive.read(name)
                mime = {
                    ".png": "image/png",
                    ".webp": "image/webp",
                }.get(Path(name).suffix.lower(), "image/jpeg")
                parsed = vlm_client.vision_json(
                    system=system_prompt,
                    prompt=f"프로젝트 설계 문서 {document.fileName}의 이미지 {media_index}입니다.",
                    image_data_url=f"data:{mime};base64,{base64.b64encode(image_bytes).decode('ascii')}",
                    timeout_s=60.0,
                ) if vlm_client else None
                if not parsed:
                    continue
                vlm_count += 1
                screen = str(parsed.get("screenName") or "").strip()
                description = str(parsed.get("description") or "").strip()
                process = parsed.get("businessFlow") or []
                controls = parsed.get("controls") or []
                text = "\n".join(
                    part for part in (
                        f"추정 화면: {screen}" if screen else "",
                        f"화면 설명: {description}" if description else "",
                        f"업무 흐름: {' → '.join(map(str, process))}" if process else "",
                        f"관측 컨트롤: {', '.join(map(str, controls))}" if controls else "",
                    ) if part
                )
                if text:
                    chunks.append(
                        {
                            "id": f"{document.id}:image:{media_index}",
                            "text": text,
                            "metadata": {
                                "kind": "vlm_screen_observation",
                                "image": name,
                                "scenarioHint": screen or description or None,
                                "vlmModel": vlm_display_name,
                                "evidenceRef": f"project_context:{document.id}:image:{media_index}",
                            },
                        }
                    )
            if media_names and vlm_count == 0:
                missing.append("vlm_ocr_unavailable")
        if not chunks:
            raise ValueError("PPTX에서 텍스트 또는 VLM 화면 컨텍스트를 추출하지 못했습니다.")
        summary = f"설계 슬라이드 컨텍스트 {len(chunks)}개를 추출했습니다."
        return chunks, summary, missing

    def _embed_and_index(self, document: ProjectContextDocument, chunks: list[dict[str, Any]]) -> str:
        texts = [str(item.get("text") or "") for item in chunks]
        embedding_client, _ = self._model_client(
            document.projectId,
            ModelRequirement(
                capabilities=["embedding"],
                minimumContext=256,
                qualityProfile="embedding",
            ),
            trace_id=document.id,
        )
        vectors = embedding_client.embed_texts(texts) if embedding_client else None
        backend = "embedding_api"
        if not vectors or len(vectors) != len(texts):
            vectors = [_hash_embedding(text) for text in texts]
            backend = "local_hash_embedding"
        document_dir = self._document_dir(document.projectId, document.id)
        dimensions = len(vectors[0]) if vectors else 0
        try:
            import faiss  # type: ignore
            import numpy as np  # type: ignore

            matrix = np.asarray(vectors, dtype="float32")
            faiss.normalize_L2(matrix)
            index = faiss.IndexFlatIP(dimensions)
            index.add(matrix)
            faiss.write_index(index, str(document_dir / "index.faiss"))
            index_backend = f"faiss:{backend}"
        except (ImportError, OSError):
            # 설치 전 개발 환경에서도 같은 데이터 계약을 유지한다. 배포 의존성에는 faiss-cpu가 포함된다.
            with (document_dir / "vectors.f32").open("wb") as output:
                for vector in vectors:
                    output.write(struct.pack(f"<{len(vector)}f", *vector))
            index_backend = f"portable-vector:{backend}"
        (document_dir / "index-metadata.json").write_text(
            json.dumps(
                {"dimensions": dimensions, "chunks": [item["id"] for item in chunks], "backend": index_backend},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return index_backend

    def _project_dir(self, project_id: str) -> Path:
        safe_project_id = re.sub(r"[^0-9A-Za-z_-]", "_", project_id)
        path = self.root / safe_project_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _document_dir(self, project_id: str, document_id: str) -> Path:
        return self._project_dir(project_id) / re.sub(r"[^0-9A-Za-z_-]", "_", document_id)

    def _write_manifest(self, project_id: str) -> None:
        documents = self.repository.list(project_id)
        manifest = {
            "schemaVersion": "project-context/v1",
            "projectId": project_id,
            "updatedAt": _now().isoformat(),
            "documents": [],
        }
        for document in documents:
            document_dir = self._document_dir(project_id, document.id)
            manifest["documents"].append(
                {
                    **document.model_dump(mode="json"),
                    "chunksPath": str(document_dir / "chunks.json"),
                    "indexPath": str(document_dir / "index.faiss"),
                }
            )
        self.manifest_path(project_id).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )

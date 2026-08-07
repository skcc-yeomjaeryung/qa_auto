#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def _tokens(value: str) -> set[str]:
    normalized = re.sub(r"[^0-9a-z가-힣]+", " ", str(value or "").lower())
    return {token for token in normalized.split() if len(token) > 1}


def _graph_query(payload: dict[str, Any]) -> str:
    explicit = str(payload.get("scenarioContextQuery") or "").strip()
    graph = payload.get("interactionGraph") if isinstance(payload.get("interactionGraph"), dict) else {}
    parts = [explicit, str(payload.get("serviceId") or "")]
    for node in (graph.get("nodes") or [])[:500]:
        if not isinstance(node, dict):
            continue
        attrs = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
        parts.extend(
            str(value or "") for value in (
                node.get("name"), attrs.get("route"), attrs.get("path"), attrs.get("normalizedPath")
            )
        )
    return " ".join(part for part in parts if part).strip()


def discover(payload: dict[str, Any]) -> dict[str, Any]:
    project_id = str(payload.get("projectId") or "")
    manifest_path = Path(str(payload.get("projectContextManifestPath") or "")).expanduser()
    query = _graph_query(payload)
    empty = {
        "status": "not_found",
        "projectId": project_id,
        "query": query,
        "documents": [],
        "chunks": [],
        "promptContext": "",
        "guardrails": [],
    }
    if not manifest_path.is_file():
        return {**empty, "missingData": ["project_context_manifest"]}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {**empty, "missingData": ["project_context_manifest_invalid"]}
    documents = [
        item for item in (manifest.get("documents") or [])
        if isinstance(item, dict) and item.get("status") in {"ready", "partial"}
    ]
    if not documents:
        return empty
    query_tokens = _tokens(query)
    ranked: list[tuple[float, dict[str, Any]]] = []
    used_documents: list[dict[str, Any]] = []
    for document in documents:
        chunks_path = Path(str(document.get("chunksPath") or ""))
        if not chunks_path.is_file():
            continue
        try:
            chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        used_documents.append(
            {
                "id": document.get("id"),
                "fileName": document.get("fileName"),
                "kind": document.get("kind"),
                "status": document.get("status"),
                "summary": document.get("summary"),
                "indexBackend": document.get("indexBackend"),
            }
        )
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            text = str(chunk.get("text") or "")
            overlap = len(query_tokens & _tokens(text))
            score = overlap / max(1, len(query_tokens))
            metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
            if metadata.get("kind") == "test_case_row":
                score += 0.15
            ranked.append(
                (
                    score,
                    {
                        **chunk,
                        "documentId": document.get("id"),
                        "fileName": document.get("fileName"),
                    },
                )
            )
    ranked.sort(key=lambda item: (item[0], len(str(item[1].get("text") or ""))), reverse=True)
    selected = [{**chunk, "score": round(score, 4)} for score, chunk in ranked[:12]]
    prompt = "\n\n".join(
        f"[project_context:{chunk.get('documentId')}] {chunk.get('fileName')}\n{chunk.get('text')}"
        for chunk in selected
    )[:16000]
    result = {
        "status": "found" if selected else "not_found",
        "projectId": project_id,
        "query": query,
        "documents": used_documents,
        "chunks": selected,
        "promptContext": prompt,
        "guardrails": [
            "보조 문서는 코드 Graph·DOM·API 근거와 결합해 사용한다.",
            "문서 단독으로 selector, endpoint, request/response, 최종 Pass/Fail을 확정하지 않는다.",
            "충돌하거나 근거가 부족한 내용은 unresolved로 남긴다.",
        ],
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8") or "{}")
    result = discover(payload)
    output = {
        "ok": True,
        "skill": "project_context_discover",
        "tool": "discover_project_context",
        "projectId": payload.get("projectId"),
        "result": {"projectContext": result},
    }
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "documents": len(result["documents"]), "chunks": len(result["chunks"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


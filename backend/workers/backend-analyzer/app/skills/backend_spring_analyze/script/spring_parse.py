from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import javalang
from javalang import tree

from app.schemas.backend_analysis import (
    BackendAnalysisResult,
    DtoField,
    DtoType,
    Endpoint,
    Evidence,
    ExceptionHandlerEntry,
    ExistingTest,
    FileHash,
    ServiceEntry,
    Unresolved,
    ValidationRule,
)

SKIP_DIRS = {".git", "build", "target", ".gradle", "node_modules", ".idea"}

MAPPING = {
    "GetMapping": "GET",
    "PostMapping": "POST",
    "PutMapping": "PUT",
    "DeleteMapping": "DELETE",
    "PatchMapping": "PATCH",
    "RequestMapping": None,
}

CONSTRAINT_ANN = {
    "NotBlank",
    "NotNull",
    "NotEmpty",
    "Pattern",
    "Size",
    "Min",
    "Max",
    "Email",
    "Positive",
    "Negative",
}


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_java_source(text: str) -> str:
    """Rewrite Java records into class-shaped source so javalang can parse them.

    Only rewrite the `record` *keyword* (must be followed by whitespace then a type
    name). Method calls like `.recordStats()` must not be rewritten.
    """
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("record", i) and (i == 0 or not (text[i - 1].isalnum() or text[i - 1] == "_")):
            j = i + len("record")
            # Java record keyword requires whitespace before the name.
            # Reject identifiers/method calls: recordStats(), .recordFoo(
            if j >= n or not text[j].isspace():
                out.append(text[i])
                i += 1
                continue
            while j < n and text[j].isspace():
                j += 1
            name_start = j
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            name = text[name_start:j]
            if not name:
                out.append(text[i])
                i += 1
                continue
            while j < n and text[j].isspace():
                j += 1
            if j >= n or text[j] != "(":
                out.append(text[i])
                i += 1
                continue
            # Skip if previous token is a member access (defensive).
            if i > 0 and text[i - 1] == ".":
                out.append(text[i])
                i += 1
                continue
            params, j = _read_balanced(text, j, "(", ")")
            while j < n and text[j].isspace():
                j += 1
            body = ""
            if j < n and text[j] == "{":
                body_inner, j = _read_balanced(text, j, "{", "}")
                body = body_inner[1:-1]
            elif j < n and text[j] == ";":
                j += 1
            fields = []
            for part in _split_params(params[1:-1]):
                part = part.strip()
                if part:
                    fields.append(f"    public {part};")
            field_block = "\n".join(fields)
            out.append(f"class {name} {{\n{field_block}\n{body}\n}}")
            i = j
            continue
        out.append(text[i])
        i += 1
    return "".join(out)


def _read_balanced(text: str, start: int, open_ch: str, close_ch: str) -> tuple[str, int]:
    assert text[start] == open_ch
    depth = 0
    in_str = False
    escape = False
    i = start
    while i < len(text):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            i += 1
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1], i + 1
        i += 1
    return text[start:], len(text)


def _split_params(params: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth_angle = 0
    depth_paren = 0
    in_str = False
    escape = False
    for ch in params:
        if in_str:
            buf.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            buf.append(ch)
            continue
        if ch == "<":
            depth_angle += 1
        elif ch == ">":
            depth_angle = max(0, depth_angle - 1)
        elif ch == "(":
            depth_paren += 1
        elif ch == ")":
            depth_paren = max(0, depth_paren - 1)
        if ch == "," and depth_angle == 0 and depth_paren == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


def _slug(*parts: str) -> str:
    raw = "-".join(parts)
    return re.sub(r"[^a-zA-Z0-9:_-]+", "-", raw).strip("-")[:140]


def _ann_name(ann: tree.Annotation) -> str:
    name = ann.name
    if isinstance(name, str):
        return name.split(".")[-1]
    return str(name).split(".")[-1]


def _ann_values(ann: tree.Annotation) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if ann.element is None:
        return out
    if not isinstance(ann.element, list):
        out["value"] = _literal(ann.element)
        return out
    for el in ann.element:
        if isinstance(el, tree.ElementValuePair):
            out[el.name] = _literal(el.value)
        else:
            out["value"] = _literal(el)
    return out


def _literal(node: Any) -> Any:
    if node is None:
        return None
    if isinstance(node, tree.Literal):
        text = node.value
        if text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        return text
    if isinstance(node, tree.MemberReference):
        return f"{node.qualifier}.{node.member}" if node.qualifier else node.member
    if isinstance(node, list):
        return [_literal(x) for x in node]
    return str(node)


def _path_join(base: str, extra: str) -> str:
    base = (base or "").rstrip("/")
    extra = (extra or "").strip()
    if not extra:
        return base or "/"
    if not extra.startswith("/"):
        extra = "/" + extra
    if not base:
        return extra
    return (base + extra).replace("//", "/")


def _class_ann_path(anns: list[tree.Annotation]) -> tuple[str, str | None]:
    method_default = None
    path = ""
    for ann in anns or []:
        name = _ann_name(ann)
        vals = _ann_values(ann)
        if name == "RequestMapping":
            path = vals.get("value") or vals.get("path") or path
            if isinstance(path, list):
                path = path[0] if path else ""
            m = vals.get("method")
            if m:
                method_default = str(m).split(".")[-1]
        elif name in MAPPING and name != "RequestMapping":
            p = vals.get("value") or vals.get("path") or ""
            if isinstance(p, list):
                p = p[0] if p else ""
            path = p or path
            method_default = MAPPING[name]
    return str(path or ""), method_default


def _simplify_type_symbol(value: Any) -> str:
    if value is None:
        return "Exception"
    text = str(value)
    m = re.search(r"name=([A-Za-z_][\w]*)", text)
    if m:
        return m.group(1)
    if "." in text:
        return text.split(".")[-1]
    return text


def _type_name(t: Any) -> str:
    if t is None:
        return "void"
    if isinstance(t, tree.ReferenceType):
        name = t.name
        if t.arguments:
            args = ",".join(_type_name(a.type) if hasattr(a, "type") else str(a) for a in t.arguments)
            return f"{name}<{args}>"
        return name
    if isinstance(t, tree.BasicType):
        return t.name
    return str(t)


def list_java_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.java"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def analyze_workspace(
    workspace: Path,
    commit_sha: str | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> BackendAnalysisResult:
    root = workspace.resolve()
    files = list_java_files(root)
    endpoints: list[Endpoint] = []
    request_dtos: list[DtoType] = []
    response_dtos: list[DtoType] = []
    validations: list[ValidationRule] = []
    services: list[ServiceEntry] = []
    exceptions: list[ExceptionHandlerEntry] = []
    tests: list[ExistingTest] = []
    unresolved: list[Unresolved] = []
    file_hashes: list[FileHash] = []

    parsed: dict[str, tuple[Path, Any]] = {}

    for file_index, path in enumerate(files, start=1):
        rel = _rel(root, path)
        file_hashes.append(FileHash(path=rel, sha256=_sha(path)))
        text = path.read_text(encoding="utf-8", errors="replace")
        normalized = _normalize_java_source(text)
        try:
            tree_cu = javalang.parse.parse(normalized)
        except javalang.parser.JavaSyntaxError as exc:
            unresolved.append(
                Unresolved(
                    id=_slug("unresolved", "parse", rel),
                    kind="parse",
                    symbol=rel,
                    reason=f"Java syntax error: {exc}",
                    evidence=Evidence(file=rel, line=1, extractor="javalang", confidence=0.2),
                )
            )
            if progress_callback:
                progress_callback(file_index, len(files))
            continue
        parsed[rel] = (path, tree_cu)

        # tests: MockMvc / REST Assured heuristics on source text
        if "/test/" in f"/{rel}/" or rel.startswith("src/test/"):
            steps = _extract_test_steps(text)
            if steps:
                fw = "mockmvc" if "MockMvc" in text or "mockMvc" in text else "rest-assured" if "RestAssured" in text or "given()" in text else "junit"
                tests.append(
                    ExistingTest(
                        id=_slug("test", fw, rel),
                        framework=fw,
                        file=rel,
                        steps=steps,
                        evidence=Evidence(file=rel, line=1, extractor="test-parser", confidence=0.85),
                    )
                )
        if progress_callback:
            progress_callback(file_index, len(files))

    # types index
    type_decls: dict[str, tuple[str, Any]] = {}
    for rel, (_path, cu) in parsed.items():
        for _, cls in cu.filter(tree.ClassDeclaration):
            type_decls[cls.name] = (rel, cls)
        for _, iface in cu.filter(tree.InterfaceDeclaration):
            type_decls[iface.name] = (rel, iface)

    for rel, (_path, cu) in parsed.items():
        for _, cls in cu.filter(tree.ClassDeclaration):
            anns = cls.annotations or []
            ann_names = {_ann_name(a) for a in anns}
            class_path, class_method = _class_ann_path(anns)

            if "Service" in ann_names or any(
                isinstance(t, tree.ReferenceType) and t.name.endswith("Service")
                for t in (cls.implements or [])
            ):
                impl = None
                if cls.implements:
                    impl = cls.implements[0].name
                methods = [m.name for m in (cls.methods or [])]
                services.append(
                    ServiceEntry(
                        id=_slug("service", cls.name, rel),
                        name=cls.name,
                        kind="class",
                        implementsInterface=impl,
                        methods=methods,
                        evidence=Evidence(
                            file=rel,
                            line=cls.position.line if cls.position else 1,
                            extractor="spring-service",
                            confidence=0.9,
                        ),
                    )
                )

            if "RestControllerAdvice" in ann_names or "ControllerAdvice" in ann_names:
                for method in cls.methods or []:
                    for ann in method.annotations or []:
                        if _ann_name(ann) != "ExceptionHandler":
                            continue
                        vals = _ann_values(ann)
                        ex = vals.get("value")
                        if isinstance(ex, list):
                            ex = ex[0] if ex else "Exception"
                        ex_name = _simplify_type_symbol(ex)
                        status = _find_http_status_in_method(method)
                        exceptions.append(
                            ExceptionHandlerEntry(
                                id=_slug("ex", cls.name, method.name, rel),
                                exceptionType=ex_name,
                                httpStatus=status,
                                handlerClass=cls.name,
                                evidence=Evidence(
                                    file=rel,
                                    line=method.position.line if method.position else 1,
                                    extractor="spring-advice",
                                    confidence=0.88,
                                ),
                            )
                        )

            is_controller = "RestController" in ann_names or "Controller" in ann_names
            if is_controller:
                for method in cls.methods or []:
                    m_anns = method.annotations or []
                    http = None
                    method_path = ""
                    for ann in m_anns:
                        name = _ann_name(ann)
                        vals = _ann_values(ann)
                        if name in MAPPING:
                            p = vals.get("value") or vals.get("path") or ""
                            if isinstance(p, list):
                                p = p[0] if p else ""
                            method_path = str(p or "")
                            http = MAPPING[name] or class_method
                            if name == "RequestMapping":
                                m = vals.get("method")
                                if m:
                                    http = str(m).split(".")[-1]
                    if not http:
                        continue
                    full = _path_join(class_path, method_path)
                    req_dto = None
                    resp_dto = _type_name(method.return_type)
                    # unwrap ResponseEntity<X>
                    m = re.match(r"ResponseEntity<(.+)>", resp_dto)
                    if m:
                        resp_dto = m.group(1)
                    service_calls: list[str] = []
                    statuses = _status_candidates(method)
                    for param in method.parameters or []:
                        p_anns = {_ann_name(a) for a in (param.annotations or [])}
                        if "RequestBody" in p_anns:
                            req_dto = _type_name(param.type)
                    # service field calls
                    for _path_node, inv in method.filter(tree.MethodInvocation):
                        q = str(inv.qualifier or "")
                        if q and q[0].islower() and q not in {"log", "logger", "System"} and not q.startswith("request"):
                            service_calls.append(f"{q}.{inv.member}")
                    endpoints.append(
                        Endpoint(
                            id=_slug("ep", http, full, cls.name, method.name),
                            method=http.upper(),
                            path=full,
                            controller=cls.name,
                            handlerMethod=method.name,
                            requestDto=req_dto,
                            responseDto=resp_dto if resp_dto != "void" else None,
                            serviceCalls=sorted(set(service_calls)),
                            statusCandidates=statuses,
                            evidence=Evidence(
                                file=rel,
                                line=method.position.line if method.position else 1,
                                extractor="spring-mvc",
                                confidence=0.93,
                            ),
                        )
                    )

            # DTO-like classes (records normalized to class)
            names = {_ann_name(a) for a in (cls.annotations or [])}
            if not (
                "RestController" in names
                or "Service" in names
                or "ControllerAdvice" in names
                or "RestControllerAdvice" in names
            ):
                if (
                    cls.name.endswith("Request")
                    or cls.name.endswith("Response")
                    or cls.name.endswith("Dto")
                ):
                    kind = "record" if "record " in text else "class"
                    _collect_dto(cls, rel, request_dtos, response_dtos, validations, kind)

        for _, iface in cu.filter(tree.InterfaceDeclaration):
            if iface.name.endswith("Service"):
                methods = [m.name for m in (iface.methods or [])]
                services.append(
                    ServiceEntry(
                        id=_slug("service-iface", iface.name, rel),
                        name=iface.name,
                        kind="interface",
                        implementsInterface=None,
                        methods=methods,
                        evidence=Evidence(
                            file=rel,
                            line=iface.position.line if iface.position else 1,
                            extractor="spring-service",
                            confidence=0.9,
                        ),
                    )
                )

    # Profile unresolved heuristic
    for rel, (_path, cu) in parsed.items():
        text = _path.read_text(encoding="utf-8", errors="replace")
        if "@Profile(" in text:
            unresolved.append(
                Unresolved(
                    id=_slug("unresolved", "profile", rel),
                    kind="profile-bean",
                    symbol="@Profile",
                    reason="Profile-conditional bean cannot be statically finalized",
                    evidence=Evidence(file=rel, line=1, extractor="profile", confidence=0.4),
                )
            )

    return BackendAnalysisResult(
        commitSha=commit_sha,
        workspacePath=str(root),
        analyzedAt=datetime.now(timezone.utc).isoformat(),
        endpoints=endpoints,
        requestDtos=request_dtos,
        validations=validations,
        services=services,
        responseDtos=response_dtos,
        exceptions=exceptions,
        existingTests=tests,
        unresolved=unresolved,
        fileHashes=file_hashes,
    )


def _collect_dto(
    node: Any,
    rel: str,
    request_dtos: list[DtoType],
    response_dtos: list[DtoType],
    validations: list[ValidationRule],
    kind: str,
) -> None:
    name = node.name
    fields: list[DtoField] = []
    line = node.position.line if getattr(node, "position", None) else 1

    for field_decl in node.fields or []:
        for declarator in field_decl.declarators:
            field, rules = _field_from_field(field_decl, declarator, name, rel)
            fields.append(field)
            validations.extend(rules)

    dto = DtoType(
        id=_slug("dto", name, rel),
        name=name,
        kind=kind,
        fields=fields,
        evidence=Evidence(file=rel, line=line, extractor="spring-dto", confidence=0.9),
    )
    if name.endswith("Request") or "Request" in name:
        request_dtos.append(dto)
    elif name.endswith("Response") or "Response" in name:
        response_dtos.append(dto)
    else:
        request_dtos.append(dto)


def _field_from_param(param: tree.FormalParameter, owner: str, rel: str) -> tuple[DtoField, list[ValidationRule]]:
    anns = param.annotations or []
    constraints: dict[str, Any] = {}
    required = False
    rules: list[ValidationRule] = []
    for ann in anns:
        n = _ann_name(ann)
        vals = _ann_values(ann)
        if n in CONSTRAINT_ANN:
            constraints[n] = vals or True
            if n in {"NotBlank", "NotNull", "NotEmpty"}:
                required = True
            rules.append(
                ValidationRule(
                    id=_slug("val", owner, param.name, n),
                    target=owner,
                    field=param.name,
                    kind=n,
                    expression=str(vals or n),
                    evidence=Evidence(
                        file=rel,
                        line=param.position.line if param.position else 1,
                        extractor="bean-validation",
                        confidence=0.92,
                    ),
                )
            )
    return (
        DtoField(
            name=param.name,
            type=_type_name(param.type),
            jsonName=param.name,
            required=required,
            constraints=constraints,
        ),
        rules,
    )


def _field_from_field(
    field_decl: tree.FieldDeclaration,
    declarator: tree.VariableDeclarator,
    owner: str,
    rel: str,
) -> tuple[DtoField, list[ValidationRule]]:
    anns = field_decl.annotations or []
    constraints: dict[str, Any] = {}
    required = False
    rules: list[ValidationRule] = []
    for ann in anns:
        n = _ann_name(ann)
        vals = _ann_values(ann)
        if n in CONSTRAINT_ANN:
            constraints[n] = vals or True
            if n in {"NotBlank", "NotNull", "NotEmpty"}:
                required = True
            rules.append(
                ValidationRule(
                    id=_slug("val", owner, declarator.name, n),
                    target=owner,
                    field=declarator.name,
                    kind=n,
                    expression=str(vals or n),
                    evidence=Evidence(
                        file=rel,
                        line=field_decl.position.line if field_decl.position else 1,
                        extractor="bean-validation",
                        confidence=0.9,
                    ),
                )
            )
    return (
        DtoField(
            name=declarator.name,
            type=_type_name(field_decl.type),
            jsonName=declarator.name,
            required=required,
            constraints=constraints,
        ),
        rules,
    )


def _find_http_status_in_method(method: tree.MethodDeclaration) -> str | None:
    for _, ref in method.filter(tree.MemberReference):
        if ref.qualifier == "HttpStatus" or (ref.member and ref.member.isupper()):
            if ref.qualifier == "HttpStatus":
                return ref.member
    text_status = None
    for _, inv in method.filter(tree.MethodInvocation):
        if inv.member == "status" and inv.arguments:
            arg = inv.arguments[0]
            lit = _literal(arg)
            if isinstance(lit, str) and "HttpStatus" in lit:
                return lit.split(".")[-1]
            text_status = str(lit)
    return text_status


def _status_candidates(method: tree.MethodDeclaration) -> list[str]:
    found: list[str] = []
    for _, ref in method.filter(tree.MemberReference):
        if ref.qualifier == "HttpStatus":
            found.append(ref.member)
    for _, inv in method.filter(tree.MethodInvocation):
        if inv.member in {"ok", "notFound", "badRequest"}:
            found.append(inv.member)
        if inv.member == "status" and inv.arguments:
            lit = _literal(inv.arguments[0])
            if lit:
                found.append(str(lit).split(".")[-1])
    # orElseThrow suggests error path
    for _, inv in method.filter(tree.MethodInvocation):
        if inv.member == "orElseThrow":
            found.append("NOT_FOUND_CANDIDATE")
    return sorted(set(found))


def _extract_test_steps(text: str) -> list[dict[str, str]]:
    steps: list[dict[str, str]] = []
    for m in re.finditer(r'post\(\s*"([^"]+)"\s*\)', text):
        steps.append({"action": "post", "target": m.group(1)})
    for m in re.finditer(r'get\(\s*"([^"]+)"\s*\)', text):
        steps.append({"action": "get", "target": m.group(1)})
    for m in re.finditer(r'\.content\(\s*"((?:\\.|[^"\\])*)"\s*\)', text):
        steps.append({"action": "content", "value": m.group(1)})
    for m in re.finditer(r"status\(\)\.is(\w+)\(\)", text):
        steps.append({"action": "expectStatus", "value": m.group(1)})
    for m in re.finditer(r'jsonPath\(\s*"([^"]+)"\s*\)\.value\(\s*"([^"]*)"\s*\)', text):
        steps.append({"action": "jsonPath", "target": m.group(1), "value": m.group(2)})
    for m in re.finditer(r'\.when\(\)\s*\.\s*(get|post|put|delete)\(\s*"([^"]+)"', text):
        steps.append({"action": m.group(1), "target": m.group(2), "framework": "rest-assured"})
    return steps

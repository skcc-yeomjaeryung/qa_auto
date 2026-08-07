from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from app.core.paths import BACKEND_ROOT


@dataclass(frozen=True)
class PromptMetadata:
    name: str
    version: str
    sha256: str
    source: str


class PromptCatalog:
    """Single LangChain-backed loader for versioned role prompts."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (BACKEND_ROOT / "app" / "prompts")

    def load_system(self, relative_path: str) -> tuple[str, PromptMetadata]:
        path = (self.root / relative_path).resolve()
        if self.root.resolve() not in path.parents or not path.is_file():
            raise FileNotFoundError(f"prompt not found: {relative_path}")
        text = path.read_text(encoding="utf-8").strip()
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        first = text.splitlines()[0] if text else ""
        version = first.removeprefix("<!-- version:").removesuffix("-->").strip() if first.startswith("<!-- version:") else digest[:12]
        return text, PromptMetadata(path.stem, version, digest, str(path))

    def chat_template(self, relative_path: str, user_template: str) -> tuple[ChatPromptTemplate, PromptMetadata]:
        system, metadata = self.load_system(relative_path)
        # System prompts are constant assets. Using SystemMessage keeps JSON examples
        # and braces literal while the human template can still bind variables.
        return ChatPromptTemplate.from_messages([SystemMessage(content=system), ("human", user_template)]), metadata

    def render_system(self, relative_path: str) -> tuple[str, PromptMetadata]:
        system, metadata = self.load_system(relative_path)
        message = SystemMessage(content=system)
        return str(message.content), metadata

    def render(self, relative_path: str, user_template: str, **kwargs: Any) -> tuple[list[Any], PromptMetadata]:
        template, metadata = self.chat_template(relative_path, user_template)
        return template.format_messages(**kwargs), metadata

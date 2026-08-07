"""Shared LLM client (singleton) for Skill structured-output helpers."""

from app.core.llm.llm_client import get_llm_client

__all__ = ["get_llm_client"]

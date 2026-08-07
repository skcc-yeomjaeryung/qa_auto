"""Optional LangGraph orchestration placeholder.

Phase 03 uses deterministic Tool scripts for fact extraction.
LangGraph may wrap tool order later; LLM must not invent endpoints.
"""


def run_spring_analyze_graph(workspace: str, commit_sha: str | None = None):
    from pathlib import Path

    from app.skills.backend_spring_analyze.script.spring_parse import analyze_workspace

    return analyze_workspace(Path(workspace), commit_sha=commit_sha)

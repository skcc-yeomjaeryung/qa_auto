"""Lightweight tech-stack detection from known manifest files."""

from __future__ import annotations

import json
from pathlib import Path


def detect_stack(root: Path) -> dict[str, object]:
    languages: set[str] = set()
    frameworks: list[str] = []
    manifests: list[str] = []

    checks = [
        ("package.json", _from_package_json),
        ("tsconfig.json", lambda _: ( {"TypeScript"}, ["TypeScript"] )),
        ("next.config.js", lambda _: ( {"TypeScript", "JavaScript"}, ["Next.js"] )),
        ("next.config.mjs", lambda _: ( {"TypeScript", "JavaScript"}, ["Next.js"] )),
        ("next.config.ts", lambda _: ( {"TypeScript"}, ["Next.js"] )),
        ("vite.config.ts", lambda _: ( {"TypeScript"}, ["Vite"] )),
        ("vite.config.js", lambda _: ( {"JavaScript"}, ["Vite"] )),
        ("pom.xml", lambda _: ( {"Java"}, ["Maven"] )),
        ("build.gradle", lambda _: ( {"Java"}, ["Gradle"] )),
        ("build.gradle.kts", lambda _: ( {"Kotlin", "Java"}, ["Gradle"] )),
        ("requirements.txt", lambda _: ( {"Python"}, ["pip"] )),
        ("pyproject.toml", lambda _: ( {"Python"}, ["Python packaging"] )),
        ("go.mod", lambda _: ( {"Go"}, ["Go modules"] )),
    ]

    for relative, handler in checks:
        path = root / relative
        if not path.is_file():
            continue
        manifests.append(relative)
        langs, fws = handler(path)
        languages.update(langs)
        for item in fws:
            if item not in frameworks:
                frameworks.append(item)

    # lockfiles
    for lock in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock"):
        if (root / lock).is_file() and lock not in manifests:
            manifests.append(lock)

    return {
        "languages": sorted(languages),
        "frameworks": frameworks,
        "manifests": manifests,
    }


def _from_package_json(path: Path) -> tuple[set[str], list[str]]:
    languages = {"JavaScript"}
    frameworks: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return languages, frameworks

    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    if "typescript" in deps or (path.parent / "tsconfig.json").is_file():
        languages.add("TypeScript")
    if "next" in deps:
        frameworks.append("Next.js")
    if "react" in deps and "Next.js" not in frameworks:
        frameworks.append("React")
    if "vite" in deps:
        frameworks.append("Vite")
    return languages, frameworks

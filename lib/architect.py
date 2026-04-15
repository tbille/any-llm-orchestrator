"""Phase 4: Technical Architect -- creates tech spec and per-repo implementation specs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from lib.config import REPO_BY_NAME, ProjectPaths


def run_architect(
    slug: str,
    repo_names: list[str],
    paths: ProjectPaths,
    *,
    light: bool = False,
) -> list[str]:
    """Launch the architect agent to produce technical specifications.

    Args:
        slug: Feature slug.
        repo_names: Repos identified by triage as affected.
        paths: Project paths.
        light: If True, produce a lighter investigation-focused spec
               (used for complex-bug path instead of full feature spec).

    Returns:
        The final list of affected repo names (the architect may adjust it).
    """
    spec_dir = paths.spec_dir(slug)

    # Check which context files exist (using relative names).
    context_files: list[str] = []
    for name in ("prd.md", "design.md", "input.md"):
        if (spec_dir / name).exists():
            context_files.append(name)

    mode_label = (
        "lightweight investigation spec" if light else "full technical specification"
    )

    print(f"\n── Phase 4: Architect ({mode_label}) ────────────────")
    print(f"  Working dir: {spec_dir}")
    print(f"  Context:     {', '.join(context_files)}")
    print(f"  Output:      tech-spec.md + per-repo specs")
    print(f"  Repos:       {', '.join(repo_names)}")
    print("  The architect agent will open in a TUI session.")
    print("  Collaborate on the tech spec, then exit.")
    print("────────────────────────────────────────────────────\n")

    repo_lines: list[str] = []
    for name in repo_names:
        if name not in REPO_BY_NAME:
            continue
        info = REPO_BY_NAME[name]
        line = f"- **{name}** ({info.language}): {info.description}"
        if info.scope_notes:
            line += f"\n  - **Scope note:** {info.scope_notes}"
        repo_lines.append(line)
    repo_descriptions = "\n".join(repo_lines)

    if light:
        task_instruction = (
            "This is a **complex bug** that needs a focused investigation and fix plan.\n"
            "Create a lightweight technical spec that covers:\n"
            "1. Root cause hypothesis\n"
            "2. Which repos need changes and why\n"
            "3. The fix approach for each repo\n"
            "4. Shared interfaces or contracts that must remain consistent\n"
            "5. Testing strategy\n"
        )
    else:
        task_instruction = (
            "This is a **new feature** that needs a full technical specification.\n"
            "Create a tech spec that covers:\n"
            "1. Architecture overview\n"
            "2. Shared interfaces / API contracts that multiple repos must agree on\n"
            "3. Per-repo implementation plan (what each repo needs to do)\n"
            "4. Dependency order (which repo changes must land first)\n"
            "5. Migration / backwards compatibility strategy\n"
            "6. Testing strategy\n"
        )

    # List which worktrees are available.
    worktree_listing = "\n".join(
        f"- `repos/{name}/` ({REPO_BY_NAME[name].language})"
        for name in repo_names
        if name in REPO_BY_NAME and (spec_dir / "repos" / name).exists()
    )

    prompt = (
        f"You are the Technical Architect for this work.\n\n"
        f"## Working directory\n"
        f"ALL spec files you read or write are in the current directory.\n"
        f"Do NOT access files outside this directory.\n\n"
        f"## Repository code\n"
        f"The source code for each affected repository is available as a\n"
        f"worktree under `repos/` in the current directory. You can browse\n"
        f"the code to understand existing APIs, types, and patterns:\n"
        f"{worktree_listing}\n\n"
        f"Use these to inform your specs -- check existing interfaces,\n"
        f"naming conventions, and test patterns before designing new ones.\n\n"
        f"## Context files (in the current directory)\n"
        f"Read these files for the full context:\n"
        + "\n".join(f"- {f}" for f in context_files)
        + f"\n\n"
        f"## Affected repositories (initial assessment)\n"
        f"{repo_descriptions}\n\n"
        f"You may add or remove repos from this list if your analysis shows different needs.\n\n"
        f"## Task\n"
        f"{task_instruction}\n"
        f"Write the overall tech spec to: tech-spec.md\n\n"
        f"Additionally, for EACH affected repo, write a standalone implementation spec to:\n"
        f"  <repo-name>-spec.md (in the current directory)\n\n"
        f"Each per-repo spec should be self-contained: an engineer reading ONLY that file "
        f"(plus the shared interface section) should know exactly what to build.\n\n"
        f"IMPORTANT: At the end, output a line like:\n"
        f"AFFECTED_REPOS: repo1, repo2, repo3\n"
        f"so the orchestrator knows the final list."
    )

    subprocess.run(
        [
            "opencode",
            "--agent",
            "architect",
            "--prompt",
            prompt,
            str(spec_dir),
        ],
        cwd=str(spec_dir),
    )

    # Try to determine the final repo list from the tech spec.
    return _extract_affected_repos(slug, repo_names, paths)


def _extract_affected_repos(
    slug: str,
    fallback_repos: list[str],
    paths: ProjectPaths,
) -> list[str]:
    """Read per-repo spec files to determine which repos the architect targeted."""
    spec_dir = paths.spec_dir(slug)
    found: list[str] = []
    for name in REPO_BY_NAME:
        if (spec_dir / f"{name}-spec.md").exists():
            found.append(name)

    if found:
        return found

    # Fallback to the triage list if no per-repo specs were written yet.
    return fallback_repos


# ── Resume helpers ────────────────────────────────────────────────────


def tech_spec_exists(slug: str, paths: ProjectPaths) -> bool:
    return paths.spec_file(slug, "tech-spec.md").exists()


def get_affected_repos(
    slug: str, fallback: list[str], paths: ProjectPaths
) -> list[str]:
    """Return the list of repos that have per-repo specs (or fallback)."""
    return _extract_affected_repos(slug, fallback, paths)

"""Phase 4: Technical Architect -- creates tech spec and per-repo implementation specs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from totomisu.config import CAVEMAN_PROMPT, REPO_BY_NAME, ProjectPaths, headless_env


def _build_architect_prompt(
    slug: str,
    repo_names: list[str],
    paths: ProjectPaths,
    *,
    light: bool,
) -> tuple[str, list[str]]:
    """Build the architect prompt and the list of existing context files.

    Returns:
        Tuple of (prompt, context_files). ``context_files`` is the list of
        relative filenames (prd.md/design.md/input.md) that actually exist
        in the spec directory; useful for logging.
    """
    spec_dir = paths.spec_dir(slug)

    # Check which context files exist (using relative names).
    context_files: list[str] = []
    for name in ("prd.md", "design.md", "input.md"):
        if (spec_dir / name).exists():
            context_files.append(name)

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
        f"## Working directory scope\n"
        f"ALL files you read or write are in the CURRENT WORKING DIRECTORY.\n"
        f"You MUST NOT access any path outside the current directory.  Do\n"
        f"NOT use `../`, absolute paths, or parent-directory references.\n"
        f"The ecosystem's upstream clones live elsewhere on disk and are\n"
        f"OFF LIMITS; only the `repos/` inside the current dir is yours.\n\n"
        f"## Repository code\n"
        f"The source code for each affected repository is available as a\n"
        f"worktree at `repos/<repo-name>/` **inside the current directory**.\n"
        f"Use relative paths only (e.g. `repos/any-llm/src/...`).  Browse\n"
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

    return prompt, context_files


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
    mode_label = (
        "lightweight investigation spec" if light else "full technical specification"
    )

    prompt, context_files = _build_architect_prompt(
        slug, repo_names, paths, light=light
    )

    print(f"\n── Phase 4: Architect ({mode_label}) ────────────────")
    print(f"  Working dir: {spec_dir}")
    print(f"  Context:     {', '.join(context_files)}")
    print(f"  Output:      tech-spec.md + per-repo specs")
    print(f"  Repos:       {', '.join(repo_names)}")
    print("  The architect agent will open in a TUI session.")
    print("  Collaborate on the tech spec, then exit.")
    print("────────────────────────────────────────────────────\n")

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


def run_architect_headless(
    slug: str,
    repo_names: list[str],
    paths: ProjectPaths,
    *,
    light: bool = False,
) -> list[str]:
    """Run the architect agent as a single headless pass.

    Produces the same ``tech-spec.md`` + per-repo specs as the interactive
    flow.  No user interaction required.
    """
    spec_dir = paths.spec_dir(slug)
    tech_spec_file = paths.spec_file(slug, "tech-spec.md")
    mode_label = (
        "lightweight investigation spec" if light else "full technical specification"
    )

    prompt, context_files = _build_architect_prompt(
        slug, repo_names, paths, light=light
    )
    prompt = CAVEMAN_PROMPT + prompt

    print(f"\n── Phase 4: Architect headless ({mode_label}) ──────")
    print(f"  Working dir: {spec_dir}")
    print(f"  Context:     {', '.join(context_files)}")
    print(f"  Output:      tech-spec.md + per-repo specs")
    print(f"  Repos:       {', '.join(repo_names)}")
    print("  Running headless (no TUI interaction)...")
    print("────────────────────────────────────────────────────\n")

    # Pass the context files via -f so opencode attaches them directly.
    file_args: list[str] = []
    for name in context_files:
        file_args.extend(["-f", str(spec_dir / name)])

    result = subprocess.run(
        [
            "opencode",
            "run",
            "--dir",
            str(spec_dir),
            "--dangerously-skip-permissions",
            *file_args,
            "--",
            prompt,
        ],
        cwd=str(spec_dir),
        env=headless_env(),
    )

    if result.returncode != 0:
        print(
            f"  [WARN] Headless architect agent exited with code {result.returncode}",
            file=sys.stderr,
        )

    if not tech_spec_file.exists():
        print(f"  [WARN] Tech spec not found at {tech_spec_file}.", file=sys.stderr)
        print("         The headless architect may not have written it.")

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

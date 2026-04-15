"""Phase 5: Clone missing repos and create worktrees via wt."""

from __future__ import annotations

import fcntl
import os
import subprocess
import sys
from contextlib import contextmanager
from collections.abc import Generator
from pathlib import Path

from lib.config import REPO_BY_NAME, REPOS, ProjectPaths


# ── File locking (for parallel orchestrator safety) ───────────────────


def _locks_dir(paths: ProjectPaths) -> Path:
    d = paths.repos_dir / ".locks"
    d.mkdir(parents=True, exist_ok=True)
    return d


@contextmanager
def _repo_lock(paths: ProjectPaths, repo_name: str) -> Generator[None, None, None]:
    """Acquire an exclusive file lock for a repo.

    Prevents two parallel orchestrator processes from cloning or creating
    worktrees in the same repo simultaneously.
    """
    lock_path = _locks_dir(paths) / f"{repo_name}.lock"
    fd = lock_path.open("w")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        fd.close()


# ── Clone ─────────────────────────────────────────────────────────────


def ensure_repos_cloned(paths: ProjectPaths) -> None:
    """Clone any repository that is not yet present under repos/."""
    paths.repos_dir.mkdir(parents=True, exist_ok=True)

    for repo in REPOS:
        dest = paths.repo_path(repo.name)
        if dest.exists() and (dest / ".git").exists():
            print(f"  [ok]   {repo.name} already cloned")
            continue

        with _repo_lock(paths, repo.name):
            # Re-check after acquiring the lock (another process may have
            # cloned while we were waiting).
            if dest.exists() and (dest / ".git").exists():
                print(f"  [ok]   {repo.name} already cloned (raced)")
                continue

            print(f"  [clone] {repo.name} -> {dest}")
            subprocess.run(
                ["git", "clone", repo.github_url, str(dest)],
                check=True,
            )


# ── Worktrees ─────────────────────────────────────────────────────────


def create_worktrees(
    slug: str,
    repo_names: list[str],
    paths: ProjectPaths,
) -> dict[str, Path]:
    """Create a worktree for each affected repo.

    Uses ``wt switch --create`` with a custom ``WORKTRUNK_WORKTREE_PATH``
    so the worktrees land inside ``specs/<slug>/repos/<repo>/``.

    Returns:
        Mapping of repo name -> worktree path.
    """
    worktree_root = paths.worktree_dir(slug)
    worktree_root.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}

    for name in repo_names:
        if name not in REPO_BY_NAME:
            print(f"  [skip] unknown repo {name!r}", file=sys.stderr)
            continue

        wt_path = paths.worktree_path(slug, name)
        repo_dir = paths.repo_path(name)

        if not repo_dir.exists():
            print(f"  [skip] repo {name!r} not cloned at {repo_dir}", file=sys.stderr)
            continue

        if wt_path.exists():
            print(f"  [ok]   worktree already exists: {wt_path}")
            result[name] = wt_path
            continue

        print(f"  [wt]   creating worktree for {name} on branch {slug}")

        with _repo_lock(paths, name):
            # Re-check after lock in case another process created it.
            if wt_path.exists():
                print(f"  [ok]   worktree appeared (raced): {wt_path}")
                result[name] = wt_path
                continue

            # Override the worktree path template so wt places it where we want.
            env = os.environ.copy()
            env["WORKTRUNK_WORKTREE_PATH"] = str(wt_path)

            try:
                subprocess.run(
                    [
                        "wt",
                        "switch",
                        "--create",
                        slug,
                        "-y",  # skip approval prompts
                        "--no-verify",  # skip hooks
                        "--no-cd",  # don't try to cd
                    ],
                    cwd=str(repo_dir),
                    env=env,
                    check=True,
                )
            except subprocess.CalledProcessError:
                # Fallback: use git worktree directly if wt has issues with
                # the env override.
                print(f"  [fallback] using git worktree add for {name}")
                _git_worktree_add(repo_dir, wt_path, slug)

            if wt_path.exists():
                result[name] = wt_path
            else:
                # wt might have placed it elsewhere; try to find it.
                found = _find_wt_path(repo_dir, slug)
                if found:
                    print(f"  [info] wt placed worktree at {found}, symlinking")
                    wt_path.parent.mkdir(parents=True, exist_ok=True)
                    os.symlink(found, wt_path)
                    result[name] = wt_path
                else:
                    print(
                        f"  [error] could not locate worktree for {name}",
                        file=sys.stderr,
                    )

    return result


def _git_worktree_add(repo_dir: Path, wt_path: Path, branch: str) -> None:
    """Direct ``git worktree add`` as fallback."""
    wt_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "worktree", "add", "-b", branch, str(wt_path)],
        cwd=str(repo_dir),
        check=True,
    )


def _find_wt_path(repo_dir: Path, branch: str) -> Path | None:
    """Ask git where it put the worktree for a given branch."""
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            candidate = Path(line.split(" ", 1)[1])
            if branch in candidate.name:
                return candidate
    return None


# ── Context setup ─────────────────────────────────────────────────────


def setup_engineer_context(
    slug: str,
    repo_name: str,
    paths: ProjectPaths,
) -> None:
    """Copy the per-repo spec into the worktree as AGENTS.md.

    This way the engineer agent picks it up automatically as project context.
    """
    spec_file = paths.spec_file(slug, f"{repo_name}-spec.md")
    wt_path = paths.worktree_path(slug, repo_name)
    agents_md = wt_path / "AGENTS.md"

    if not spec_file.exists():
        print(f"  [warn] no per-repo spec for {repo_name}, skipping AGENTS.md")
        return

    spec_content = spec_file.read_text(encoding="utf-8")

    # If an AGENTS.md already exists in the repo, prepend the spec to it.
    existing = ""
    if agents_md.exists():
        existing = agents_md.read_text(encoding="utf-8")

    header = (
        f"# Implementation Spec: {slug}\n\n"
        f"THIS FILE WAS GENERATED by the any-llm-world orchestrator.\n"
        f"It contains the implementation spec for this repository.\n\n"
        f"---\n\n"
    )

    combined = header + spec_content
    if existing:
        combined += f"\n\n---\n\n# Original AGENTS.md\n\n{existing}"

    agents_md.write_text(combined, encoding="utf-8")
    print(f"  [ok] wrote AGENTS.md for {repo_name}")


# ── Resume helpers ────────────────────────────────────────────────────


def worktrees_exist(slug: str, repo_names: list[str], paths: ProjectPaths) -> bool:
    """Check if all expected worktrees exist."""
    return all(paths.worktree_path(slug, name).exists() for name in repo_names)

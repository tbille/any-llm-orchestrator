"""Phase 6-7: Engineer agents (tmux) and code review loop."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

from lib.config import REPO_BY_NAME, ProjectPaths


# ── Tmux helpers ──────────────────────────────────────────────────────

TMUX = "tmux"


def _tmux_session_exists(session: str) -> bool:
    result = subprocess.run(
        [TMUX, "has-session", "-t", session],
        capture_output=True,
    )
    return result.returncode == 0


def _tmux_create_session(session: str, first_pane_cmd: str, cwd: str) -> None:
    """Create a new tmux session with the first pane running a command."""
    subprocess.run(
        [
            TMUX,
            "new-session",
            "-d",  # detached
            "-s",
            session,  # session name
            "-c",
            cwd,  # working directory
            first_pane_cmd,
        ],
        check=True,
    )


def _tmux_add_pane(session: str, cmd: str, cwd: str) -> None:
    """Split the current window to add a new pane."""
    subprocess.run(
        [
            TMUX,
            "split-window",
            "-t",
            session,
            "-c",
            cwd,
            cmd,
        ],
        check=True,
    )
    # Re-tile to keep panes evenly distributed.
    subprocess.run(
        [TMUX, "select-layout", "-t", session, "tiled"],
        check=True,
    )


def _tmux_attach(session: str) -> None:
    """Attach to the tmux session so the user can watch."""
    subprocess.run([TMUX, "attach-session", "-t", session])


def _tmux_wait_for_all_panes(session: str, poll_interval: float = 5.0) -> None:
    """Block until all panes in the session have finished their commands."""
    while True:
        result = subprocess.run(
            [
                TMUX,
                "list-panes",
                "-t",
                session,
                "-F",
                "#{pane_dead}",
            ],
            capture_output=True,
            text=True,
        )
        statuses = result.stdout.strip().splitlines()
        # pane_dead is "1" when the command has exited.
        if statuses and all(s.strip() == "1" for s in statuses):
            break
        time.sleep(poll_interval)


# ── Phase 6: Engineers ────────────────────────────────────────────────


def _build_engineer_command(
    slug: str,
    repo_name: str,
    paths: ProjectPaths,
    *,
    is_fix_round: bool = False,
    review_file: Path | None = None,
) -> str:
    """Build the opencode run command for an engineer agent."""
    wt_path = paths.worktree_path(slug, repo_name)
    spec_file = paths.spec_file(slug, f"{repo_name}-spec.md")
    log_file = paths.logs_dir(slug) / f"{repo_name}-engineer.log"
    repo_info = REPO_BY_NAME.get(repo_name)
    lang = repo_info.language if repo_info else "unknown"

    file_args: list[str] = []
    if spec_file.exists():
        file_args += ["-f", str(spec_file)]
    if review_file and review_file.exists():
        file_args += ["-f", str(review_file)]

    lint_test_suffix = (
        " Before committing, you MUST: "
        "run the project linter and fix all lint errors, "
        "run the full test suite and make sure all tests pass, "
        "only commit once lint and tests are green. "
        "Look at the project config files (pyproject.toml, Cargo.toml, "
        "package.json, Makefile, etc.) to find the correct lint and test commands."
    )

    if is_fix_round and review_file:
        message = (
            f"Review the code review feedback in the attached review file and "
            f"fix the issues found. This is a {lang} project."
            f"{lint_test_suffix}"
        )
    else:
        message = (
            f"Implement the feature described in the attached spec for this "
            f"{lang} project. Follow the repository's existing patterns and "
            f"conventions. Write tests for your changes."
            f"{lint_test_suffix}"
        )

    # For simple-bug path (no spec file), use the input directly.
    if not spec_file.exists():
        input_file = paths.spec_file(slug, "input.md")
        if input_file.exists():
            file_args += ["-f", str(input_file)]
        message = (
            f"Fix the bug described in the attached issue for this {lang} project. "
            f"Follow the repository's existing patterns."
            f"{lint_test_suffix}"
        )

    # Write the prompt to a file to avoid shell escaping issues with
    # multi-line strings passed through tmux.
    prompt_file = paths.logs_dir(slug) / f"{repo_name}-engineer-prompt.md"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(message, encoding="utf-8")

    parts = [
        "opencode",
        "run",
        "--dir",
        shlex.quote(str(wt_path)),
        "--dangerously-skip-permissions",
    ]
    parts += file_args
    # Pass prompt via file to avoid shell quoting issues in tmux.
    parts += ["-f", shlex.quote(str(prompt_file))]
    parts.append(shlex.quote("Follow the instructions in the attached prompt file."))

    # Wrap in a shell command that tees output to a log file.
    cmd = " ".join(parts)
    return f'{cmd} 2>&1 | tee {shlex.quote(str(log_file))}; echo "[DONE: {repo_name}]"'


def run_engineers(
    slug: str,
    repo_names: list[str],
    paths: ProjectPaths,
    *,
    is_fix_round: bool = False,
) -> None:
    """Launch one opencode engineer per repo in tmux panes.

    Args:
        is_fix_round: If True, engineers address code review feedback.
    """
    suffix = "-fix" if is_fix_round else ""
    session_name = f"eng-{slug}{suffix}"

    if _tmux_session_exists(session_name):
        print(f"  [info] tmux session {session_name!r} already exists, attaching.")
        _tmux_attach(session_name)
        return

    print(f"\n── Phase 6: Engineers {'(fix round)' if is_fix_round else ''} ─────")
    print(f"  Session: {session_name}")
    print(f"  Repos:   {', '.join(repo_names)}")
    print("────────────────────────────────────────────────────\n")

    paths.logs_dir(slug).mkdir(parents=True, exist_ok=True)

    for i, name in enumerate(repo_names):
        review_file = (
            paths.spec_file(slug, f"{name}-review.md") if is_fix_round else None
        )
        cmd = _build_engineer_command(
            slug,
            name,
            paths,
            is_fix_round=is_fix_round,
            review_file=review_file,
        )
        wt_path = str(paths.worktree_path(slug, name))

        if i == 0:
            _tmux_create_session(session_name, cmd, wt_path)
        else:
            _tmux_add_pane(session_name, cmd, wt_path)

    print(f"  Attaching to tmux session. Use Ctrl-B D to detach.\n")
    _tmux_attach(session_name)

    # After user detaches (or all panes finish), wait for completion.
    print("  Waiting for all engineer agents to finish...")
    _tmux_wait_for_all_panes(session_name)
    print("  All engineers done.\n")


# ── Phase 7a: Per-repo code review ───────────────────────────────────


def _build_review_command(
    slug: str,
    repo_name: str,
    paths: ProjectPaths,
) -> str:
    """Build the opencode run command for a code reviewer agent."""
    wt_path = paths.worktree_path(slug, repo_name)
    spec_file = paths.spec_file(slug, f"{repo_name}-spec.md")
    review_file = paths.spec_file(slug, f"{repo_name}-review.md")
    log_file = paths.logs_dir(slug) / f"{repo_name}-review.log"
    repo_info = REPO_BY_NAME.get(repo_name)
    lang = repo_info.language if repo_info else "unknown"

    file_args: list[str] = []
    if spec_file.exists():
        file_args += ["-f", str(spec_file)]

    message = (
        f"Review the code changes in this {lang} repository. "
        f"Compare against the attached spec. Check for: "
        f"spec compliance, code quality and {lang}-idiomatic patterns, "
        f"test coverage, error handling, backwards compatibility. "
        f"Write your review to: {review_file} "
        f"Use this format: "
        f"## Status: PASS or NEEDS_CHANGES "
        f"## Issues Found (list each issue) "
        f"## Recommendations (list improvements)"
    )

    prompt_file = paths.logs_dir(slug) / f"{repo_name}-review-prompt.md"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(message, encoding="utf-8")

    parts = [
        "opencode",
        "run",
        "--dir",
        shlex.quote(str(wt_path)),
        "--dangerously-skip-permissions",
    ]
    parts += file_args
    parts += ["-f", shlex.quote(str(prompt_file))]
    parts.append(shlex.quote("Follow the instructions in the attached prompt file."))

    cmd = " ".join(parts)
    return f'{cmd} 2>&1 | tee {shlex.quote(str(log_file))}; echo "[REVIEW DONE: {repo_name}]"'


def run_code_reviews(slug: str, repo_names: list[str], paths: ProjectPaths) -> None:
    """Launch per-repo code reviewers in tmux panes."""
    session_name = f"review-{slug}"

    if _tmux_session_exists(session_name):
        print(f"  [info] tmux session {session_name!r} already exists, attaching.")
        _tmux_attach(session_name)
        return

    print(f"\n── Phase 7a: Per-repo Code Review ──────────────────")
    print(f"  Session: {session_name}")
    print(f"  Repos:   {', '.join(repo_names)}")
    print("────────────────────────────────────────────────────\n")

    for i, name in enumerate(repo_names):
        cmd = _build_review_command(slug, name, paths)
        wt_path = str(paths.worktree_path(slug, name))

        if i == 0:
            _tmux_create_session(session_name, cmd, wt_path)
        else:
            _tmux_add_pane(session_name, cmd, wt_path)

    print(f"  Attaching to tmux session. Use Ctrl-B D to detach.\n")
    _tmux_attach(session_name)

    print("  Waiting for all reviewers to finish...")
    _tmux_wait_for_all_panes(session_name)
    print("  All reviews done.\n")


# ── Phase 7b: Cross-repo consistency review ──────────────────────────


def run_cross_repo_review(
    slug: str, repo_names: list[str], paths: ProjectPaths
) -> None:
    """Single headless agent that checks cross-repo interface alignment."""
    print("\n── Phase 7b: Cross-repo Consistency Review ─────────")

    tech_spec = paths.spec_file(slug, "tech-spec.md")
    cross_review_file = paths.spec_file(slug, "cross-review.md")

    file_args: list[str] = []
    if tech_spec.exists():
        file_args += ["-f", str(tech_spec)]

    # Collect diffs from each worktree.
    diff_sections: list[str] = []
    for name in repo_names:
        wt_path = paths.worktree_path(slug, name)
        if not wt_path.exists():
            continue
        result = subprocess.run(
            ["git", "diff", "HEAD~1..HEAD", "--stat"],
            cwd=str(wt_path),
            capture_output=True,
            text=True,
        )
        if result.stdout.strip():
            diff_sections.append(f"### {name}\n```\n{result.stdout.strip()}\n```")

        # Also attach per-repo review files.
        review = paths.spec_file(slug, f"{name}-review.md")
        if review.exists():
            file_args += ["-f", str(review)]

    diffs_text = "\n\n".join(diff_sections) if diff_sections else "No diffs available."

    message = (
        f"You are reviewing changes across multiple repositories for consistency.\n\n"
        f"## Change summaries\n{diffs_text}\n\n"
        f"Check for:\n"
        f"- Interface alignment: do the shared API contracts match across repos?\n"
        f"- Type consistency: are shared types defined the same way?\n"
        f"- Version compatibility: will these changes work together?\n"
        f"- Integration gaps: anything the isolated engineers missed?\n\n"
        f"Write your review to: {cross_review_file}"
    )

    print(f"  Output: {cross_review_file}")
    print("  Running cross-repo review (headless)...\n")

    subprocess.run(
        [
            "opencode",
            "run",
            "--dir",
            str(paths.root),
            "--dangerously-skip-permissions",
            *file_args,
            message,
        ],
        cwd=str(paths.root),
    )

    print("  Cross-repo review complete.\n")


# ── Review loop ───────────────────────────────────────────────────────


def _any_repo_needs_changes(
    slug: str, repo_names: list[str], paths: ProjectPaths
) -> list[str]:
    """Check per-repo review files and return repos that need fixes."""
    needs_fix: list[str] = []
    for name in repo_names:
        review_file = paths.spec_file(slug, f"{name}-review.md")
        if not review_file.exists():
            continue
        content = review_file.read_text(encoding="utf-8").upper()
        if "NEEDS_CHANGES" in content:
            needs_fix.append(name)
    return needs_fix


def run_review_loop(
    slug: str,
    repo_names: list[str],
    paths: ProjectPaths,
    *,
    max_rounds: int = 2,
) -> None:
    """Orchestrate: engineer -> review -> fix -> review ... up to max_rounds."""
    for round_num in range(1, max_rounds + 1):
        print(f"\n{'=' * 56}")
        print(f"  Review-fix round {round_num}/{max_rounds}")
        print(f"{'=' * 56}")

        # Code review.
        run_code_reviews(slug, repo_names, paths)

        # Check which repos need fixes.
        needs_fix = _any_repo_needs_changes(slug, repo_names, paths)
        if not needs_fix:
            print("  All repos passed review. No fixes needed.")
            break

        print(f"  Repos needing fixes: {', '.join(needs_fix)}")

        if round_num < max_rounds:
            # Re-run engineers only for repos that need fixes.
            run_engineers(slug, needs_fix, paths, is_fix_round=True)
        else:
            print(f"  Max review rounds ({max_rounds}) reached.")
            print("  Remaining issues are noted in the review files.")

    # Always run cross-repo review at the end.
    if len(repo_names) > 1:
        run_cross_repo_review(slug, repo_names, paths)

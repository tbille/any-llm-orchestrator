"""Phase 8: PR creation per repo and CI monitoring loop."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

from lib.config import REPO_BY_NAME, ProjectPaths
from lib.engineer import (
    _tmux_add_pane,
    _tmux_attach,
    _tmux_create_session,
    _tmux_session_exists,
    _tmux_wait_for_all_panes,
    run_engineers,
)


# ── PR template detection ─────────────────────────────────────────────


def _find_pr_template(worktree: Path) -> Path | None:
    """Locate a pull-request template in the worktree.

    GitHub supports several locations; check them in priority order.
    """
    candidates = [
        worktree / ".github" / "pull_request_template.md",
        worktree / ".github" / "PULL_REQUEST_TEMPLATE.md",
        worktree / "pull_request_template.md",
        worktree / "PULL_REQUEST_TEMPLATE.md",
        worktree / "docs" / "pull_request_template.md",
    ]
    # Also check the PULL_REQUEST_TEMPLATE/ directory for multiple templates.
    template_dir = worktree / ".github" / "PULL_REQUEST_TEMPLATE"
    if template_dir.is_dir():
        for child in sorted(template_dir.iterdir()):
            if child.suffix.lower() == ".md":
                return child

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


# ── PR creation via opencode agent ────────────────────────────────────


def _build_pr_command(
    slug: str,
    repo_name: str,
    paths: ProjectPaths,
) -> str:
    """Build the opencode run command for the PR-creator agent."""
    wt_path = paths.worktree_path(slug, repo_name)
    spec_file = paths.spec_file(slug, f"{repo_name}-spec.md")
    log_file = paths.logs_dir(slug) / f"{repo_name}-pr.log"
    repo_info = REPO_BY_NAME.get(repo_name)
    lang = repo_info.language if repo_info else "unknown"

    file_args: list[str] = []
    if spec_file.exists():
        file_args += ["-f", str(spec_file)]

    template = _find_pr_template(wt_path)
    template_instruction = ""
    if template:
        file_args += ["-f", str(template)]
        template_instruction = (
            f"\n\nIMPORTANT: This repository has a PR template at {template.name}. "
            f"It is attached. You MUST follow its structure when writing the PR body."
        )

    message = (
        f"Create a pull request for the changes in this {lang} repository. "
        f"Steps: "
        f"1. Review all uncommitted changes and commit them if needed. "
        f"2. Push the branch to the remote. "
        f"3. Create a pull request using `gh pr create`. "
        f"4. Write a clear title and description summarizing the changes. "
        f"5. Reference the original issue if applicable."
        f"{template_instruction}"
    )

    prompt_file = paths.logs_dir(slug) / f"{repo_name}-pr-prompt.md"
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
    return (
        f'{cmd} 2>&1 | tee {shlex.quote(str(log_file))}; echo "[PR DONE: {repo_name}]"'
    )


def create_pull_requests(
    slug: str,
    repo_names: list[str],
    paths: ProjectPaths,
) -> None:
    """Launch PR-creation agents in tmux panes, one per repo."""
    session_name = f"pr-{slug}"

    if _tmux_session_exists(session_name):
        print(f"  [info] tmux session {session_name!r} already exists, attaching.")
        _tmux_attach(session_name)
        return

    print(f"\n── Phase 8: Pull Requests ──────────────────────────")
    print(f"  Session: {session_name}")
    print(f"  Repos:   {', '.join(repo_names)}")
    print("────────────────────────────────────────────────────\n")

    paths.logs_dir(slug).mkdir(parents=True, exist_ok=True)

    for i, name in enumerate(repo_names):
        cmd = _build_pr_command(slug, name, paths)
        wt_path = str(paths.worktree_path(slug, name))

        if i == 0:
            _tmux_create_session(session_name, cmd, wt_path)
        else:
            _tmux_add_pane(session_name, cmd, wt_path)

    print("  Attaching to tmux session. Use Ctrl-B D to detach.\n")
    _tmux_attach(session_name)

    print("  Waiting for all PR agents to finish...")
    _tmux_wait_for_all_panes(session_name)
    print("  All PRs created.\n")


# ── CI monitoring (pure script, no agent) ─────────────────────────────

_CI_POLL_INTERVAL = 30  # seconds
_CI_TIMEOUT = 1800  # 30 minutes max wait


def _get_pr_number(worktree: Path) -> str | None:
    """Get the PR number for the current branch using gh."""
    result = subprocess.run(
        ["gh", "pr", "view", "--json", "number", "--jq", ".number"],
        cwd=str(worktree),
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def _get_ci_status(worktree: Path) -> tuple[str, str]:
    """Check CI status for the current branch's PR.

    Returns:
        (status, detail) where status is one of:
        "pass", "fail", "pending", "no-pr", "no-ci"
    """
    result = subprocess.run(
        [
            "gh",
            "pr",
            "checks",
            "--json",
            "name,state,conclusion",
        ],
        cwd=str(worktree),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        # No PR or gh error.
        if "no pull requests" in result.stderr.lower():
            return "no-pr", "No pull request found for this branch"
        return "no-ci", result.stderr.strip()[:200]

    try:
        checks = json.loads(result.stdout)
    except json.JSONDecodeError:
        return "no-ci", "Could not parse CI status"

    if not checks:
        return "no-ci", "No CI checks configured"

    # Aggregate status across all checks.
    states = {c.get("state", "").upper() for c in checks}
    conclusions = {c.get("conclusion", "").upper() for c in checks}

    if "IN_PROGRESS" in states or "QUEUED" in states or "PENDING" in states:
        running = [
            c["name"]
            for c in checks
            if c.get("state", "").upper() in ("IN_PROGRESS", "QUEUED", "PENDING")
        ]
        return "pending", f"Running: {', '.join(running[:5])}"

    if "FAILURE" in conclusions or "TIMED_OUT" in conclusions:
        failed = [
            c["name"]
            for c in checks
            if c.get("conclusion", "").upper() in ("FAILURE", "TIMED_OUT")
        ]
        return "fail", f"Failed: {', '.join(failed)}"

    if all(c.get("conclusion", "").upper() == "SUCCESS" for c in checks):
        return "pass", f"All {len(checks)} checks passed"

    return "pending", "Some checks still running"


def _collect_ci_failure_logs(worktree: Path) -> str:
    """Pull the failed check names + recent log hints via gh."""
    result = subprocess.run(
        [
            "gh",
            "pr",
            "checks",
            "--json",
            "name,state,conclusion,detailsUrl",
        ],
        cwd=str(worktree),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "Could not fetch CI failure details."

    try:
        checks = json.loads(result.stdout)
    except json.JSONDecodeError:
        return "Could not parse CI check results."

    lines = ["# CI Failures\n"]
    for check in checks:
        conclusion = check.get("conclusion", "").upper()
        if conclusion in ("FAILURE", "TIMED_OUT"):
            name = check.get("name", "unknown")
            url = check.get("detailsUrl", "N/A")
            lines.append(f"## {name}")
            lines.append(f"- Conclusion: {conclusion}")
            lines.append(f"- Details: {url}")
            lines.append("")

    return "\n".join(lines)


def watch_ci(
    slug: str,
    repo_names: list[str],
    paths: ProjectPaths,
    *,
    max_fix_rounds: int = 2,
) -> None:
    """Poll CI for all repos. If any fail, send engineers to fix and re-push.

    This is pure Python orchestration -- no agents involved in the monitoring.
    Agents are only called when fixes are needed.
    """
    for fix_round in range(max_fix_rounds + 1):
        round_label = "Initial" if fix_round == 0 else f"Fix round {fix_round}"

        print(f"\n── Phase 9: CI Watch ({round_label}) ───────────────────")
        print(f"  Monitoring repos: {', '.join(repo_names)}")
        print(f"  Poll interval: {_CI_POLL_INTERVAL}s, timeout: {_CI_TIMEOUT}s")
        print("────────────────────────────────────────────────────\n")

        # Wait for all CIs to reach a terminal state.
        ci_results = _poll_until_complete(slug, repo_names, paths)

        # Partition into pass / fail / no-ci.
        passed = [name for name, (st, _) in ci_results.items() if st == "pass"]
        failed = [name for name, (st, _) in ci_results.items() if st == "fail"]
        no_ci = [
            name for name, (st, _) in ci_results.items() if st in ("no-ci", "no-pr")
        ]

        print(f"\n  CI Results:")
        for name in passed:
            print(f"    [PASS] {name}")
        for name in failed:
            _, detail = ci_results[name]
            print(f"    [FAIL] {name} -- {detail}")
        for name in no_ci:
            _, detail = ci_results[name]
            print(f"    [SKIP] {name} -- {detail}")

        if not failed:
            print("\n  All CI checks passed (or no CI configured).")
            break

        if fix_round >= max_fix_rounds:
            print(f"\n  Max CI fix rounds ({max_fix_rounds}) reached.")
            print("  Remaining failures need manual attention.")
            break

        # Collect failure details and run engineers to fix.
        print(f"\n  {len(failed)} repo(s) have CI failures. Sending to engineers...")

        for name in failed:
            wt_path = paths.worktree_path(slug, name)
            failure_log = _collect_ci_failure_logs(wt_path)
            ci_log_file = paths.spec_file(slug, f"{name}-ci-failures.md")
            ci_log_file.write_text(failure_log, encoding="utf-8")

        _run_ci_fix_engineers(slug, failed, paths)

        # After fixing, push again.
        _push_branches(slug, failed, paths)


def _poll_until_complete(
    slug: str,
    repo_names: list[str],
    paths: ProjectPaths,
) -> dict[str, tuple[str, str]]:
    """Poll until all repos have a terminal CI status."""
    results: dict[str, tuple[str, str]] = {}
    remaining = set(repo_names)
    elapsed = 0

    while remaining and elapsed < _CI_TIMEOUT:
        for name in list(remaining):
            wt_path = paths.worktree_path(slug, name)
            status, detail = _get_ci_status(wt_path)

            if status in ("pass", "fail", "no-ci", "no-pr"):
                results[name] = (status, detail)
                remaining.discard(name)
                print(f"  [{status.upper():7s}] {name}: {detail}")
            else:
                print(f"  [PENDING] {name}: {detail}")

        if remaining:
            time.sleep(_CI_POLL_INTERVAL)
            elapsed += _CI_POLL_INTERVAL

    # Anything still remaining after timeout is treated as pending/fail.
    for name in remaining:
        results[name] = ("fail", "CI timed out after {_CI_TIMEOUT}s")

    return results


def _run_ci_fix_engineers(
    slug: str,
    repo_names: list[str],
    paths: ProjectPaths,
) -> None:
    """Launch engineers to fix CI failures."""
    from lib.engineer import (
        _tmux_create_session,
        _tmux_add_pane,
        _tmux_attach,
        _tmux_wait_for_all_panes,
    )

    session_name = f"ci-fix-{slug}"

    print(f"\n  Launching CI fix engineers in tmux: {session_name}")
    paths.logs_dir(slug).mkdir(parents=True, exist_ok=True)

    for i, name in enumerate(repo_names):
        cmd = _build_ci_fix_command(slug, name, paths)
        wt_path = str(paths.worktree_path(slug, name))

        if i == 0:
            _tmux_create_session(session_name, cmd, wt_path)
        else:
            _tmux_add_pane(session_name, cmd, wt_path)

    print("  Attaching to tmux session. Use Ctrl-B D to detach.\n")
    _tmux_attach(session_name)

    print("  Waiting for CI fix engineers to finish...")
    _tmux_wait_for_all_panes(session_name)
    print("  CI fix engineers done.\n")


def _build_ci_fix_command(
    slug: str,
    repo_name: str,
    paths: ProjectPaths,
) -> str:
    """Build an opencode run command to fix CI failures."""
    wt_path = paths.worktree_path(slug, repo_name)
    ci_log_file = paths.spec_file(slug, f"{repo_name}-ci-failures.md")
    log_file = paths.logs_dir(slug) / f"{repo_name}-ci-fix.log"
    repo_info = REPO_BY_NAME.get(repo_name)
    lang = repo_info.language if repo_info else "unknown"

    file_args: list[str] = []
    if ci_log_file.exists():
        file_args += ["-f", str(ci_log_file)]

    message = (
        f"The CI pipeline is failing for this {lang} project. "
        f"The attached file lists the failed checks. "
        f"Investigate the failures by running the linter and tests locally. "
        f"Fix the issues. Make sure the linter passes and all tests pass. "
        f"Commit your fixes. Do NOT push -- the orchestrator will handle that."
    )

    prompt_file = paths.logs_dir(slug) / f"{repo_name}-ci-fix-prompt.md"
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
    return f'{cmd} 2>&1 | tee {shlex.quote(str(log_file))}; echo "[CI FIX DONE: {repo_name}]"'


def _push_branches(
    slug: str,
    repo_names: list[str],
    paths: ProjectPaths,
) -> None:
    """Push updated branches after CI fixes."""
    for name in repo_names:
        wt_path = paths.worktree_path(slug, name)
        print(f"  Pushing {name}...")
        subprocess.run(
            ["git", "push"],
            cwd=str(wt_path),
        )

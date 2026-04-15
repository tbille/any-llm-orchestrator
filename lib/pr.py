"""PR and CI helper functions shared by repo_runner.py."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


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
    template_dir = worktree / ".github" / "PULL_REQUEST_TEMPLATE"
    if template_dir.is_dir():
        for child in sorted(template_dir.iterdir()):
            if child.suffix.lower() == ".md":
                return child

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


# ── CI status helpers ─────────────────────────────────────────────────

# gh pr checks --json only supports these fields:
#   bucket, completedAt, description, event, link, name, startedAt, state, workflow
# It does NOT have a "conclusion" field.  All status info is in "state":
#   SUCCESS, FAILURE, PENDING, QUEUED, IN_PROGRESS, SKIPPED, CANCELLED, TIMED_OUT


def _get_ci_status(worktree: Path) -> tuple[str, str]:
    """Check CI status for the current branch's PR.

    Returns:
        (status, detail) where status is one of:
        "pass", "fail", "pending", "no-pr", "no-ci"
    """
    result = subprocess.run(
        ["gh", "pr", "checks", "--json", "name,state"],
        cwd=str(worktree),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        stderr = result.stderr.lower()
        if "no pull requests" in stderr or "no open pull requests" in stderr:
            return "no-pr", "No pull request found for this branch"
        return "no-ci", result.stderr.strip()[:200]

    try:
        checks = json.loads(result.stdout)
    except json.JSONDecodeError:
        return "no-ci", "Could not parse CI status"

    if not checks:
        return "no-ci", "No CI checks configured"

    # Filter out SKIPPED checks -- they don't indicate pass or fail.
    active = [c for c in checks if c.get("state", "").upper() != "SKIPPED"]
    if not active:
        return "no-ci", "All checks skipped"

    states = {c.get("state", "").upper() for c in active}

    # Check for in-progress first.
    pending_states = {"IN_PROGRESS", "QUEUED", "PENDING"}
    if states & pending_states:
        running = [
            c["name"] for c in active if c.get("state", "").upper() in pending_states
        ]
        return "pending", f"Running: {', '.join(running[:5])}"

    # Check for failures.
    fail_states = {"FAILURE", "TIMED_OUT", "CANCELLED"}
    if states & fail_states:
        failed = [
            c["name"] for c in active if c.get("state", "").upper() in fail_states
        ]
        return "fail", f"Failed: {', '.join(failed)}"

    # All remaining active checks must be SUCCESS.
    if all(c.get("state", "").upper() == "SUCCESS" for c in active):
        return "pass", f"All {len(active)} checks passed"

    return "pending", "Some checks still running"


def _collect_ci_failure_logs(worktree: Path) -> str:
    """Pull the failed check names + details URL via gh."""
    result = subprocess.run(
        ["gh", "pr", "checks", "--json", "name,state,link"],
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

    fail_states = {"FAILURE", "TIMED_OUT", "CANCELLED"}
    lines = ["# CI Failures\n"]
    for check in checks:
        state = check.get("state", "").upper()
        if state in fail_states:
            name = check.get("name", "unknown")
            url = check.get("link", "N/A")
            lines.append(f"## {name}")
            lines.append(f"- State: {state}")
            lines.append(f"- Details: {url}")
            lines.append("")

    return "\n".join(lines)

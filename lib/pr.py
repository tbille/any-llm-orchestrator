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


def _get_ci_status(worktree: Path) -> tuple[str, str]:
    """Check CI status for the current branch's PR.

    Returns:
        (status, detail) where status is one of:
        "pass", "fail", "pending", "no-pr", "no-ci"
    """
    result = subprocess.run(
        ["gh", "pr", "checks", "--json", "name,state,conclusion"],
        cwd=str(worktree),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        if "no pull requests" in result.stderr.lower():
            return "no-pr", "No pull request found for this branch"
        return "no-ci", result.stderr.strip()[:200]

    try:
        checks = json.loads(result.stdout)
    except json.JSONDecodeError:
        return "no-ci", "Could not parse CI status"

    if not checks:
        return "no-ci", "No CI checks configured"

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
    """Pull the failed check names + details URL via gh."""
    result = subprocess.run(
        ["gh", "pr", "checks", "--json", "name,state,conclusion,detailsUrl"],
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

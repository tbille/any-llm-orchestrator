"""Status tracking for the orchestrator dashboard."""

from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from lib.config import ProjectPaths


# ── Phase definitions ─────────────────────────────────────────────────

# Ordered list of all phases.  The pipeline skips some depending on triage type.
# Workspace runs early so all agents have access to repo worktrees.
# "build" is a per-repo parallel phase: engineer -> review -> PR -> CI.
# "cross-review" is the only sync point after all repos finish.
ALL_PHASES = (
    "intake",
    "workspace",
    "pm",
    "debate",
    "designer",
    "architect",
    "build",
    "cross-review",
)

# Phases used per triage path.
PHASES_BY_TYPE = {
    "feature": ALL_PHASES,
    "complex-bug": ("intake", "workspace", "architect", "build", "cross-review"),
    "simple-bug": ("intake", "workspace", "build", "cross-review"),
}

PHASE_LABELS = {
    "intake": "Intake",
    "workspace": "Workspace",
    "pm": "PM",
    "debate": "Debate",
    "designer": "Designer",
    "architect": "Architect",
    "build": "Build",
    "cross-review": "X-Review",
}


# ── Read / write status.json ─────────────────────────────────────────


def _status_path(slug: str, paths: ProjectPaths) -> Path:
    return paths.spec_file(slug, "status.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_status(slug: str, paths: ProjectPaths) -> dict | None:
    """Load the status file for a single feature, or None."""
    p = _status_path(slug, paths)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _save_status(slug: str, data: dict, paths: ProjectPaths) -> None:
    paths.ensure_spec_dirs(slug)
    data["updated_at"] = _now()
    _status_path(slug, paths).write_text(json.dumps(data, indent=2), encoding="utf-8")


def init_status(
    slug: str,
    triage_type: str,
    repos: list[str],
    paths: ProjectPaths,
) -> dict:
    """Create (or reset) the status file for a new feature."""
    applicable = PHASES_BY_TYPE.get(triage_type, ALL_PHASES)
    phases: dict[str, dict] = {}
    for phase in ALL_PHASES:
        if phase in applicable:
            phases[phase] = {"status": "pending"}
        else:
            phases[phase] = {"status": "skipped"}

    data = {
        "slug": slug,
        "triage_type": triage_type,
        "repos": repos,
        "current_phase": applicable[0],
        "phases": phases,
        "created_at": _now(),
        "updated_at": _now(),
    }
    _save_status(slug, data, paths)
    return data


def update_phase(
    slug: str,
    phase: str,
    status: str,
    paths: ProjectPaths,
    *,
    repo_statuses: dict[str, str] | None = None,
) -> None:
    """Update a single phase's status in the status file.

    Args:
        slug: Feature slug.
        phase: Phase name (one of ALL_PHASES).
        status: "pending", "running", "done", "failed", "skipped".
        paths: Project paths.
        repo_statuses: Optional per-repo status map, e.g.
            ``{"any-llm": "running", "gateway": "done"}``.
    """
    data = load_status(slug, paths)
    if data is None:
        # Status file doesn't exist yet (e.g. --resume with old data).
        # Create a minimal one.
        data = {
            "slug": slug,
            "triage_type": "unknown",
            "repos": [],
            "current_phase": phase,
            "phases": {},
            "created_at": _now(),
        }

    phase_data = data.setdefault("phases", {}).setdefault(phase, {})
    phase_data["status"] = status

    if status == "running":
        phase_data["started_at"] = _now()
        data["current_phase"] = phase
    elif status in ("done", "failed"):
        phase_data["finished_at"] = _now()

    if repo_statuses is not None:
        phase_data["repos"] = repo_statuses

    _save_status(slug, data, paths)


def update_repo_step(
    slug: str,
    repo_name: str,
    step: str,
    paths: ProjectPaths,
) -> None:
    """Update a single repo's build step in status.json.

    Called by ``repo_runner.py`` as each repo progresses through
    engineer -> review -> pr -> ci-watch -> done.
    """
    data = load_status(slug, paths)
    if data is None:
        return

    repo_progress = data.setdefault("repo_progress", {})
    prev = repo_progress.get(repo_name, {})

    now = _now()
    entry: dict = {"step": step, "updated_at": now}

    # Track when this step started.  If the step changed, record a
    # new started_at; otherwise preserve the existing one.
    if prev.get("step") != step:
        entry["started_at"] = now
        # Record previous step in history for timeline view.
        history = prev.get("history", [])
        if prev.get("step") and prev.get("started_at"):
            history.append(
                {
                    "step": prev["step"],
                    "started_at": prev["started_at"],
                    "finished_at": now,
                }
            )
        entry["history"] = history
    else:
        entry["started_at"] = prev.get("started_at", now)
        entry["history"] = prev.get("history", [])

    repo_progress[repo_name] = entry

    # Keep current_phase as "build" while repos are running.
    data["current_phase"] = "build"

    _save_status(slug, data, paths)


# ── Load all features ─────────────────────────────────────────────────


def load_all_statuses(paths: ProjectPaths) -> list[dict]:
    """Read status.json from every spec directory."""
    results: list[dict] = []
    if not paths.specs_dir.exists():
        return results
    for child in sorted(paths.specs_dir.iterdir()):
        if not child.is_dir():
            continue
        status = load_status(child.name, paths)
        if status is not None:
            results.append(status)
    return results


# ── Live log data ─────────────────────────────────────────────────────

# ANSI escape code pattern for stripping terminal colors from log lines.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def get_log_tails(
    slug: str,
    repo_names: list[str],
    paths: ProjectPaths,
    *,
    tail_lines: int = 3,
    active_threshold_secs: float = 30.0,
) -> dict[str, dict]:
    """Read the last few lines and size of each agent log file.

    Returns a map of repo name -> {
        "size_bytes": int,
        "last_lines": list[str],   # stripped of ANSI codes
        "phase": str,              # which log was found (engineer/review/pr/ci-fix)
        "active": bool,            # True if the log was modified recently
        "mtime": str,              # ISO timestamp of last modification
    }.
    """
    info: dict[str, dict] = {}
    logs_dir = paths.logs_dir(slug)
    if not logs_dir.exists():
        return info

    now = time.time()

    # Check logs in priority order (most recent phase first).
    log_phases = ("ci-fix", "pr", "review", "engineer")

    for name in repo_names:
        for phase in log_phases:
            log_file = logs_dir / f"{name}-{phase}.log"
            if not log_file.exists() or log_file.stat().st_size == 0:
                continue

            stat = log_file.stat()
            size = stat.st_size
            mtime = stat.st_mtime
            active = (now - mtime) < active_threshold_secs

            try:
                raw = log_file.read_text(encoding="utf-8", errors="replace")
                lines = raw.strip().splitlines()
                # Take last N non-empty lines, strip ANSI codes.
                tail = []
                for line in reversed(lines):
                    cleaned = _ANSI_RE.sub("", line).strip()
                    if cleaned:
                        tail.append(cleaned)
                    if len(tail) >= tail_lines:
                        break
                tail.reverse()
            except OSError:
                tail = []

            info[name] = {
                "size_bytes": size,
                "last_lines": tail,
                "phase": phase,
                "active": active,
                "mtime": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
            }
            break  # Use the most recent phase log found.

    return info


# ── Live tmux data ────────────────────────────────────────────────────


def get_live_tmux_sessions() -> dict[str, list[str]]:
    """Return a map of slug -> list of active tmux session names.

    Session names are expected to follow the pattern ``<type>-<slug>``,
    e.g. ``build-add-batch-api``.
    """
    result = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {}

    slug_sessions: dict[str, list[str]] = {}
    for line in result.stdout.strip().splitlines():
        name = line.strip()
        # Parse prefix-slug pattern.
        for prefix in ("build-", "eng-", "review-", "pr-", "ci-fix-"):
            if name.startswith(prefix):
                slug = name[len(prefix) :]
                # Handle suffixes like "-fix".
                if slug.endswith("-fix"):
                    slug = slug[: -len("-fix")]
                slug_sessions.setdefault(slug, []).append(name)
                break
    return slug_sessions


# ── Live PR / CI data ─────────────────────────────────────────────────


def get_pr_info_for_feature(
    slug: str,
    repo_names: list[str],
    paths: ProjectPaths,
) -> dict[str, dict]:
    """Query ``gh`` for PR URL and check status per repo.

    Returns a map of repo name -> {"url": ..., "ci": "pass"|"fail"|"pending"|"none"}.
    """
    info: dict[str, dict] = {}
    for name in repo_names:
        wt_path = paths.worktree_path(slug, name)
        if not wt_path.exists():
            info[name] = {"url": None, "ci": "none"}
            continue

        # Get PR URL.
        pr_result = subprocess.run(
            ["gh", "pr", "view", "--json", "url", "--jq", ".url"],
            cwd=str(wt_path),
            capture_output=True,
            text=True,
        )
        url = pr_result.stdout.strip() if pr_result.returncode == 0 else None

        # Get CI status.  gh pr checks uses "state" not "conclusion".
        ci_result = subprocess.run(
            ["gh", "pr", "checks", "--json", "name,state"],
            cwd=str(wt_path),
            capture_output=True,
            text=True,
        )
        ci = "none"
        if ci_result.returncode == 0:
            try:
                checks = json.loads(ci_result.stdout)
                # Filter out SKIPPED checks.
                active = [c for c in checks if c.get("state", "").upper() != "SKIPPED"]
                if not active:
                    ci = "none"
                elif any(
                    c.get("state", "").upper() in ("IN_PROGRESS", "QUEUED", "PENDING")
                    for c in active
                ):
                    ci = "pending"
                elif any(
                    c.get("state", "").upper() in ("FAILURE", "TIMED_OUT", "CANCELLED")
                    for c in active
                ):
                    ci = "fail"
                elif all(c.get("state", "").upper() == "SUCCESS" for c in active):
                    ci = "pass"
                else:
                    ci = "pending"
            except json.JSONDecodeError:
                ci = "none"

        info[name] = {"url": url, "ci": ci}
    return info

"""Query the opencode SQLite database for cost and token usage data."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from lib.config import REPO_BY_NAME, ProjectPaths


# ── DB location ───────────────────────────────────────────────────────

_DB_CANDIDATES = [
    Path.home() / ".local" / "share" / "opencode" / "opencode.db",
    Path.home() / "Library" / "Application Support" / "opencode" / "opencode.db",
]


def _find_db() -> Path | None:
    """Locate the opencode SQLite database."""
    env_path = os.environ.get("OPENCODE_DB")
    if env_path:
        p = Path(env_path)
        if p.exists():
            return p

    for candidate in _DB_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


# ── Cost queries ──────────────────────────────────────────────────────

_FEATURE_COSTS_SQL = """\
SELECT
    s.id           AS session_id,
    s.title        AS title,
    s.directory    AS directory,
    COUNT(*)       AS messages,
    COALESCE(SUM(json_extract(m.data, '$.cost')), 0)                   AS cost,
    COALESCE(SUM(json_extract(m.data, '$.tokens.input')), 0)           AS input_tokens,
    COALESCE(SUM(json_extract(m.data, '$.tokens.output')), 0)          AS output_tokens,
    COALESCE(SUM(json_extract(m.data, '$.tokens.reasoning')), 0)       AS reasoning_tokens,
    COALESCE(SUM(json_extract(m.data, '$.tokens.cache.read')), 0)      AS cache_read,
    COALESCE(SUM(json_extract(m.data, '$.tokens.cache.write')), 0)     AS cache_write
FROM message m
JOIN session s ON s.id = m.session_id
WHERE s.directory LIKE ?
  AND json_extract(m.data, '$.cost') > 0
GROUP BY s.id
ORDER BY s.time_created
"""


def _map_session_to_repo(directory: str, slug: str) -> str | None:
    """Extract the repo name from a session directory path.

    Session directories look like:
        .../specs/<slug>/repos/<repo-name>/
        .../specs/<slug>/                    (for PM, architect, etc.)
    """
    repos_marker = f"specs/{slug}/repos/"
    idx = directory.find(repos_marker)
    if idx != -1:
        rest = directory[idx + len(repos_marker) :]
        repo_name = rest.strip("/").split("/")[0]
        if repo_name in REPO_BY_NAME:
            return repo_name
    return None


def _map_session_to_phase(title: str) -> str:
    """Best-effort phase detection from session title."""
    lower = title.lower()
    if "review" in lower or "code review" in lower:
        return "review"
    if "pr" in lower or "pull request" in lower:
        return "pr"
    if "ci" in lower or "fix" in lower and "ci" in lower:
        return "ci-fix"
    if "explore" in lower:
        return "engineer"  # subagent of engineer
    # Default: most sessions are engineer sessions.
    return "engineer"


def get_feature_costs(slug: str, paths: ProjectPaths) -> dict | None:
    """Query all opencode sessions related to a feature and aggregate costs.

    Returns None if the opencode DB is not found.
    """
    db_path = _find_db()
    if db_path is None:
        return None

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return None

    try:
        # Match sessions whose directory contains the slug.
        pattern = f"%{slug}%"
        rows = conn.execute(_FEATURE_COSTS_SQL, (pattern,)).fetchall()
    except sqlite3.Error:
        conn.close()
        return None

    if not rows:
        conn.close()
        return _empty_costs()

    # Aggregate totals.
    totals = {
        "total_cost": 0.0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_reasoning_tokens": 0,
        "total_cache_read": 0,
        "total_cache_write": 0,
        "sessions": 0,
        "messages": 0,
    }
    by_repo: dict[str, dict] = {}
    by_phase: dict[str, dict] = {}

    for row in rows:
        cost = row["cost"] or 0
        input_tok = row["input_tokens"] or 0
        output_tok = row["output_tokens"] or 0
        reasoning_tok = row["reasoning_tokens"] or 0
        cache_r = row["cache_read"] or 0
        cache_w = row["cache_write"] or 0
        msgs = row["messages"] or 0

        totals["total_cost"] += cost
        totals["total_input_tokens"] += input_tok
        totals["total_output_tokens"] += output_tok
        totals["total_reasoning_tokens"] += reasoning_tok
        totals["total_cache_read"] += cache_r
        totals["total_cache_write"] += cache_w
        totals["sessions"] += 1
        totals["messages"] += msgs

        # Per-repo breakdown.
        repo = _map_session_to_repo(row["directory"], slug)
        if repo:
            bucket = by_repo.setdefault(repo, _empty_bucket())
            _add_to_bucket(
                bucket,
                cost,
                input_tok,
                output_tok,
                reasoning_tok,
                cache_r,
                cache_w,
                msgs,
            )

        # Per-phase breakdown.
        phase = _map_session_to_phase(row["title"] or "")
        phase_bucket = by_phase.setdefault(phase, _empty_bucket())
        _add_to_bucket(
            phase_bucket,
            cost,
            input_tok,
            output_tok,
            reasoning_tok,
            cache_r,
            cache_w,
            msgs,
        )

    conn.close()

    # Round costs for display.
    totals["total_cost"] = round(totals["total_cost"], 4)
    for bucket in (*by_repo.values(), *by_phase.values()):
        bucket["cost"] = round(bucket["cost"], 4)

    return {
        **totals,
        "by_repo": by_repo,
        "by_phase": by_phase,
    }


def save_costs(slug: str, paths: ProjectPaths) -> Path | None:
    """Query costs and write them to specs/<slug>/costs.json."""
    costs = get_feature_costs(slug, paths)
    if costs is None:
        return None

    paths.ensure_spec_dirs(slug)
    dest = paths.spec_file(slug, "costs.json")
    dest.write_text(json.dumps(costs, indent=2), encoding="utf-8")
    return dest


# ── Helpers ───────────────────────────────────────────────────────────


def _empty_bucket() -> dict:
    return {
        "cost": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "reasoning_tokens": 0,
        "cache_read": 0,
        "cache_write": 0,
        "messages": 0,
    }


def _empty_costs() -> dict:
    return {
        "total_cost": 0.0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_reasoning_tokens": 0,
        "total_cache_read": 0,
        "total_cache_write": 0,
        "sessions": 0,
        "messages": 0,
        "by_repo": {},
        "by_phase": {},
    }


def _add_to_bucket(
    bucket: dict,
    cost: float,
    input_tok: int,
    output_tok: int,
    reasoning_tok: int,
    cache_r: int,
    cache_w: int,
    msgs: int,
) -> None:
    bucket["cost"] += cost
    bucket["input_tokens"] += input_tok
    bucket["output_tokens"] += output_tok
    bucket["reasoning_tokens"] += reasoning_tok
    bucket["cache_read"] += cache_r
    bucket["cache_write"] += cache_w
    bucket["messages"] += msgs

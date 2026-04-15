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

_COSTS_BY_DIR_SQL = """\
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

# Separate query for project-root sessions (PM, designer, architect)
# matched by title keywords. Uses LIKE with placeholders built dynamically.
_COSTS_BY_TITLE_SQL = """\
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
WHERE s.directory = ?
  AND {title_conditions}
  AND s.time_created >= ?
  AND json_extract(m.data, '$.cost') > 0
GROUP BY s.id
ORDER BY s.time_created
"""

# Words to drop when extracting keywords from the slug.
_SLUG_STOP_WORDS = frozenset(
    {
        "add",
        "fix",
        "update",
        "implement",
        "remove",
        "refactor",
        "support",
        "for",
        "the",
        "all",
        "to",
        "in",
        "a",
        "an",
    }
)


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


def _map_session_to_phase(title: str, directory: str, project_root: str) -> str:
    """Best-effort phase detection from session title and directory."""
    lower = title.lower()
    is_root = directory.rstrip("/") == project_root.rstrip("/")

    # Project-root sessions are planning phases (PM, designer, architect).
    if is_root:
        if "prd" in lower or "product" in lower:
            return "pm"
        if "design" in lower:
            return "designer"
        if "architect" in lower or "technical" in lower or "tech spec" in lower:
            return "architect"
        if "review" in lower and "cross" in lower:
            return "cross-review"
        if "classify" in lower or "triage" in lower:
            return "intake"
        # Subagents (explore) at root are typically architect helpers.
        if "explore" in lower:
            return "architect"
        return "planning"

    # Repo worktree sessions are build phases.
    if "review" in lower:
        return "review"
    if "pr" in lower or "pull request" in lower:
        return "pr"
    if "ci" in lower:
        return "ci-fix"
    if "explore" in lower:
        return "engineer"
    return "engineer"


def _extract_slug_keywords(slug: str) -> list[str]:
    """Extract meaningful keywords from a slug for title matching."""
    parts = slug.split("-")
    return [w for w in parts if w.lower() not in _SLUG_STOP_WORDS and len(w) > 1]


def get_feature_costs(slug: str, paths: ProjectPaths) -> dict | None:
    """Query all opencode sessions related to a feature and aggregate costs.

    Matches sessions two ways:
    1. Sessions whose directory contains the slug (repo worktree sessions).
    2. Sessions at the project root whose title matches slug keywords
       (PM, designer, architect sessions).

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
        # Query 1: sessions in worktree directories.
        dir_pattern = f"%{slug}%"
        rows = list(conn.execute(_COSTS_BY_DIR_SQL, (dir_pattern,)).fetchall())

        # Query 2: project-root sessions matched by title keywords.
        keywords = _extract_slug_keywords(slug)
        if len(keywords) >= 2:
            # Require at least 2 keywords to match to avoid false positives.
            title_conditions = " AND ".join(f"LOWER(s.title) LIKE ?" for _ in keywords)
            sql = _COSTS_BY_TITLE_SQL.format(title_conditions=title_conditions)
            params: list = [str(paths.root)]
            params += [f"%{kw.lower()}%" for kw in keywords]

            # Only look at sessions created after a reasonable start time.
            # Use the feature's status.json created_at if available, else 0.
            from lib.status import load_status

            status_data = load_status(slug, paths)
            created_at = 0
            if status_data and "created_at" in status_data:
                from datetime import datetime

                try:
                    dt = datetime.fromisoformat(status_data["created_at"])
                    created_at = int(dt.timestamp() * 1000)  # ms epoch
                except (ValueError, TypeError):
                    pass
            params.append(created_at)

            seen_ids = {r["session_id"] for r in rows}
            for row in conn.execute(sql, params).fetchall():
                if row["session_id"] not in seen_ids:
                    rows.append(row)
                    seen_ids.add(row["session_id"])

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
        phase = _map_session_to_phase(
            row["title"] or "", row["directory"] or "", str(paths.root)
        )
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

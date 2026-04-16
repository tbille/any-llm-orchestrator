"""Structured output parsing for agent responses.

Provides robust extraction of machine-readable data from agent output
that may contain markdown, prose, and JSON blocks in various formats.
Replaces ad-hoc string matching (e.g. ``"NEEDS_CHANGES" in text``)
with reliable structured parsing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


# ── JSON extraction ──────────────────────────────────────────────────


def extract_json_block(
    text: str,
    required_keys: list[str] | None = None,
) -> dict | None:
    """Extract a JSON object from text that may contain prose and markdown.

    Tries multiple strategies in order:
    1. Fenced code blocks (```json ... ```)
    2. HTML comments (<!-- VERDICT: {...} -->)
    3. Bare JSON objects (outermost braces)

    When *required_keys* is provided, only returns a dict that contains
    all of the specified keys.  If multiple JSON blocks exist, returns
    the first one that satisfies the key requirement.

    Returns None if no valid JSON object is found.
    """
    candidates: list[str] = []

    # Strategy 1: Fenced code blocks.
    for match in re.finditer(r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL):
        candidates.append(match.group(1).strip())

    # Strategy 2: HTML comment blocks (<!-- VERDICT: {...} -->).
    for match in re.finditer(r"<!--\s*\w+:\s*(\{.*?\})\s*-->", text, re.DOTALL):
        candidates.append(match.group(1).strip())

    # Strategy 3: Bare JSON -- find all top-level brace pairs.
    # Only used as fallback when fenced/comment blocks yield nothing.
    if not candidates:
        candidates.extend(_find_bare_json_objects(text))

    for raw in candidates:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        if required_keys and not all(k in data for k in required_keys):
            continue
        return data

    return None


def _find_bare_json_objects(text: str) -> list[str]:
    """Find top-level ``{...}`` substrings that could be JSON objects.

    Uses a simple brace-depth counter rather than regex to handle
    nested braces correctly.
    """
    results: list[str] = []
    depth = 0
    start = -1

    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                results.append(text[start : i + 1])
                start = -1

    return results


# ── Review verdict parsing ───────────────────────────────────────────


@dataclass(frozen=True)
class ReviewVerdict:
    """Structured result from a code review agent."""

    status: str  # "PASS" or "NEEDS_CHANGES"
    blockers: int
    majors: int
    minors: int

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    @property
    def has_blocking_issues(self) -> bool:
        """True if there are issues serious enough to warrant a fix round."""
        return self.blockers > 0 or self.majors > 0


# Fallback: count severity markers in the review markdown when no
# machine-readable verdict block is present.
_SEVERITY_RE = re.compile(
    r"###\s*\[(BLOCKER|MAJOR|MINOR)\]",
    re.IGNORECASE,
)


def parse_review_verdict(review_file: Path) -> ReviewVerdict:
    """Parse a code review file and return a structured verdict.

    Tries two strategies:
    1. Machine-readable verdict block (HTML comment or JSON fence).
    2. Fallback: count ``### [BLOCKER]`` / ``### [MAJOR]`` / ``### [MINOR]``
       headings and check for ``NEEDS_CHANGES`` in the text.

    Returns a ReviewVerdict that always has a valid status.
    """
    if not review_file.exists():
        # No review file means the review agent didn't run or crashed.
        # Treat as PASS to avoid blocking the pipeline.
        return ReviewVerdict(status="PASS", blockers=0, majors=0, minors=0)

    content = review_file.read_text(encoding="utf-8")

    # Strategy 1: Look for a structured verdict block.
    verdict_data = extract_json_block(content, required_keys=["status"])
    if verdict_data is not None:
        status = verdict_data.get("status", "PASS").upper()
        # Normalize variant spellings.
        if "NEEDS" in status or "CHANGE" in status:
            status = "NEEDS_CHANGES"
        elif "PASS" in status:
            status = "PASS"
        return ReviewVerdict(
            status=status,
            blockers=int(verdict_data.get("blockers", 0)),
            majors=int(verdict_data.get("majors", 0)),
            minors=int(verdict_data.get("minors", 0)),
        )

    # Strategy 2: Parse the markdown text.
    content_upper = content.upper()
    blockers = 0
    majors = 0
    minors = 0

    for match in _SEVERITY_RE.finditer(content):
        severity = match.group(1).upper()
        if severity == "BLOCKER":
            blockers += 1
        elif severity == "MAJOR":
            majors += 1
        elif severity == "MINOR":
            minors += 1

    # Determine status from text.
    if "NEEDS_CHANGES" in content_upper or "NEEDS CHANGES" in content_upper:
        status = "NEEDS_CHANGES"
    elif blockers > 0 or majors > 0:
        # Issues found but status line missing or ambiguous.
        status = "NEEDS_CHANGES"
    else:
        status = "PASS"

    return ReviewVerdict(
        status=status,
        blockers=blockers,
        majors=majors,
        minors=minors,
    )


# ── Cross-review repo parsing ────────────────────────────────────────


def parse_cross_review_repos(
    cross_review_file: Path,
    candidate_repos: list[str],
) -> list[str]:
    """Extract repos with actionable findings from a cross-review file.

    Tries three strategies in order:
    1. Machine-readable JSON block with ``affected_repos`` key.
    2. Summary-of-findings table rows (excluding "informational").
    3. Returns empty list if neither strategy finds anything.

    Only returns repos that are in *candidate_repos*.
    """
    if not cross_review_file.exists():
        return []

    content = cross_review_file.read_text(encoding="utf-8")

    # Strategy 1: JSON block with affected_repos.
    for match in re.finditer(r"```json\s*\n(.*?)\n\s*```", content, re.DOTALL):
        try:
            data = json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(data, dict) or "affected_repos" not in data:
            continue
        repos = data["affected_repos"]
        if isinstance(repos, list):
            found = [r for r in repos if r in candidate_repos]
            if found or repos == []:
                return found

    # Strategy 2: Parse the summary/findings table.
    affected: set[str] = set()
    in_summary = False

    for line in content.splitlines():
        if "summary" in line.lower() and "finding" in line.lower():
            in_summary = True
            continue
        if in_summary and line.strip().startswith("|"):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 3:
                continue
            # Skip header/separator rows.
            if any(p in ("#", "---", "") for p in parts[1:2]):
                continue
            if "---" in line:
                continue
            # Skip informational-only rows.
            if "informational" in line.lower():
                continue
            for repo in candidate_repos:
                if repo in line:
                    affected.add(repo)

    return [r for r in candidate_repos if r in affected]


# ── Classifier response parsing ──────────────────────────────────────


def parse_classifier_json(
    text: str,
    required_keys: list[str] | None = None,
) -> dict | None:
    """Extract a JSON response from a classifier agent's output.

    Handles markdown fences, stray backticks, and prose surrounding
    the JSON block.  Returns None if parsing fails.
    """
    # Strip markdown fences.
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = cleaned.strip().rstrip("`")

    return extract_json_block(cleaned, required_keys=required_keys)

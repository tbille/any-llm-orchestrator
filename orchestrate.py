"""Main CLI entry point for the any-llm-world multi-repo orchestrator.

Usage:
    uv run orchestrate.py --issue https://github.com/mozilla-ai/any-llm/issues/123
    uv run orchestrate.py --prompt "Add streaming support to all SDKs"
    uv run orchestrate.py --resume <slug>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lib.config import get_project_paths
from lib.intake import (
    TriageResult,
    classify,
    confirm_triage,
    fetch_issue,
    format_issue_as_input,
    load_triage,
    save_input,
    save_triage,
)
from lib.prd import (
    classify_design_need,
    design_exists,
    prd_exists,
    run_debate,
    run_designer,
    run_pm,
)
from lib.architect import get_affected_repos, run_architect, tech_spec_exists
from lib.workspace import (
    create_worktrees,
    ensure_repos_cloned,
    setup_engineer_context,
    worktrees_exist,
)
from lib.engineer import run_engineers, run_review_loop


# ── CLI ───────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orchestrate",
        description="Multi-repo orchestrator for the any-llm ecosystem.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--issue",
        metavar="URL",
        help="GitHub issue URL to work on",
    )
    group.add_argument(
        "--prompt",
        metavar="TEXT",
        help="Free-form prompt describing the work",
    )
    group.add_argument(
        "--resume",
        metavar="SLUG",
        help="Resume a previous run from its slug",
    )
    return parser


# ── Phase runners ─────────────────────────────────────────────────────


def phase_intake(args: argparse.Namespace) -> TriageResult:
    """Phase 1: Fetch input, classify, confirm."""
    paths = get_project_paths()

    # -- Resume path --
    if args.resume:
        print(f"\n  Resuming from slug: {args.resume}")
        triage = load_triage(args.resume, paths)
        if triage is None:
            print(
                f"  [ERROR] No triage found for slug {args.resume!r}.", file=sys.stderr
            )
            sys.exit(1)
        return triage

    # -- Issue path --
    if args.issue:
        print("\n── Phase 1: Intake (GitHub issue) ──────────────────")
        print(f"  Fetching: {args.issue}")
        issue = fetch_issue(args.issue)
        input_text = format_issue_as_input(issue)
    else:
        # -- Prompt path --
        print("\n── Phase 1: Intake (prompt) ─────────────────────────")
        input_text = f"# Feature Request\n\n{args.prompt}"

    print("  Classifying...")
    triage = classify(input_text, paths)
    triage = confirm_triage(triage)

    # Persist for resume.
    save_input(triage.slug, input_text, paths)
    save_triage(triage.slug, triage, paths)

    print(f"\n  Saved to: specs/{triage.slug}/")
    return triage


def phase_feature(slug: str, repo_names: list[str]) -> list[str]:
    """Phases 2-4 for the feature path: PM -> debate -> designer? -> architect."""
    paths = get_project_paths()

    # Phase 2: Product Manager
    if not prd_exists(slug, paths):
        run_pm(slug, paths)
    else:
        print(f"  [skip] PRD already exists: specs/{slug}/prd.md")

    # Phase 3: Debate
    if prd_exists(slug, paths):
        run_debate(slug, paths)

    # Phase 3.5-3.6: Designer (conditional)
    if not design_exists(slug, paths):
        print("\n── Phase 3.5: Design classification ────────────────")
        if classify_design_need(slug, paths):
            run_designer(slug, paths)
        else:
            print("  Design phase skipped (technical-only change).")
    else:
        print(f"  [skip] Design doc already exists: specs/{slug}/design.md")

    # Phase 4: Architect
    if not tech_spec_exists(slug, paths):
        return run_architect(slug, repo_names, paths)
    else:
        print(f"  [skip] Tech spec already exists: specs/{slug}/tech-spec.md")
        return get_affected_repos(slug, repo_names, paths)


def phase_complex_bug(slug: str, repo_names: list[str]) -> list[str]:
    """Phase 4 only for complex bugs: lightweight architect."""
    paths = get_project_paths()

    if not tech_spec_exists(slug, paths):
        return run_architect(slug, repo_names, paths, light=True)
    else:
        print(f"  [skip] Tech spec already exists: specs/{slug}/tech-spec.md")
        return get_affected_repos(slug, repo_names, paths)


def phase_workspace(slug: str, repo_names: list[str]) -> dict[str, Path]:
    """Phase 5: Clone repos and create worktrees."""
    paths = get_project_paths()

    print("\n── Phase 5: Workspace setup ─────────────────────────")

    if worktrees_exist(slug, repo_names, paths):
        print("  [skip] All worktrees already exist.")
        return {name: paths.worktree_path(slug, name) for name in repo_names}

    print("  Ensuring all repos are cloned...")
    ensure_repos_cloned(paths)

    print("  Creating worktrees...")
    worktrees = create_worktrees(slug, repo_names, paths)

    # Set up context for each engineer.
    print("  Setting up engineer context (AGENTS.md)...")
    for name in worktrees:
        setup_engineer_context(slug, name, paths)

    print("  Workspace ready.\n")
    return worktrees


def phase_engineer_and_review(slug: str, repo_names: list[str]) -> None:
    """Phase 6-7: Engineers + review loop."""
    paths = get_project_paths()

    # Phase 6: Engineers
    run_engineers(slug, repo_names, paths)

    # Phase 7: Review loop (review -> fix -> review, max 2 rounds)
    run_review_loop(slug, repo_names, paths, max_rounds=2)


# ── Main pipeline ─────────────────────────────────────────────────────


_PATH_HEADER = {
    "simple-bug": "Simple Bug",
    "complex-bug": "Complex Bug",
    "feature": "Feature",
}


def run_pipeline(args: argparse.Namespace) -> None:
    """Execute the full pipeline based on triage type."""
    triage = phase_intake(args)
    slug = triage.slug
    repo_names = triage.repos

    print(f"\n{'=' * 56}")
    print(f"  Path: {_PATH_HEADER[triage.triage_type]}")
    print(f"  Slug: {slug}")
    print(f"  Repos: {', '.join(repo_names)}")
    print(f"{'=' * 56}")

    # Phases 2-4: depends on triage type.
    if triage.triage_type == "feature":
        repo_names = phase_feature(slug, repo_names)
    elif triage.triage_type == "complex-bug":
        repo_names = phase_complex_bug(slug, repo_names)
    # simple-bug skips straight to workspace.

    # Phase 5: Workspace.
    phase_workspace(slug, repo_names)

    # Phase 6-7: Engineers + review.
    phase_engineer_and_review(slug, repo_names)

    # Done.
    print(f"\n{'=' * 56}")
    print(f"  Pipeline complete for: {slug}")
    print(f"  Specs:      specs/{slug}/")
    print(f"  Worktrees:  specs/{slug}/repos/")
    print(f"  Logs:       specs/{slug}/logs/")
    print(f"{'=' * 56}\n")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run_pipeline(args)


if __name__ == "__main__":
    main()

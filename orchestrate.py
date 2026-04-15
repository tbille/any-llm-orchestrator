"""Main CLI entry point for the any-llm-world multi-repo orchestrator.

Usage:
    uv run orchestrate.py --issue https://github.com/mozilla-ai/any-llm/issues/123
    uv run orchestrate.py --prompt "Add streaming support to all SDKs"
    uv run orchestrate.py --resume <slug>
    uv run orchestrate.py --resume <slug> --skip-to engineer
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
from lib.pr import create_pull_requests, watch_ci
from lib.status import PHASES_BY_TYPE, init_status, update_phase


# ── Phase ordering for --skip-to ──────────────────────────────────────

SKIP_TO_PHASES = (
    "intake",
    "pm",
    "debate",
    "designer",
    "architect",
    "workspace",
    "engineer",
    "review",
    "pr",
    "ci",
)


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
    parser.add_argument(
        "--skip-to",
        metavar="PHASE",
        choices=SKIP_TO_PHASES,
        help=(
            "Skip to a specific phase (requires --resume). "
            f"Choices: {', '.join(SKIP_TO_PHASES)}"
        ),
    )
    return parser


def _should_skip(phase: str, skip_to: str | None) -> bool:
    """Return True if *phase* should be skipped based on --skip-to."""
    if skip_to is None:
        return False
    try:
        return SKIP_TO_PHASES.index(phase) < SKIP_TO_PHASES.index(skip_to)
    except ValueError:
        return False


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
                f"  [ERROR] No triage found for slug {args.resume!r}.",
                file=sys.stderr,
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

    # Initialise status tracking.
    init_status(triage.slug, triage.triage_type, triage.repos, paths)
    update_phase(triage.slug, "intake", "done", paths)

    print(f"\n  Saved to: specs/{triage.slug}/")
    return triage


def phase_feature(slug: str, repo_names: list[str], skip_to: str | None) -> list[str]:
    """Phases 2-4 for the feature path: PM -> debate -> designer? -> architect."""
    paths = get_project_paths()

    # Phase 2: Product Manager
    if _should_skip("pm", skip_to):
        print("  [skip-to] skipping PM phase")
        update_phase(slug, "pm", "skipped", paths)
    elif not prd_exists(slug, paths):
        update_phase(slug, "pm", "running", paths)
        run_pm(slug, paths)
        update_phase(slug, "pm", "done", paths)
    else:
        print(f"  [skip] PRD already exists: specs/{slug}/prd.md")
        update_phase(slug, "pm", "done", paths)

    # Phase 3: Debate
    if _should_skip("debate", skip_to):
        print("  [skip-to] skipping debate phase")
        update_phase(slug, "debate", "skipped", paths)
    elif prd_exists(slug, paths):
        update_phase(slug, "debate", "running", paths)
        run_debate(slug, paths)
        update_phase(slug, "debate", "done", paths)
    else:
        update_phase(slug, "debate", "skipped", paths)

    # Phase 3.5-3.6: Designer (conditional)
    if _should_skip("designer", skip_to):
        print("  [skip-to] skipping designer phase")
        update_phase(slug, "designer", "skipped", paths)
    elif not design_exists(slug, paths):
        print("\n── Phase 3.5: Design classification ────────────────")
        if classify_design_need(slug, paths):
            update_phase(slug, "designer", "running", paths)
            run_designer(slug, paths)
            update_phase(slug, "designer", "done", paths)
        else:
            print("  Design phase skipped (technical-only change).")
            update_phase(slug, "designer", "skipped", paths)
    else:
        print(f"  [skip] Design doc already exists: specs/{slug}/design.md")
        update_phase(slug, "designer", "done", paths)

    # Phase 4: Architect
    if _should_skip("architect", skip_to):
        print("  [skip-to] skipping architect phase")
        update_phase(slug, "architect", "skipped", paths)
        return get_affected_repos(slug, repo_names, paths)

    if not tech_spec_exists(slug, paths):
        update_phase(slug, "architect", "running", paths)
        result = run_architect(slug, repo_names, paths)
        update_phase(slug, "architect", "done", paths)
        return result
    else:
        print(f"  [skip] Tech spec already exists: specs/{slug}/tech-spec.md")
        update_phase(slug, "architect", "done", paths)
        return get_affected_repos(slug, repo_names, paths)


def phase_complex_bug(
    slug: str, repo_names: list[str], skip_to: str | None
) -> list[str]:
    """Phase 4 only for complex bugs: lightweight architect."""
    paths = get_project_paths()

    if _should_skip("architect", skip_to):
        print("  [skip-to] skipping architect phase")
        update_phase(slug, "architect", "skipped", paths)
        return get_affected_repos(slug, repo_names, paths)

    if not tech_spec_exists(slug, paths):
        update_phase(slug, "architect", "running", paths)
        result = run_architect(slug, repo_names, paths, light=True)
        update_phase(slug, "architect", "done", paths)
        return result
    else:
        print(f"  [skip] Tech spec already exists: specs/{slug}/tech-spec.md")
        update_phase(slug, "architect", "done", paths)
        return get_affected_repos(slug, repo_names, paths)


def phase_workspace(slug: str, repo_names: list[str]) -> dict[str, Path]:
    """Phase 5: Clone repos and create worktrees."""
    paths = get_project_paths()

    print("\n── Phase 5: Workspace setup ─────────────────────────")
    update_phase(slug, "workspace", "running", paths)

    if worktrees_exist(slug, repo_names, paths):
        print("  [skip] All worktrees already exist.")
        update_phase(slug, "workspace", "done", paths)
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
    update_phase(slug, "workspace", "done", paths)
    return worktrees


def phase_engineer_and_review(
    slug: str, repo_names: list[str], skip_to: str | None
) -> None:
    """Phase 6-7: Engineers + review loop."""
    paths = get_project_paths()

    # Phase 6: Engineers
    if not _should_skip("engineer", skip_to):
        update_phase(
            slug,
            "engineer",
            "running",
            paths,
            repo_statuses={r: "running" for r in repo_names},
        )
        run_engineers(slug, repo_names, paths)
        update_phase(
            slug,
            "engineer",
            "done",
            paths,
            repo_statuses={r: "done" for r in repo_names},
        )
    else:
        print("  [skip-to] skipping engineer phase")
        update_phase(slug, "engineer", "skipped", paths)

    # Phase 7: Review loop (review -> fix -> review, max 2 rounds)
    if not _should_skip("review", skip_to):
        update_phase(
            slug,
            "review",
            "running",
            paths,
            repo_statuses={r: "running" for r in repo_names},
        )
        run_review_loop(slug, repo_names, paths, max_rounds=2)
        update_phase(
            slug,
            "review",
            "done",
            paths,
            repo_statuses={r: "done" for r in repo_names},
        )
    else:
        print("  [skip-to] skipping review phase")
        update_phase(slug, "review", "skipped", paths)


def phase_pull_requests(slug: str, repo_names: list[str]) -> None:
    """Phase 8: Create pull requests for each repo."""
    paths = get_project_paths()
    update_phase(
        slug,
        "pr",
        "running",
        paths,
        repo_statuses={r: "running" for r in repo_names},
    )
    create_pull_requests(slug, repo_names, paths)
    update_phase(
        slug,
        "pr",
        "done",
        paths,
        repo_statuses={r: "done" for r in repo_names},
    )


def phase_ci_watch(slug: str, repo_names: list[str]) -> None:
    """Phase 9: Monitor CI, send engineers to fix failures."""
    paths = get_project_paths()
    update_phase(
        slug,
        "ci",
        "running",
        paths,
        repo_statuses={r: "pending" for r in repo_names},
    )
    watch_ci(slug, repo_names, paths, max_fix_rounds=2)
    update_phase(
        slug,
        "ci",
        "done",
        paths,
        repo_statuses={r: "done" for r in repo_names},
    )


# ── Main pipeline ─────────────────────────────────────────────────────


_PATH_HEADER = {
    "simple-bug": "Simple Bug",
    "complex-bug": "Complex Bug",
    "feature": "Feature",
}


def run_pipeline(args: argparse.Namespace) -> None:
    """Execute the full pipeline based on triage type."""
    skip_to: str | None = getattr(args, "skip_to", None)

    if skip_to and not args.resume:
        print("[ERROR] --skip-to requires --resume.", file=sys.stderr)
        sys.exit(1)

    triage = phase_intake(args)
    slug = triage.slug
    repo_names = triage.repos

    print(f"\n{'=' * 56}")
    print(f"  Path: {_PATH_HEADER[triage.triage_type]}")
    print(f"  Slug: {slug}")
    print(f"  Repos: {', '.join(repo_names)}")
    if skip_to:
        print(f"  Skip-to: {skip_to}")
    print(f"{'=' * 56}")

    # Phases 2-4: depends on triage type.
    if triage.triage_type == "feature":
        repo_names = phase_feature(slug, repo_names, skip_to)
    elif triage.triage_type == "complex-bug":
        repo_names = phase_complex_bug(slug, repo_names, skip_to)
    # simple-bug skips straight to workspace.

    # Phase 5: Workspace.
    if not _should_skip("workspace", skip_to):
        phase_workspace(slug, repo_names)
    else:
        print("  [skip-to] skipping workspace phase")

    # Phase 6-7: Engineers + review.
    phase_engineer_and_review(slug, repo_names, skip_to)

    # Phase 8: Pull requests.
    if not _should_skip("pr", skip_to):
        phase_pull_requests(slug, repo_names)
    else:
        print("  [skip-to] skipping PR phase")

    # Phase 9: CI watch + fix loop.
    if not _should_skip("ci", skip_to):
        phase_ci_watch(slug, repo_names)
    else:
        print("  [skip-to] skipping CI phase")

    # Done.
    paths = get_project_paths()
    update_phase(slug, "ci", "done", paths)

    print(f"\n{'=' * 56}")
    print(f"  Pipeline complete for: {slug}")
    print(f"  Specs:      specs/{slug}/")
    print(f"  Worktrees:  specs/{slug}/repos/")
    print(f"  Logs:       specs/{slug}/logs/")
    print(f"  Dashboard:  uv run dashboard.py")
    print(f"{'=' * 56}\n")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run_pipeline(args)


if __name__ == "__main__":
    main()

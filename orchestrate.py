"""Main CLI entry point for the any-llm-world multi-repo orchestrator.

Usage:
    uv run orchestrate.py --issue https://github.com/mozilla-ai/any-llm/issues/123
    uv run orchestrate.py --prompt "Add streaming support to all SDKs"
    uv run orchestrate.py --resume <slug>
    uv run orchestrate.py --resume <slug> --skip-to build
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
from lib.costs import save_costs
from lib.engineer import run_build_pipelines, run_cross_repo_review
from lib.status import PHASES_BY_TYPE, init_status, update_phase


# ── Phase ordering for --skip-to ──────────────────────────────────────

SKIP_TO_PHASES = (
    "intake",
    "workspace",
    "pm",
    "debate",
    "designer",
    "architect",
    "build",
    "cross-review",
)


# ── CLI ───────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="orchestrate",
        description="Multi-repo orchestrator for the any-llm ecosystem.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--issue", metavar="URL", help="GitHub issue URL to work on")
    group.add_argument(
        "--prompt", metavar="TEXT", help="Free-form prompt describing the work"
    )
    group.add_argument(
        "--resume", metavar="SLUG", help="Resume a previous run from its slug"
    )
    parser.add_argument(
        "--skip-to",
        metavar="PHASE",
        choices=SKIP_TO_PHASES,
        help=f"Skip to a specific phase (requires --resume). Choices: {', '.join(SKIP_TO_PHASES)}",
    )
    return parser


def _should_skip(phase: str, skip_to: str | None) -> bool:
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

    if args.resume:
        print(f"\n  Resuming from slug: {args.resume}")
        triage = load_triage(args.resume, paths)
        if triage is None:
            print(
                f"  [ERROR] No triage found for slug {args.resume!r}.", file=sys.stderr
            )
            sys.exit(1)
        return triage

    if args.issue:
        print("\n── Phase 1: Intake (GitHub issue) ──────────────────")
        print(f"  Fetching: {args.issue}")
        issue = fetch_issue(args.issue)
        input_text = format_issue_as_input(issue)
    else:
        print("\n── Phase 1: Intake (prompt) ─────────────────────────")
        input_text = f"# Feature Request\n\n{args.prompt}"

    print("  Classifying...")
    triage = classify(input_text, paths)
    triage = confirm_triage(triage)

    save_input(triage.slug, input_text, paths)
    save_triage(triage.slug, triage, paths)
    init_status(triage.slug, triage.triage_type, triage.repos, paths)
    update_phase(triage.slug, "intake", "done", paths)

    print(f"\n  Saved to: specs/{triage.slug}/")
    return triage


def phase_workspace(slug: str, repo_names: list[str]) -> dict[str, Path]:
    """Clone repos and create worktrees."""
    paths = get_project_paths()

    print("\n── Workspace setup ─────────────────────────────────")
    update_phase(slug, "workspace", "running", paths)

    if worktrees_exist(slug, repo_names, paths):
        print("  [skip] All worktrees already exist.")
        update_phase(slug, "workspace", "done", paths)
        return {name: paths.worktree_path(slug, name) for name in repo_names}

    print("  Ensuring all repos are cloned...")
    ensure_repos_cloned(paths)

    print("  Creating worktrees...")
    worktrees = create_worktrees(slug, repo_names, paths)

    print("  Workspace ready.\n")
    update_phase(slug, "workspace", "done", paths)
    return worktrees


def phase_feature(slug: str, repo_names: list[str], skip_to: str | None) -> list[str]:
    """PM -> debate -> designer? -> architect."""
    paths = get_project_paths()

    # PM
    if _should_skip("pm", skip_to):
        update_phase(slug, "pm", "skipped", paths)
    elif not prd_exists(slug, paths):
        update_phase(slug, "pm", "running", paths)
        run_pm(slug, paths)
        update_phase(slug, "pm", "done", paths)
    else:
        print(f"  [skip] PRD already exists: specs/{slug}/prd.md")
        update_phase(slug, "pm", "done", paths)

    # Debate
    if _should_skip("debate", skip_to):
        update_phase(slug, "debate", "skipped", paths)
    elif prd_exists(slug, paths):
        update_phase(slug, "debate", "running", paths)
        run_debate(slug, paths)
        update_phase(slug, "debate", "done", paths)
    else:
        update_phase(slug, "debate", "skipped", paths)

    # Designer (conditional)
    if _should_skip("designer", skip_to):
        update_phase(slug, "designer", "skipped", paths)
    elif not design_exists(slug, paths):
        print("\n── Design classification ────────────────────────────")
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

    # Architect
    if _should_skip("architect", skip_to):
        update_phase(slug, "architect", "skipped", paths)
        return get_affected_repos(slug, repo_names, paths)
    if not tech_spec_exists(slug, paths):
        update_phase(slug, "architect", "running", paths)
        result = run_architect(slug, repo_names, paths)
        update_phase(slug, "architect", "done", paths)
        return result
    print(f"  [skip] Tech spec already exists: specs/{slug}/tech-spec.md")
    update_phase(slug, "architect", "done", paths)
    return get_affected_repos(slug, repo_names, paths)


def phase_complex_bug(
    slug: str, repo_names: list[str], skip_to: str | None
) -> list[str]:
    """Lightweight architect only."""
    paths = get_project_paths()

    if _should_skip("architect", skip_to):
        update_phase(slug, "architect", "skipped", paths)
        return get_affected_repos(slug, repo_names, paths)
    if not tech_spec_exists(slug, paths):
        update_phase(slug, "architect", "running", paths)
        result = run_architect(slug, repo_names, paths, light=True)
        update_phase(slug, "architect", "done", paths)
        return result
    print(f"  [skip] Tech spec already exists: specs/{slug}/tech-spec.md")
    update_phase(slug, "architect", "done", paths)
    return get_affected_repos(slug, repo_names, paths)


def phase_build(slug: str, repo_names: list[str]) -> None:
    """Per-repo parallel pipelines: engineer -> review -> PR -> CI."""
    paths = get_project_paths()
    update_phase(slug, "build", "running", paths)
    run_build_pipelines(slug, repo_names, paths)
    update_phase(slug, "build", "done", paths)


def phase_cross_review(slug: str, repo_names: list[str]) -> None:
    """Cross-repo consistency review after all repos finish."""
    paths = get_project_paths()
    if len(repo_names) > 1:
        update_phase(slug, "cross-review", "running", paths)
        run_cross_repo_review(slug, repo_names, paths)
        update_phase(slug, "cross-review", "done", paths)
    else:
        update_phase(slug, "cross-review", "skipped", paths)


# ── Main pipeline ─────────────────────────────────────────────────────

_PATH_HEADER = {
    "simple-bug": "Simple Bug",
    "complex-bug": "Complex Bug",
    "feature": "Feature",
}


def run_pipeline(args: argparse.Namespace) -> None:
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

    # Workspace: set up early so all agents have repo access.
    if not _should_skip("workspace", skip_to):
        phase_workspace(slug, repo_names)

    # Spec phases: depends on triage type.
    if triage.triage_type == "feature":
        repo_names = phase_feature(slug, repo_names, skip_to)
    elif triage.triage_type == "complex-bug":
        repo_names = phase_complex_bug(slug, repo_names, skip_to)

    # Set up engineer context (AGENTS.md in each worktree).
    if not _should_skip("build", skip_to):
        paths = get_project_paths()
        print("  Setting up engineer context (AGENTS.md)...")
        for name in repo_names:
            if paths.worktree_path(slug, name).exists():
                setup_engineer_context(slug, name, paths)

    # Build: per-repo parallel pipelines.
    if not _should_skip("build", skip_to):
        phase_build(slug, repo_names)

    # Cross-repo review: only sync point.
    if not _should_skip("cross-review", skip_to):
        phase_cross_review(slug, repo_names)

    # Done.
    paths = get_project_paths()
    cost_file = save_costs(slug, paths)
    if cost_file:
        from lib.costs import get_feature_costs

        costs = get_feature_costs(slug, paths)
        cost_str = f"${costs['total_cost']:.2f}" if costs else "N/A"
    else:
        cost_str = "N/A (opencode DB not found)"

    print(f"\n{'=' * 56}")
    print(f"  Pipeline complete for: {slug}")
    print(f"  Cost:       {cost_str}")
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

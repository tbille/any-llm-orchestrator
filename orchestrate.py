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
    debate_done,
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
    update_worktrees,
    worktrees_exist,
)
from lib.costs import check_cost_ceiling, save_costs
from lib.engineer import (
    run_build_pipelines,
    run_cross_repo_review,
    run_cross_review_fixes,
)
from lib.status import init_status, update_phase


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
    "cross-review-fix",
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
    parser.add_argument(
        "--ci-check",
        nargs="?",
        const="all",
        metavar="REPO",
        help="Check CI status for all repos (or a specific repo). Requires --resume.",
    )
    parser.add_argument(
        "--fix-pr",
        nargs="?",
        const="all",
        metavar="REPO",
        help="Fetch PR review comments and send engineer to fix for all repos (or a specific repo). Requires --resume.",
    )
    parser.add_argument(
        "--fix-cross-review",
        nargs="?",
        const="all",
        metavar="REPO",
        help=(
            "Fix cross-review findings for all affected repos (or a specific "
            "repo). Requires --resume."
        ),
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help=(
            "Run PM and debate phases headlessly (no TUI interaction). "
            "The PRD is generated and critiqued in a single pass. "
            "Architect still runs interactively unless combined with --skip-to."
        ),
    )
    return parser


def _should_skip(phase: str, skip_to: str | None) -> bool:
    if skip_to is None:
        return False
    try:
        return SKIP_TO_PHASES.index(phase) < SKIP_TO_PHASES.index(skip_to)
    except ValueError:
        return False


def _confirm_continue(phase_name: str, slug: str) -> None:
    """Prompt the user to confirm continuation after an interactive phase.

    Catches accidental early exits from TUI sessions.  Typing 'n' pauses
    the pipeline and prints a resume command.
    """
    answer = input(f"\n  {phase_name} phase complete. Continue? [Y/n] ").strip().lower()
    if answer in ("n", "no"):
        print(f"  Pipeline paused after {phase_name}.")
        next_phase_idx = SKIP_TO_PHASES.index(phase_name.lower().replace(" ", "-")) + 1
        if next_phase_idx < len(SKIP_TO_PHASES):
            next_phase = SKIP_TO_PHASES[next_phase_idx]
            print(
                f"  Resume with: uv run orchestrate.py "
                f"--resume {slug} --skip-to {next_phase}"
            )
        sys.exit(0)


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
    init_status(
        triage.slug, triage.triage_type, triage.repos, paths, spec_phases=triage.phases
    )
    update_phase(triage.slug, "intake", "done", paths)

    print(f"\n  Saved to: specs/{triage.slug}/")
    return triage


def phase_workspace(slug: str, repo_names: list[str]) -> dict[str, Path]:
    """Clone repos and create worktrees."""
    paths = get_project_paths()

    print("\n── Workspace setup ─────────────────────────────────")
    update_phase(slug, "workspace", "running", paths)

    if worktrees_exist(slug, repo_names, paths):
        print("  [update] Worktrees exist, updating to latest upstream...")
        ensure_repos_cloned(paths)
        update_worktrees(slug, repo_names, paths)
        update_phase(slug, "workspace", "done", paths)
        return {name: paths.worktree_path(slug, name) for name in repo_names}

    print("  Ensuring all repos are cloned...")
    ensure_repos_cloned(paths)

    print("  Creating worktrees...")
    worktrees = create_worktrees(slug, repo_names, paths)

    print("  Workspace ready.\n")
    update_phase(slug, "workspace", "done", paths)
    return worktrees


def phase_specs(
    slug: str,
    repo_names: list[str],
    phases: list[str],
    skip_to: str | None,
    *,
    headless: bool = False,
    triage_type: str = "feature",
) -> list[str]:
    """Run the spec-phase agents selected by the triage classifier.

    ``phases`` is a subset of ``["pm", "debate", "designer", "architect"]``.
    Each phase is only executed if it appears in the list.  Phases not in
    the list are marked "skipped" in the status tracker.
    """
    paths = get_project_paths()

    has_pm = "pm" in phases
    has_debate = "debate" in phases
    has_designer = "designer" in phases
    has_architect = "architect" in phases

    # ── PM + Debate ───────────────────────────────────────────────
    if has_pm and headless:
        from lib.prd import run_pm_headless

        if _should_skip("pm", skip_to):
            pass
        elif not prd_exists(slug, paths):
            update_phase(slug, "pm", "running", paths)
            run_pm_headless(slug, paths)
            update_phase(slug, "pm", "done", paths)
            # Headless mode auto-critiques, so debate is implicit.
            update_phase(slug, "debate", "done", paths)
        else:
            print(f"  [skip] PRD already exists: specs/{slug}/prd.md")
            update_phase(slug, "pm", "done", paths)
            update_phase(slug, "debate", "done", paths)
    elif has_pm:
        # PM (interactive)
        if _should_skip("pm", skip_to):
            pass
        elif not prd_exists(slug, paths):
            update_phase(slug, "pm", "running", paths)
            run_pm(slug, paths)
            update_phase(slug, "pm", "done", paths)
            _confirm_continue("PM", slug)
        else:
            print(f"  [skip] PRD already exists: specs/{slug}/prd.md")
            update_phase(slug, "pm", "done", paths)

        # Debate (interactive) -- always paired with PM.
        if has_debate:
            if _should_skip("debate", skip_to):
                pass
            elif debate_done(slug, paths):
                print(f"  [skip] Debate already completed for: specs/{slug}/")
                update_phase(slug, "debate", "done", paths)
            elif prd_exists(slug, paths):
                update_phase(slug, "debate", "running", paths)
                run_debate(slug, paths)
                update_phase(slug, "debate", "done", paths)
                _confirm_continue("Debate", slug)
            else:
                update_phase(slug, "debate", "skipped", paths)

    # ── Designer ──────────────────────────────────────────────────
    if has_designer:
        if _should_skip("designer", skip_to):
            pass
        elif not design_exists(slug, paths):
            update_phase(slug, "designer", "running", paths)
            run_designer(slug, paths)
            update_phase(slug, "designer", "done", paths)
            _confirm_continue("Designer", slug)
        else:
            print(f"  [skip] Design doc already exists: specs/{slug}/design.md")
            update_phase(slug, "designer", "done", paths)

    # ── Architect ─────────────────────────────────────────────────
    if has_architect:
        light = triage_type == "complex-bug"
        if _should_skip("architect", skip_to):
            return get_affected_repos(slug, repo_names, paths)
        if not tech_spec_exists(slug, paths):
            update_phase(slug, "architect", "running", paths)
            result = run_architect(slug, repo_names, paths, light=light)
            update_phase(slug, "architect", "done", paths)
            _confirm_continue("Architect", slug)
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


def phase_cross_review_fix(slug: str, repo_names: list[str]) -> None:
    """Fix cross-review findings in affected repos (parallel)."""
    paths = get_project_paths()
    cross_review_file = paths.spec_file(slug, "cross-review.md")

    if not cross_review_file.exists():
        print("  [skip] No cross-review file -- nothing to fix.")
        update_phase(slug, "cross-review-fix", "skipped", paths)
        return

    # Quick check: if the review is a clean PASS with no findings, skip.
    content = cross_review_file.read_text(encoding="utf-8")
    if "Summary of Findings" not in content:
        print("  [skip] Cross-review has no findings table.")
        update_phase(slug, "cross-review-fix", "skipped", paths)
        return

    update_phase(slug, "cross-review-fix", "running", paths)
    affected = run_cross_review_fixes(slug, repo_names, paths)

    if affected:
        update_phase(slug, "cross-review-fix", "done", paths)
    else:
        print("  [skip] No repos had actionable findings to fix.")
        update_phase(slug, "cross-review-fix", "skipped", paths)


# ── Main pipeline ─────────────────────────────────────────────────────

_PATH_HEADER = {
    "simple-bug": "Simple Bug",
    "complex-bug": "Complex Bug",
    "feature": "Feature",
}


def _run_ci_check(args: argparse.Namespace) -> None:
    """Standalone CI check for one or all repos."""
    from lib.repo_runner import step_ci_watch

    paths = get_project_paths()
    triage = load_triage(args.resume, paths)
    if triage is None:
        print(f"[ERROR] No triage found for slug {args.resume!r}.", file=sys.stderr)
        sys.exit(1)

    slug = triage.slug
    target = args.ci_check
    repos = [target] if target != "all" else triage.repos

    print(f"\n── CI Check ────────────────────────────────────────")
    print(f"  Slug:  {slug}")
    print(f"  Repos: {', '.join(repos)}")
    print("────────────────────────────────────────────────────\n")

    for name in repos:
        wt_path = paths.worktree_path(slug, name)
        if not wt_path.exists():
            print(f"  [{name}] No worktree found, skipping.")
            continue
        step_ci_watch(slug, name, paths)

    save_costs(slug, paths)


def _run_fix_pr(args: argparse.Namespace) -> None:
    """Fetch PR comments and send engineer to fix (parallel via tmux)."""
    from lib.engineer import run_fix_pr_pipelines

    paths = get_project_paths()
    triage = load_triage(args.resume, paths)
    if triage is None:
        print(f"[ERROR] No triage found for slug {args.resume!r}.", file=sys.stderr)
        sys.exit(1)

    slug = triage.slug
    target = args.fix_pr
    repos = [target] if target != "all" else triage.repos

    if target != "all" and target not in triage.repos:
        print(
            f"[ERROR] Repo {target!r} not in feature repos: {triage.repos}",
            file=sys.stderr,
        )
        sys.exit(1)

    run_fix_pr_pipelines(slug, repos, paths, attach=True)

    print(f"\n  Done. To re-check CI:")
    print(f"  uv run orchestrate.py --resume {slug} --ci-check\n")
    save_costs(slug, paths)


def _run_fix_cross_review(args: argparse.Namespace) -> None:
    """Fix cross-review findings for all or a specific repo."""
    paths = get_project_paths()
    triage = load_triage(args.resume, paths)
    if triage is None:
        print(f"[ERROR] No triage found for slug {args.resume!r}.", file=sys.stderr)
        sys.exit(1)

    slug = triage.slug
    target = args.fix_cross_review
    repos = [target] if target != "all" else triage.repos

    print("\n── Fix Cross-Review Findings ────────────────────────")
    print(f"  Slug:  {slug}")
    print(f"  Repos: {', '.join(repos)}")
    print("────────────────────────────────────────────────────\n")

    phase_cross_review_fix(slug, repos)

    print("\n  Done. To re-check CI:")
    print(f"  uv run orchestrate.py --resume {slug} --ci-check\n")
    save_costs(slug, paths)


def run_pipeline(args: argparse.Namespace) -> None:
    # Handle standalone actions first.
    if args.ci_check is not None:
        if not args.resume:
            print("[ERROR] --ci-check requires --resume.", file=sys.stderr)
            sys.exit(1)
        _run_ci_check(args)
        return

    if args.fix_pr is not None:
        if not args.resume:
            print("[ERROR] --fix-pr requires --resume.", file=sys.stderr)
            sys.exit(1)
        _run_fix_pr(args)
        return

    if args.fix_cross_review is not None:
        if not args.resume:
            print("[ERROR] --fix-cross-review requires --resume.", file=sys.stderr)
            sys.exit(1)
        _run_fix_cross_review(args)
        return

    # Full pipeline.
    skip_to: str | None = getattr(args, "skip_to", None)

    if skip_to and not args.resume:
        print("[ERROR] --skip-to requires --resume.", file=sys.stderr)
        sys.exit(1)

    triage = phase_intake(args)
    slug = triage.slug
    repo_names = triage.repos
    phases_str = ", ".join(triage.phases) if triage.phases else "(none)"

    print(f"\n{'=' * 56}")
    print(f"  Path: {_PATH_HEADER[triage.triage_type]}")
    print(f"  Slug: {slug}")
    print(f"  Repos: {', '.join(repo_names)}")
    print(f"  Phases: {phases_str}")
    if skip_to:
        print(f"  Skip-to: {skip_to}")
    print(f"{'=' * 56}")

    # Workspace: set up early so all agents have repo access.
    if not _should_skip("workspace", skip_to):
        phase_workspace(slug, repo_names)

    # Spec phases: driven by the phases list from intake.
    headless = getattr(args, "headless", False)
    repo_names = phase_specs(
        slug,
        repo_names,
        triage.phases,
        skip_to,
        headless=headless,
        triage_type=triage.triage_type,
    )

    # Cost guardrail: check before the expensive build phase.
    paths = get_project_paths()
    if not check_cost_ceiling(slug, paths):
        print("  Pipeline paused by cost guardrail.")
        print(f"  Resume with: uv run orchestrate.py --resume {slug} --skip-to build")
        save_costs(slug, paths)
        return

    # Set up engineer context (AGENTS.md in each worktree).
    if not _should_skip("build", skip_to):
        print("  Setting up engineer context (AGENTS.md)...")
        for name in repo_names:
            if paths.worktree_path(slug, name).exists():
                setup_engineer_context(slug, name, paths)

    # Build: per-repo parallel pipelines.
    if not _should_skip("build", skip_to):
        phase_build(slug, repo_names)

    # Cost guardrail: check after build before cross-review.
    if not check_cost_ceiling(slug, paths):
        print("  Pipeline paused by cost guardrail.")
        print(
            f"  Resume with: uv run orchestrate.py --resume {slug} --skip-to cross-review"
        )
        save_costs(slug, paths)
        return

    # Cross-repo review: only sync point.
    if not _should_skip("cross-review", skip_to):
        phase_cross_review(slug, repo_names)

    # Fix cross-review findings (if any).
    if not _should_skip("cross-review-fix", skip_to):
        phase_cross_review_fix(slug, repo_names)

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

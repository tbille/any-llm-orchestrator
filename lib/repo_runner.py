"""Per-repo build pipeline: engineer -> review -> PR -> CI.

Runs inside a single tmux pane. Each repo flows independently.

Usage (called by the orchestrator, not directly):
    uv run lib/repo_runner.py <slug> <repo-name>
"""

from __future__ import annotations

import shlex
import subprocess
import sys
import time
from pathlib import Path

# Ensure project root is on sys.path when run as a script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from lib.config import CAVEMAN_PROMPT, REPO_BY_NAME, ProjectPaths, get_project_paths
from lib.status import update_repo_step


# ── Opencode runner ───────────────────────────────────────────────────


def _run_opencode(
    wt_path: Path,
    prompt_file: Path,
    file_args: list[str],
    log_file: Path,
) -> int:
    """Run opencode and tee output to a log file. Returns exit code."""
    parts = [
        "opencode",
        "run",
        "--dir",
        shlex.quote(str(wt_path)),
        "--dangerously-skip-permissions",
    ]
    parts += file_args
    parts += ["-f", shlex.quote(str(prompt_file))]
    parts += ["--", shlex.quote("Follow the instructions in the attached prompt file.")]

    cmd = " ".join(parts) + f" 2>&1 | tee -a {shlex.quote(str(log_file))}"
    result = subprocess.run(["sh", "-c", cmd])
    return result.returncode


def _write_prompt(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CAVEMAN_PROMPT + message, encoding="utf-8")


# ── Step: Engineer ────────────────────────────────────────────────────


def step_engineer(
    slug: str,
    repo_name: str,
    paths: ProjectPaths,
    *,
    is_fix_round: bool = False,
) -> None:
    """Run the engineer agent."""
    wt_path = paths.worktree_path(slug, repo_name)
    spec_file = paths.spec_file(slug, f"{repo_name}-spec.md")
    log_file = paths.logs_dir(slug) / f"{repo_name}-engineer.log"
    repo_info = REPO_BY_NAME.get(repo_name)
    lang = repo_info.language if repo_info else "unknown"

    file_args: list[str] = []
    if spec_file.exists():
        file_args += ["-f", str(spec_file)]

    if is_fix_round:
        review_file = paths.spec_file(slug, f"{repo_name}-review.md")
        if review_file.exists():
            file_args += ["-f", str(review_file)]

    scope_note = ""
    if repo_info and repo_info.scope_notes:
        scope_note = f" SCOPE NOTE: {repo_info.scope_notes}"

    commit_instructions = (
        " As you implement, commit your work in small, atomic commits. "
        "Each commit should be a single logical change (one concept per "
        "commit) with a clear, descriptive message in imperative mood. "
        "Good examples: 'Add BatchRequest and BatchResponse types', "
        "'Implement batch endpoint handler', 'Add unit tests for batch "
        "processing'. Bad: one giant 'implement feature' commit. "
        "Run the project linter and test suite regularly. Look at the "
        "project config files (pyproject.toml, Cargo.toml, package.json, "
        "Makefile, etc.) to find the correct lint and test commands. "
        "Make sure lint and tests pass before your final commit."
    )

    if is_fix_round:
        message = (
            f"Review the code review feedback in the attached review file and "
            f"fix the issues found. This is a {lang} project."
            f"{scope_note}{commit_instructions}"
        )
    else:
        message = (
            f"Implement the feature described in the attached spec for this "
            f"{lang} project. Follow the repository's existing patterns and "
            f"conventions. Write tests for your changes."
            f"{scope_note}{commit_instructions}"
        )

    # Simple-bug path: no spec file, use input directly.
    if not spec_file.exists():
        input_file = paths.spec_file(slug, "input.md")
        if input_file.exists():
            file_args += ["-f", str(input_file)]
        message = (
            f"Fix the bug described in the attached issue for this {lang} project. "
            f"Follow the repository's existing patterns."
            f"{scope_note}{commit_instructions}"
        )

    prompt_file = paths.logs_dir(slug) / f"{repo_name}-engineer-prompt.md"
    _write_prompt(prompt_file, message)
    _run_opencode(wt_path, prompt_file, file_args, log_file)


# ── Step: Review ──────────────────────────────────────────────────────


def step_review(slug: str, repo_name: str, paths: ProjectPaths) -> bool:
    """Run the code review agent. Returns True if review passed."""
    wt_path = paths.worktree_path(slug, repo_name)
    spec_file = paths.spec_file(slug, f"{repo_name}-spec.md")
    review_file = paths.spec_file(slug, f"{repo_name}-review.md")
    log_file = paths.logs_dir(slug) / f"{repo_name}-review.log"
    repo_info = REPO_BY_NAME.get(repo_name)
    lang = repo_info.language if repo_info else "unknown"

    file_args: list[str] = []
    if spec_file.exists():
        file_args += ["-f", str(spec_file)]

    message = (
        f"Review the code changes in this {lang} repository. "
        f"Compare against the attached spec. Check for: "
        f"spec compliance, code quality and {lang}-idiomatic patterns, "
        f"test coverage, error handling, backwards compatibility. "
        f"Write your review to: {review_file} "
        f"Use this format: "
        f"## Status: PASS or NEEDS_CHANGES "
        f"## Issues Found (list each issue) "
        f"## Recommendations (list improvements)"
    )

    prompt_file = paths.logs_dir(slug) / f"{repo_name}-review-prompt.md"
    _write_prompt(prompt_file, message)
    _run_opencode(wt_path, prompt_file, file_args, log_file)

    if review_file.exists():
        content = review_file.read_text(encoding="utf-8").upper()
        return "NEEDS_CHANGES" not in content
    return True


# ── Step: PR ──────────────────────────────────────────────────────────


def step_pr(slug: str, repo_name: str, paths: ProjectPaths) -> None:
    """Create a pull request."""
    wt_path = paths.worktree_path(slug, repo_name)
    spec_file = paths.spec_file(slug, f"{repo_name}-spec.md")
    log_file = paths.logs_dir(slug) / f"{repo_name}-pr.log"
    repo_info = REPO_BY_NAME.get(repo_name)
    lang = repo_info.language if repo_info else "unknown"

    file_args: list[str] = []
    if spec_file.exists():
        file_args += ["-f", str(spec_file)]

    from lib.pr import _find_pr_template

    template = _find_pr_template(wt_path)
    template_instruction = ""
    if template:
        file_args += ["-f", str(template)]
        template_instruction = (
            f" IMPORTANT: This repository has a PR template at {template.name}. "
            f"It is attached. You MUST follow its structure when writing the PR body."
        )

    message = (
        f"Create a pull request for the changes in this {lang} repository. "
        f"Steps: "
        f"1. Review all uncommitted changes and commit them if needed. "
        f"2. Push the branch to the remote. "
        f"3. Create a pull request using `gh pr create`. "
        f"4. Write a clear title and description summarizing the changes. "
        f"5. Reference the original issue if applicable."
        f"{template_instruction}"
    )

    prompt_file = paths.logs_dir(slug) / f"{repo_name}-pr-prompt.md"
    _write_prompt(prompt_file, message)
    _run_opencode(wt_path, prompt_file, file_args, log_file)


# ── Step: CI watch ────────────────────────────────────────────────────


def step_ci_watch(
    slug: str,
    repo_name: str,
    paths: ProjectPaths,
    *,
    max_fix_rounds: int = 2,
    poll_interval: int = 30,
    poll_timeout: int = 1800,
) -> None:
    """Poll CI and fix failures."""
    from lib.pr import _get_ci_status, _collect_ci_failure_logs

    wt_path = paths.worktree_path(slug, repo_name)

    for fix_round in range(max_fix_rounds + 1):
        elapsed = 0
        status = "pending"
        detail = ""
        while elapsed < poll_timeout:
            status, detail = _get_ci_status(wt_path)
            if status in ("pass", "fail", "no-ci", "no-pr"):
                break
            print(f"  [{repo_name}] CI pending: {detail}")
            time.sleep(poll_interval)
            elapsed += poll_interval

        if status == "pass":
            print(f"  [{repo_name}] CI passed: {detail}")
            return
        if status in ("no-ci", "no-pr"):
            print(f"  [{repo_name}] No CI: {detail}")
            return

        print(f"  [{repo_name}] CI failed: {detail}")

        if fix_round >= max_fix_rounds:
            print(f"  [{repo_name}] Max CI fix rounds reached.")
            return

        # Fix CI failures.
        failure_log = _collect_ci_failure_logs(wt_path)
        ci_log_file = paths.spec_file(slug, f"{repo_name}-ci-failures.md")
        ci_log_file.write_text(failure_log, encoding="utf-8")

        repo_info = REPO_BY_NAME.get(repo_name)
        lang = repo_info.language if repo_info else "unknown"
        log_file = paths.logs_dir(slug) / f"{repo_name}-ci-fix.log"

        file_args: list[str] = []
        if ci_log_file.exists():
            file_args += ["-f", str(ci_log_file)]

        message = (
            f"The CI pipeline is failing for this {lang} project. "
            f"The attached file lists the failed checks. "
            f"Investigate the failures by running the linter and tests locally. "
            f"Fix the issues. Make sure the linter passes and all tests pass. "
            f"Commit your fixes and push."
        )

        print(f"  [{repo_name}] Fixing CI (round {fix_round + 1})...")
        update_repo_step(slug, repo_name, f"ci-fix (round {fix_round + 1})", paths)

        prompt_file = paths.logs_dir(slug) / f"{repo_name}-ci-fix-prompt.md"
        _write_prompt(prompt_file, message)
        _run_opencode(wt_path, prompt_file, file_args, log_file)

        subprocess.run(["git", "push"], cwd=str(wt_path))


# ── Main pipeline ─────────────────────────────────────────────────────


def run_repo_pipeline(
    slug: str,
    repo_name: str,
    *,
    max_review_rounds: int = 2,
) -> None:
    """Run the full build pipeline for a single repo."""
    paths = get_project_paths()

    print(f"\n{'=' * 50}")
    print(f"  [{repo_name}] Starting build pipeline")
    print(f"{'=' * 50}\n")

    # Engineer + review loop.
    for review_round in range(max_review_rounds):
        is_fix = review_round > 0
        step_label = f"engineer-fix-{review_round}" if is_fix else "engineer"

        print(f"\n  [{repo_name}] -> {step_label}")
        update_repo_step(slug, repo_name, step_label, paths)
        step_engineer(slug, repo_name, paths, is_fix_round=is_fix)

        print(f"\n  [{repo_name}] -> review (round {review_round + 1})")
        update_repo_step(slug, repo_name, f"review-{review_round + 1}", paths)
        passed = step_review(slug, repo_name, paths)

        if passed:
            print(f"  [{repo_name}] Review passed.")
            break
        print(f"  [{repo_name}] Review: needs changes.")

    # PR creation.
    print(f"\n  [{repo_name}] -> pr")
    update_repo_step(slug, repo_name, "pr", paths)
    step_pr(slug, repo_name, paths)

    # CI watch + fix.
    print(f"\n  [{repo_name}] -> ci-watch")
    update_repo_step(slug, repo_name, "ci-watch", paths)
    step_ci_watch(slug, repo_name, paths)

    # Done.
    print(f"\n  [{repo_name}] Build pipeline complete.")
    update_repo_step(slug, repo_name, "done", paths)


# ── CLI entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <slug> <repo-name>", file=sys.stderr)
        sys.exit(1)
    run_repo_pipeline(sys.argv[1], sys.argv[2])

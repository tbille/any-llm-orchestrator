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
    result = subprocess.run(["sh", "-c", cmd], cwd=str(wt_path))
    if result.returncode != 0:
        print(
            f"  [WARN] opencode exited with code {result.returncode}",
            file=sys.stderr,
        )
    return result.returncode


# Phases where detailed, clear output matters more than token savings.
_VERBOSE_PHASES = frozenset({"review", "cross-review", "pr"})


def _write_prompt(path: Path, message: str, *, phase: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = "" if phase in _VERBOSE_PHASES else CAVEMAN_PROMPT
    path.write_text(prefix + message, encoding="utf-8")


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

    test_note = ""
    if repo_info and repo_info.test_hints:
        test_note = f" TESTING: {repo_info.test_hints}"

    commit_instructions = (
        " As you implement, commit your work in small, atomic commits. "
        "Each commit should be a single logical change (one concept per "
        "commit) with a clear, descriptive message in imperative mood. "
        "Good examples: 'Add BatchRequest and BatchResponse types', "
        "'Implement batch endpoint handler', 'Add unit tests for batch "
        "processing'. Bad: one giant 'implement feature' commit."
        f"{test_note}"
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
    _write_prompt(prompt_file, message, phase="engineer")
    rc = _run_opencode(wt_path, prompt_file, file_args, log_file)
    if rc != 0:
        print(f"  [{repo_name}] Engineer agent exited with code {rc}", file=sys.stderr)


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
    _write_prompt(prompt_file, message, phase="review")
    rc = _run_opencode(wt_path, prompt_file, file_args, log_file)
    if rc != 0:
        print(f"  [{repo_name}] Review agent exited with code {rc}", file=sys.stderr)

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
    _write_prompt(prompt_file, message, phase="pr")
    rc = _run_opencode(wt_path, prompt_file, file_args, log_file)
    if rc != 0:
        print(f"  [{repo_name}] PR agent exited with code {rc}", file=sys.stderr)


# ── Step: CI watch ────────────────────────────────────────────────────


def step_ci_watch(
    slug: str,
    repo_name: str,
    paths: ProjectPaths,
    *,
    max_fix_rounds: int = 2,
    poll_interval: int = 30,
) -> None:
    """Poll CI and fix failures."""
    from lib.pr import _get_ci_status, _collect_ci_failure_logs

    wt_path = paths.worktree_path(slug, repo_name)

    for fix_round in range(max_fix_rounds + 1):
        status = "pending"
        detail = ""
        while True:
            status, detail = _get_ci_status(wt_path)
            if status in ("pass", "fail", "no-ci", "no-pr"):
                break
            print(f"  [{repo_name}] CI pending: {detail}")
            time.sleep(poll_interval)

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
        _write_prompt(prompt_file, message, phase="ci-fix")
        rc = _run_opencode(wt_path, prompt_file, file_args, log_file)
        if rc != 0:
            print(
                f"  [{repo_name}] CI fix agent exited with code {rc}",
                file=sys.stderr,
            )

        push_result = subprocess.run(
            ["git", "push"], cwd=str(wt_path), capture_output=True, text=True
        )
        if push_result.returncode != 0:
            print(
                f"  [{repo_name}] git push failed after CI fix: "
                f"{push_result.stderr.strip()[:200]}",
                file=sys.stderr,
            )


# ── Step: Fix PR feedback ─────────────────────────────────────────────


def step_fix_pr(slug: str, repo_name: str, paths: ProjectPaths) -> None:
    """Fetch PR review comments and send the engineer to address them.

    Collects **all** feedback on the PR:
    - Top-level review bodies (approve / request-changes summaries)
    - General conversation comments
    - Inline review comments on specific files and lines (via the REST API)
    - The overall review decision
    """
    import json as _json

    update_repo_step(slug, repo_name, "fix-pr", paths)
    wt_path = paths.worktree_path(slug, repo_name)
    repo_info = REPO_BY_NAME.get(repo_name)
    lang = repo_info.language if repo_info else "unknown"
    log_file = paths.logs_dir(slug) / f"{repo_name}-pr-fix.log"
    feedback_file = paths.spec_file(slug, f"{repo_name}-pr-feedback.md")

    # ── 1. Fetch PR metadata, reviews, and general comments ───────────
    print(f"  [{repo_name}] Fetching PR review comments...")
    pr_data = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            "--json",
            "title,url,number,reviews,comments",
        ],
        cwd=str(wt_path),
        capture_output=True,
        text=True,
    )
    if pr_data.returncode != 0:
        print(
            f"  [{repo_name}] No PR found or gh error: {pr_data.stderr.strip()[:100]}"
        )
        update_repo_step(slug, repo_name, "done", paths)
        return

    try:
        data = _json.loads(pr_data.stdout)
    except _json.JSONDecodeError:
        print(f"  [{repo_name}] Could not parse PR data.")
        update_repo_step(slug, repo_name, "done", paths)
        return

    # ── 2. Fetch review decision ──────────────────────────────────────
    decision_result = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            "--json",
            "reviewDecision",
            "--jq",
            ".reviewDecision",
        ],
        cwd=str(wt_path),
        capture_output=True,
        text=True,
    )
    review_decision = (
        decision_result.stdout.strip() if decision_result.returncode == 0 else ""
    )

    # ── 3. Fetch inline review comments (file/line-level) ────────────
    #    These are NOT included in `gh pr view --json reviews`.
    #    Use the REST API: GET /repos/{owner}/{repo}/pulls/{number}/comments
    pr_number = data.get("number")
    inline_comments: list[dict] = []
    if pr_number:
        inline_result = subprocess.run(
            [
                "gh",
                "api",
                "--paginate",
                "repos/{owner}/{repo}/pulls/" + str(pr_number) + "/comments",
            ],
            cwd=str(wt_path),
            capture_output=True,
            text=True,
        )
        if inline_result.returncode == 0 and inline_result.stdout.strip():
            try:
                inline_comments = _json.loads(inline_result.stdout)
                if not isinstance(inline_comments, list):
                    inline_comments = []
            except _json.JSONDecodeError:
                inline_comments = []

    # ── 4. Build feedback markdown ────────────────────────────────────
    lines = [
        f"# PR Review Feedback: {repo_name}",
        f"",
        f"**PR:** {data.get('url', 'N/A')}",
        f"**Title:** {data.get('title', 'N/A')}",
        f"",
    ]

    if review_decision:
        lines.append(f"**Review Decision:** {review_decision}")
        lines.append("")

    # Top-level review bodies (approve / changes-requested summaries).
    reviews = data.get("reviews") or []
    if reviews:
        lines.append("## Reviews")
        lines.append("")
        for review in reviews:
            author = review.get("author", {}).get("login", "unknown")
            state = review.get("state", "")
            body = review.get("body", "").strip()
            lines.append(f"### @{author} ({state})")
            if body:
                lines.append("")
                lines.append(body)
            lines.append("")

    # Inline review comments (file/line-level code feedback).
    if inline_comments:
        lines.append("## Inline Code Comments")
        lines.append("")
        lines.append(
            "These are comments left on specific files and lines. Address each one."
        )
        lines.append("")
        for ic in inline_comments:
            author = ic.get("user", {}).get("login", "unknown")
            file_path = ic.get("path", "unknown")
            line = ic.get("original_line") or ic.get("line") or "?"
            body = ic.get("body", "").strip()
            diff_hunk = ic.get("diff_hunk", "").strip()
            if not body:
                continue
            lines.append(f"### `{file_path}` (line {line}) — @{author}")
            if diff_hunk:
                lines.append("")
                lines.append("```diff")
                # Show only the last few lines of the hunk for context.
                hunk_lines = diff_hunk.splitlines()
                for hl in hunk_lines[-8:]:
                    lines.append(hl)
                lines.append("```")
            lines.append("")
            lines.append(body)
            lines.append("")

    # General conversation comments (not attached to specific lines).
    comments = data.get("comments") or []
    if comments:
        lines.append("## General Comments")
        lines.append("")
        for comment in comments:
            author = comment.get("author", {}).get("login", "unknown")
            body = comment.get("body", "").strip()
            if body:
                lines.append(f"**@{author}:** {body}")
                lines.append("")

    feedback_content = "\n".join(lines)
    feedback_file.write_text(feedback_content, encoding="utf-8")

    has_feedback = reviews or inline_comments or comments
    print(
        f"  [{repo_name}] Feedback saved: "
        f"{len(reviews)} reviews, "
        f"{len(inline_comments)} inline comments, "
        f"{len(comments)} general comments"
    )

    if not has_feedback:
        print(f"  [{repo_name}] No review comments found on the PR.")
        update_repo_step(slug, repo_name, "done", paths)
        return

    # ── 5. Send engineer to fix ───────────────────────────────────────
    test_note = ""
    if repo_info and repo_info.test_hints:
        test_note = f" TESTING: {repo_info.test_hints}"

    message = (
        f"Address ALL the PR review feedback in the attached file for this {lang} project. "
        f"Read each review comment AND each inline code comment carefully and "
        f"make the requested changes. Pay special attention to the inline code "
        f"comments in the 'Inline Code Comments' section — these point to "
        f"specific files and lines that need changes. "
        f"Commit your fixes in atomic commits."
        f"{test_note}"
    )

    file_args: list[str] = ["-f", str(feedback_file)]
    spec_file = paths.spec_file(slug, f"{repo_name}-spec.md")
    if spec_file.exists():
        file_args += ["-f", str(spec_file)]

    prompt_file = paths.logs_dir(slug) / f"{repo_name}-pr-fix-prompt.md"
    _write_prompt(prompt_file, message, phase="pr-fix")
    _run_opencode(wt_path, prompt_file, file_args, log_file)

    # Push the fixes.
    print(f"  [{repo_name}] Pushing fixes...")
    push_result = subprocess.run(
        ["git", "push"], cwd=str(wt_path), capture_output=True, text=True
    )
    if push_result.returncode != 0:
        print(
            f"  [{repo_name}] git push failed after PR fix: "
            f"{push_result.stderr.strip()[:200]}",
            file=sys.stderr,
        )
    else:
        print(f"  [{repo_name}] PR fixes pushed.")
    update_repo_step(slug, repo_name, "done", paths)


# ── Step: Fix cross-review findings ───────────────────────────────────


def step_fix_cross_review(slug: str, repo_name: str, paths: ProjectPaths) -> None:
    """Read cross-review findings and send the engineer to fix repo-specific issues."""
    wt_path = paths.worktree_path(slug, repo_name)
    cross_review_file = paths.spec_file(slug, "cross-review.md")
    spec_file = paths.spec_file(slug, f"{repo_name}-spec.md")
    log_file = paths.logs_dir(slug) / f"{repo_name}-xfix.log"
    repo_info = REPO_BY_NAME.get(repo_name)
    lang = repo_info.language if repo_info else "unknown"

    if not cross_review_file.exists():
        print(f"  [{repo_name}] No cross-review file found, skipping.")
        return

    file_args: list[str] = ["-f", str(cross_review_file)]
    if spec_file.exists():
        file_args += ["-f", str(spec_file)]

    test_note = ""
    if repo_info and repo_info.test_hints:
        test_note = f" TESTING: {repo_info.test_hints}"

    message = (
        f"The cross-repository review found issues that need fixing in this "
        f"{lang} repository ({repo_name}). The attached cross-review.md "
        f"contains the full review. Look at the 'Summary of Findings' table "
        f"and the 'Recommendations' section. Fix ONLY the findings that "
        f"mention this repository ({repo_name}). Ignore findings for other "
        f"repos. Commit your fixes in atomic commits and push."
        f"{test_note}"
    )

    print(f"  [{repo_name}] Fixing cross-review findings...")
    prompt_file = paths.logs_dir(slug) / f"{repo_name}-xfix-prompt.md"
    _write_prompt(prompt_file, message, phase="xfix")
    _run_opencode(wt_path, prompt_file, file_args, log_file)

    # Push the fixes.
    print(f"  [{repo_name}] Pushing cross-review fixes...")
    push_result = subprocess.run(
        ["git", "push"], cwd=str(wt_path), capture_output=True, text=True
    )
    if push_result.returncode != 0:
        print(
            f"  [{repo_name}] git push failed after cross-review fix: "
            f"{push_result.stderr.strip()[:200]}",
            file=sys.stderr,
        )
    else:
        print(f"  [{repo_name}] Cross-review fixes pushed.")


def run_cross_review_fix_pipeline(
    slug: str,
    repo_name: str,
) -> None:
    """Run the cross-review fix pipeline for a single repo.

    Called from a tmux pane by the orchestrator. Sequences:
    fix cross-review -> CI watch -> done.
    """
    paths = get_project_paths()

    print(f"\n{'=' * 50}")
    print(f"  [{repo_name}] Starting cross-review fix pipeline")
    print(f"{'=' * 50}\n")

    update_repo_step(slug, repo_name, "xfix", paths)
    step_fix_cross_review(slug, repo_name, paths)

    # CI watch after the fix.
    print(f"\n  [{repo_name}] -> ci-watch (post cross-review fix)")
    update_repo_step(slug, repo_name, "xfix-ci", paths)
    step_ci_watch(slug, repo_name, paths)

    print(f"\n  [{repo_name}] Cross-review fix pipeline complete.")
    update_repo_step(slug, repo_name, "xfix-done", paths)


# ── Fix PR pipeline (single repo, run from tmux pane) ─────────────────


def run_fix_pr_pipeline(
    slug: str,
    repo_name: str,
) -> None:
    """Run the fix-PR pipeline for a single repo.

    Called from a tmux pane by the dashboard or CLI. Sequences:
    fetch PR feedback -> engineer fix -> push -> done.
    """
    paths = get_project_paths()

    print(f"\n{'=' * 50}")
    print(f"  [{repo_name}] Starting fix-PR pipeline")
    print(f"{'=' * 50}\n")

    step_fix_pr(slug, repo_name, paths)

    print(f"\n  [{repo_name}] Fix-PR pipeline complete.")


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
    review_passed = False
    for review_round in range(max_review_rounds):
        is_fix = review_round > 0
        step_label = f"engineer-fix-{review_round}" if is_fix else "engineer"

        print(f"\n  [{repo_name}] -> {step_label}")
        update_repo_step(slug, repo_name, step_label, paths)
        step_engineer(slug, repo_name, paths, is_fix_round=is_fix)

        print(f"\n  [{repo_name}] -> review (round {review_round + 1})")
        update_repo_step(slug, repo_name, f"review-{review_round + 1}", paths)
        review_passed = step_review(slug, repo_name, paths)

        if review_passed:
            print(f"  [{repo_name}] Review passed.")
            update_repo_step(slug, repo_name, "review-passed", paths)
            break
        print(f"  [{repo_name}] Review: needs changes.")

    if not review_passed:
        print(
            f"  [{repo_name}] [WARN] Review never passed after "
            f"{max_review_rounds} rounds. Proceeding to PR anyway.",
            file=sys.stderr,
        )
        update_repo_step(slug, repo_name, "review-not-passed", paths)

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
    flag = sys.argv[3] if len(sys.argv) >= 4 else None
    if flag == "--fix-cross-review":
        run_cross_review_fix_pipeline(sys.argv[1], sys.argv[2])
    elif flag == "--fix-pr":
        run_fix_pr_pipeline(sys.argv[1], sys.argv[2])
    elif len(sys.argv) == 3:
        run_repo_pipeline(sys.argv[1], sys.argv[2])
    else:
        print(
            f"Usage: {sys.argv[0]} <slug> <repo-name> [--fix-cross-review|--fix-pr]",
            file=sys.stderr,
        )
        sys.exit(1)

# AGENTS.md

Multi-repo orchestrator for the any-llm ecosystem. Coordinates feature work across 6 repositories using AI agents via opencode. Zero Python dependencies — everything is stdlib.

## System requirements

All must be on PATH: `uv`, `opencode`, `gh` (authenticated), `git`, `tmux`.
Optional: `wt` (worktrunk) — falls back to `git worktree add`.

Python 3.12 (pinned in `.python-version`). macOS/Linux only — uses `fcntl.flock()`.

## Running

```sh
uv run orchestrate.py --issue <github-issue-url>
uv run orchestrate.py --prompt "description"
uv run orchestrate.py --prompt "description" --headless  # no TUI interaction for PM/debate
uv run orchestrate.py --resume <slug>
uv run orchestrate.py --resume <slug> --skip-to engineer
uv run orchestrate.py --resume <slug> --ci-check all
uv run orchestrate.py --resume <slug> --fix-pr all
uv run dashboard.py                    # http://localhost:8080
```

There are no build, test, lint, format, or typecheck commands for this repo itself. No CI pipeline exists. No Makefile, pre-commit, or test suite.

## Architecture

- `orchestrate.py` — CLI entry point. Phases run sequentially: intake → PM → debate → design → architect → workspace setup → engineer (tmux) → code review → cross-review → PR creation. Supports `--headless` for non-interactive PM/debate.
- `dashboard.py` — Standalone HTTP server with inline HTML/JS. No build step.
- `lib/config.py` — Repo registry, env-var tunables, path helpers. Source of truth for repo metadata. Each `RepoInfo` now includes `test_command` for pre-review build checks.
- `lib/intake.py` — Fetches issues via `gh`, classifies via opencode headless mode. Parses opencode's `--format json` output as newline-delimited JSON events.
- `lib/parse.py` — Structured output parsing for agent responses. Extracts JSON blocks, review verdicts, and cross-review repo lists. Replaces ad-hoc string matching.
- `lib/workspace.py` — Clones repos to `repos/`, creates worktrees under `specs/<slug>/repos/`. Injects `AGENTS.md` into each worktree before the build phase.
- `lib/engineer.py` — Launches per-repo pipelines as tmux panes. Each pane runs `uv run python lib/repo_runner.py <slug> <repo>`. Build phase has a configurable timeout.
- `lib/repo_runner.py` — Both a module and a standalone script (has `sys.path` manipulation). Runs in tmux panes. Includes pre-review build check and simple bug investigation steps.
- `lib/status.py` — Concurrent-safe status tracking via `fcntl.flock()` and atomic write-then-rename to `status.json`.
- `lib/pr.py` — Tries deterministic PR creation first (shell commands only). Falls back to AI agent only when a PR template needs filling.
- `lib/costs.py` — Reads opencode's SQLite DB directly for cost/token aggregation.

## Key directories

- `repos/` — Cloned upstream repos (gitignored, created at runtime)
- `specs/<slug>/` — Per-feature workspace: specs, reviews, status.json, costs.json, `repos/` (worktrees), `logs/`
- `.opencode/agents/` — Six agent definitions (product-manager, reviewer, designer, architect, code-reviewer, pr-creator)

## Non-obvious behaviors

- **Resumability**: Each phase writes output to `specs/<slug>/`. If the output file exists, the phase is skipped on re-run.
- **Cost guardrail**: Pipeline pauses before expensive phases if accumulated cost exceeds `$ORCHESTRATOR_COST_CEILING` (default $200).
- **Draft PRs**: If code review doesn't pass after `MAX_REVIEW_ROUNDS` (default 2), a draft PR is created instead.
- **Context isolation**: Each engineer agent runs in its own worktree with only its per-repo spec. It never sees other repos' code.
- **`any-llm` scope trap**: The `any-llm` repo contains gateway *client* code (in scope) but gateway *server* code lives in the `gateway` repo. Agents are explicitly warned not to add server code to `any-llm`.
- **`any-llm-platform` uses `develop` branch**, not `main`. All other repos use `main`.
- **CAVEMAN_PROMPT** in `lib/config.py` is applied to headless agent calls for token savings. It includes the instruction to never create AGENTS.md files unless asked.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ORCHESTRATOR_MAX_REVIEW_ROUNDS` | 2 | Engineer → review → fix cycles before PR |
| `ORCHESTRATOR_MAX_CI_FIX_ROUNDS` | 2 | CI fail → fix → re-push cycles |
| `ORCHESTRATOR_CI_POLL_INTERVAL` | 30 | Seconds between CI polls |
| `ORCHESTRATOR_CLASSIFIER_TIMEOUT` | 120 | Headless classifier timeout (seconds) |
| `ORCHESTRATOR_COST_CEILING` | 200.0 | USD cost ceiling before pipeline pauses |
| `ORCHESTRATOR_BUILD_PHASE_TIMEOUT` | 5400 | Build phase tmux wait timeout (seconds, default 90 min) |

## Code conventions

- `from __future__ import annotations` in every file
- Type hints throughout, `Path` objects (not strings) for filesystem paths
- Section headers use `# ── Name ──────` box-drawing style
- f-strings exclusively for formatting
- `subprocess.run` with `capture_output=True`, errors to stderr

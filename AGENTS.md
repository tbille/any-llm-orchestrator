# AGENTS.md

Multi-repo orchestrator for the any-llm ecosystem. Coordinates feature work across 6 repositories using AI agents via opencode. Zero Python dependencies — everything is stdlib. Packaged as `totomisu`.

## System requirements

All must be on PATH: `opencode`, `gh` (authenticated), `git`, `tmux`.
Optional: `uv` (used by individual repo test commands), `wt` (worktrunk) — falls back to `git worktree add`.

Python 3.12 (pinned in `.python-version`). macOS/Linux only — uses `fcntl.flock()`.

## Installation

```sh
pip install .          # or: uv pip install .
```

This installs the `totomisu` command on PATH.

## Running

```sh
totomisu init                                         # set up workspace (clones repos, creates dirs)
totomisu run --issue <github-issue-url>
totomisu run --prompt "description"
totomisu run --prompt "description" --headless        # no TUI interaction for PM/debate
totomisu run --resume <slug>
totomisu run --resume <slug> --skip-to engineer
totomisu run --resume <slug> --ci-check all
totomisu run --resume <slug> --fix-pr all
totomisu dashboard                                    # http://localhost:8080
```

There are no build, test, lint, format, or typecheck commands for this repo itself. No CI pipeline exists. No Makefile, pre-commit, or test suite.

## Architecture

- `totomisu/cli.py` — CLI entry point with subcommands: `init`, `run`, `dashboard`, `_repo-runner` (hidden, for tmux panes). The `init` command sets up a workspace directory with repos, specs, and agent definitions. The `run` command orchestrates the pipeline. Workspace resolution: `$TOTOMISU_WORKSPACE` env → walk up from cwd for `.totomisu` marker → `~/.config/totomisu/config.json`.
- `totomisu/dashboard_server.py` — Standalone HTTP server. Frontend assets bundled in `totomisu/data/dashboard/`.
- `totomisu/config.py` — Repo registry, env-var tunables, path helpers. Source of truth for repo metadata. Each `RepoInfo` now includes `test_command` for pre-review build checks. `get_project_paths()` resolves the workspace root. `get_package_data_path()` locates bundled assets.
- `totomisu/intake.py` — Fetches issues via `gh`, classifies via opencode headless mode. The classifier returns a `phases` list (subset of pm, debate, designer, architect) that controls which spec agents run. Parses opencode's `--format json` output as newline-delimited JSON events.
- `totomisu/parse.py` — Structured output parsing for agent responses. Extracts JSON blocks, review verdicts, and cross-review repo lists. Replaces ad-hoc string matching.
- `totomisu/workspace.py` — Clones repos to `repos/`, creates worktrees under `specs/<slug>/repos/`. Injects `AGENTS.md` into each worktree before the build phase.
- `totomisu/engineer.py` — Launches per-repo pipelines as tmux panes. Each pane runs `totomisu _repo-runner <slug> <repo>`. Build phase has a configurable timeout.
- `totomisu/repo_runner.py` — Per-repo pipeline module. Runs in tmux panes via the hidden `_repo-runner` CLI subcommand. Includes pre-review build check and simple bug investigation steps.
- `totomisu/status.py` — Concurrent-safe status tracking via `fcntl.flock()` and atomic write-then-rename to `status.json`.
- `totomisu/pr.py` — Tries deterministic PR creation first (shell commands only). Falls back to AI agent only when a PR template needs filling.
- `totomisu/costs.py` — Reads opencode's SQLite DB directly for cost/token aggregation.

## Key directories (workspace)

After `totomisu init`, the workspace contains:
- `repos/` — Cloned upstream repos
- `specs/<slug>/` — Per-feature workspace: specs, reviews, status.json, costs.json, `repos/` (worktrees), `logs/`
- `.opencode/agents/` — Six agent definitions (copied from package data during init)
- `.totomisu` — Workspace marker file (JSON with version and path)

## Key directories (package)

- `totomisu/data/agents/` — Bundled agent definition .md files
- `totomisu/data/dashboard/` — Bundled frontend assets (HTML/CSS/JS)

## Non-obvious behaviors

- **Workspace resolution**: `get_project_paths()` checks: (1) `$TOTOMISU_WORKSPACE` env var, (2) walk up from cwd for `.totomisu` marker, (3) `~/.config/totomisu/config.json`.
- **Resumability**: Each phase writes output to `specs/<slug>/`. If the output file exists, the phase is skipped on re-run.
- **Cost guardrail**: Pipeline pauses before expensive phases if accumulated cost exceeds `$ORCHESTRATOR_COST_CEILING` (default $200).
- **Draft PRs**: If code review doesn't pass after `MAX_REVIEW_ROUNDS` (default 2), a draft PR is created instead.
- **Context isolation**: Each engineer agent runs in its own worktree with only its per-repo spec. It never sees other repos' code.
- **`any-llm` scope trap**: The `any-llm` repo contains gateway *client* code (in scope) but gateway *server* code lives in the `gateway` repo. Agents are explicitly warned not to add server code to `any-llm`.
- **`any-llm-platform` uses `develop` branch**, not `main`. All other repos use `main`.
- **CAVEMAN_PROMPT** in `totomisu/config.py` is applied to headless agent calls for token savings. It includes the instruction to never create AGENTS.md files unless asked.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `TOTOMISU_WORKSPACE` | (none) | Override workspace path |
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

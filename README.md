# any-llm-world

Multi-repo orchestrator for the [any-llm ecosystem](https://github.com/mozilla-ai). Coordinates feature work, bug fixes, and cross-repo changes across all six repositories from a single entry point.

## Repositories

| Repo | Language | Role |
|------|----------|------|
| [any-llm](https://github.com/mozilla-ai/any-llm) | Python | Core SDK -- common interface for LLM calls |
| [gateway](https://github.com/mozilla-ai/gateway) | Python | Gateway service -- routes LLM requests, captures observability |
| [any-llm-rust](https://github.com/mozilla-ai/any-llm-rust) | Rust | Rust SDK -- talks to the gateway |
| [any-llm-go](https://github.com/mozilla-ai/any-llm-go) | Go | Go SDK -- talks to the gateway |
| [any-llm-ts](https://github.com/mozilla-ai/any-llm-ts) | TypeScript | TypeScript SDK -- talks to the gateway |
| [any-llm-platform](https://github.com/mozilla-ai/any-llm-platform) | Python | Platform -- budgets, users, observability |

## Prerequisites

- [uv](https://docs.astral.sh/uv/)
- [opencode](https://opencode.ai) with a configured provider
- [gh](https://cli.github.com/) (GitHub CLI, authenticated)
- [tmux](https://github.com/tmux/tmux)
- git
- [wt](https://worktrunk.dev/) (optional -- falls back to `git worktree add` if not installed)

## Usage

```sh
# From a GitHub issue
uv run orchestrate.py --issue https://github.com/mozilla-ai/any-llm/issues/123

# From a free-form prompt
uv run orchestrate.py --prompt "Add batch API support to all SDKs"

# Headless mode (PM and debate run non-interactively)
uv run orchestrate.py --prompt "Add batch API support to all SDKs" --headless

# Resume a previous run
uv run orchestrate.py --resume add-batch-api

# Skip to a specific phase
uv run orchestrate.py --resume add-batch-api --skip-to build

# Check CI status for all repos (or a specific one)
uv run orchestrate.py --resume add-batch-api --ci-check
uv run orchestrate.py --resume add-batch-api --ci-check any-llm

# Fix PR review comments
uv run orchestrate.py --resume add-batch-api --fix-pr
uv run orchestrate.py --resume add-batch-api --fix-pr gateway

# Fix cross-review findings
uv run orchestrate.py --resume add-batch-api --fix-cross-review
uv run orchestrate.py --resume add-batch-api --fix-cross-review any-llm-ts
```

### CLI flags

| Flag | Description |
|------|-------------|
| `--issue URL` | GitHub issue URL to work on |
| `--prompt TEXT` | Free-form prompt describing the work |
| `--resume SLUG` | Resume a previous run from its slug |
| `--skip-to PHASE` | Skip to a specific phase (requires `--resume`). Choices: `intake`, `workspace`, `pm`, `debate`, `designer`, `architect`, `build`, `cross-review`, `cross-review-fix` |
| `--headless` | Run PM and debate phases non-interactively. The PRD is generated and self-critiqued in a single pass. |
| `--ci-check [REPO]` | Check CI status for all repos or a specific repo (requires `--resume`) |
| `--fix-pr [REPO]` | Fetch PR review comments and send engineer to fix (requires `--resume`) |
| `--fix-cross-review [REPO]` | Fix cross-review findings for all affected repos or a specific one (requires `--resume`) |

## How it works

The orchestrator triages the input and routes it through a dynamic set of spec phases based on the nature of the work. The intake classifier selects which phases to run -- purely technical features skip PM/debate/designer, simple bugs go straight to build, and so on.

```
                                           Workspace setup
                                           (clone + worktrees)
                                                   │
                         ┌─ simple-bug ────────────┼──────────────────┐
                         │                         │                  │
Input ─> Triage ─────────┼─ complex-bug ──> Architect (light) ───────┤
                         │                         │                  │
                         └─ feature ──> PM* ──> Debate* ──> Designer?┤
                                                   ──> Architect     │
                                                                     v
                                              Build (per-repo, parallel)
                              ┌──────────────────┼──────────────────┐
                              v                  v                  v
                          any-llm            gateway           any-llm-ts
                        ┌──────────┐       ┌──────────┐      ┌──────────┐
                        │ engineer │       │ engineer │      │ engineer │
                        │ test     │       │ test     │      │ test     │
                        │ review   │       │ review   │      │ review   │
                        │ PR       │       │ PR       │      │ PR       │
                        │ CI watch │       │ CI watch │      │ CI watch │
                        └────┬─────┘       └────┬─────┘      └────┬─────┘
                             └──────────────────┼─────────────────┘
                                                v
                                       Cross-repo review
```

*\* The intake classifier chooses which spec phases to run. For features, the default is all four (PM, debate, designer, architect). Technical features may skip PM/debate/designer. The classifier's recommendation can be overridden at the confirmation prompt.*

Workspace runs right after triage so that all subsequent agents have the repo code available under `specs/<slug>/repos/`. Each repo flows through its own build pipeline independently -- no waiting for other repos.

### Phases

| Phase | Mode | What happens |
|-------|------|-------------|
| **Intake + Triage** | Headless | Fetches the issue via `gh`, classifies as simple-bug / complex-bug / feature, and selects which spec phases to run. You confirm or override. |
| **Workspace** | Automated | Runs right after triage. Clones missing repos, creates git worktrees (via `wt` or `git worktree add` fallback), rebases onto the latest base branch. |
| **Product Manager** | Interactive TUI (or headless with `--headless`) | Creates a PRD. Asks clarifying questions if needed. Skipped if the classifier deems it unnecessary. |
| **Debate** | Interactive TUI (or headless with `--headless`) | A reviewer agent critiques the PRD. You participate until satisfied. Skipped if PM is skipped. |
| **Designer** | Interactive TUI (conditional) | Creates UX/DX proposals if the feature has user-facing impact. |
| **Architect** | Interactive TUI | Creates tech spec with shared interface contracts and per-repo specs. |
| **Build** | Parallel tmux panes | One pane per repo. Each runs: engineer -> targeted tests -> code review -> fix loop -> PR -> CI watch + fix. If code review doesn't pass after `MAX_REVIEW_ROUNDS` (default 2), a draft PR is created. |
| **Cross-review** | Headless | After all repos finish, checks cross-repo interface alignment using the full feature-branch diffs. |

### Context isolation

Each engineer agent runs in its own worktree directory with only its per-repo spec. It never sees other repos' code or specs. The architect's shared interface contract is copied into each per-repo spec so engineers can build independently without a massive shared context window.

### Build pipeline details

Each per-repo build pipeline includes several notable behaviors:

- **Targeted test execution**: Instead of running the full test suite, the pipeline detects which files changed on the feature branch and maps them to language-specific test targets (e.g., `test_module.py` for Python, `cargo test <module>` for Rust, `go test ./pkg/...` for Go, `*.test.ts` for TypeScript). Falls back to the full suite if targeted detection fails.
- **Pre-review build check**: Targeted tests run before the code review step to avoid wasting a review cycle on broken code. If tests fail, the engineer gets one immediate retry with the failure output.
- **Automatic rebase**: Before every push, the pipeline rebases onto the latest base branch. If conflicts arise, an agent attempts to resolve them (up to 5 rounds).
- **Draft PRs**: If code review doesn't pass after the configured number of review rounds, a draft PR is created instead of a regular one.
- **Simple bug investigation**: For simple bugs (no spec file), a headless investigation step scans the repo and writes a brief note identifying the likely root cause before the engineer begins.
- **Deterministic PR creation**: PRs are created via shell commands first. An AI agent is only invoked as a fallback when a PR template needs filling.

## Project structure

```
any-llm-world/
├── orchestrate.py              # CLI entry point
├── dashboard.py                # Web dashboard server
├── dashboard/                  # Dashboard frontend
│   ├── index.html              # Main dashboard page
│   ├── docs.html               # Document viewer page
│   ├── css/                    # Stylesheets
│   └── js/                     # JavaScript modules
├── lib/
│   ├── config.py               # Repo registry, paths, env-var tunables
│   ├── intake.py               # Issue fetching, triage classifier
│   ├── parse.py                # Structured output parsing (JSON, verdicts, findings)
│   ├── prd.py                  # PM, debate, designer phases
│   ├── architect.py            # Tech spec generation
│   ├── workspace.py            # Repo cloning, worktree creation
│   ├── engineer.py             # Tmux launcher, cross-repo review, fix pipelines
│   ├── repo_runner.py          # Per-repo pipeline: engineer -> test -> review -> PR -> CI
│   ├── pr.py                   # PR creation (deterministic + AI fallback), CI helpers
│   ├── costs.py                # Cost/token aggregation from opencode's SQLite DB
│   └── status.py               # Concurrent-safe status tracking (fcntl.flock)
├── .opencode/agents/           # Agent definitions
│   ├── product-manager.md
│   ├── reviewer.md
│   ├── designer.md
│   ├── architect.md
│   ├── code-reviewer.md
│   └── pr-creator.md
├── repos/                      # Cloned repositories (gitignored)
└── specs/                      # Feature specs and worktrees (gitignored)
    └── <slug>/
        ├── input.md            # Raw issue or prompt
        ├── triage.json         # Triage classification + selected phases
        ├── prd.md              # Product requirements
        ├── design.md           # Design proposals (if applicable)
        ├── tech-spec.md        # Overall technical spec
        ├── <repo>-spec.md      # Per-repo implementation specs
        ├── <repo>-review.md    # Per-repo code reviews
        ├── cross-review.md     # Cross-repo consistency review
        ├── <repo>-ci-failures.md  # CI failure logs (when fixes needed)
        ├── <repo>-addressed-comments.json  # Tracks which PR comments have been fixed
        ├── status.json         # Phase progress (read by dashboard)
        ├── costs.json          # Cost/token breakdown
        ├── repos/              # Git worktrees (gitignored)
        └── logs/               # Agent output logs (gitignored)
```

## Dashboard

Monitor and control all active features from a browser:

```sh
uv run dashboard.py              # http://localhost:8080
uv run dashboard.py --port 9090  # custom port
```

The dashboard auto-refreshes and shows:

- **Phase progress** per feature (color coded: green=done, blue=running, gray=pending)
- **Per-repo status** within the active phase, with step history timeline
- **Real-time log streaming** per repo via Server-Sent Events (click to expand)
- **Document viewer** for specs, reviews, PRDs, and other artifacts (grouped by category)
- **Cost tracking** per feature with per-repo and per-phase breakdowns
- **PR links and CI status** with `needs_rebase` detection
- **Active tmux sessions**

### Dashboard actions

The dashboard provides buttons to trigger operations without using the CLI:

| Action | What it does |
|--------|-------------|
| **Fix PRs** | Fetches PR review comments and launches engineer fix pipelines (all repos or a specific one) |
| **Stop Fixing** | Kills running fix-pr tmux sessions |
| **CI Check** | Triggers a CI status check for a specific repo |
| **Resume** | Resumes a paused pipeline from a specific phase |
| **Rebase** | Rebases a repo's worktree onto the latest base branch |
| **Cancel** | Kills all running tmux sessions for a feature and marks running phases as failed |

## Running multiple features in parallel

Each feature is fully isolated by slug -- separate spec directories, worktrees, tmux sessions, and branches. You can run multiple orchestrators simultaneously:

```sh
# Terminal 1: complete interactive phases for Feature A
uv run orchestrate.py --issue https://github.com/mozilla-ai/any-llm/issues/123

# Terminal 2: start Feature B once A's interactive phases are done
uv run orchestrate.py --prompt "Add rate limiting to the gateway"

# Terminal 3: dashboard watches both
uv run dashboard.py
```

To re-run only the build phase (e.g. after editing a spec manually):

```sh
uv run orchestrate.py --resume add-batch-api --skip-to build
```

File locking on `repos/` ensures parallel orchestrators don't corrupt shared git state during clone or worktree creation.

## Resumability

Every phase writes its output to `specs/<slug>/`. If a phase's output already exists, it is skipped on re-run. Use `--resume <slug>` to pick up where you left off.

## Cost tracking

The orchestrator reads opencode's SQLite database to track costs and token usage across all phases. Cost data is saved to `specs/<slug>/costs.json` and displayed in the dashboard.

A configurable cost guardrail pauses the pipeline before expensive phases if the accumulated cost exceeds the ceiling. You are prompted to continue or abort.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `ORCHESTRATOR_MAX_REVIEW_ROUNDS` | 2 | Engineer -> review -> fix cycles before creating a PR |
| `ORCHESTRATOR_MAX_CI_FIX_ROUNDS` | 2 | CI failure -> fix -> re-push cycles |
| `ORCHESTRATOR_CI_POLL_INTERVAL` | 30 | Seconds between CI status polls |
| `ORCHESTRATOR_CLASSIFIER_TIMEOUT` | 120 | Seconds before a headless classifier call times out |
| `ORCHESTRATOR_COST_CEILING` | 200.0 | USD cost ceiling before the pipeline pauses for confirmation |
| `ORCHESTRATOR_BUILD_PHASE_TIMEOUT` | 5400 | Build phase tmux wait timeout (seconds, default 90 min) |

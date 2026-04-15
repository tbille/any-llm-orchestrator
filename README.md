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
- [wt](https://worktrunk.dev/) (worktrunk, for worktree management)
- [tmux](https://github.com/tmux/tmux)
- git

## Usage

```sh
# From a GitHub issue
uv run orchestrate.py --issue https://github.com/mozilla-ai/any-llm/issues/123

# From a free-form prompt
uv run orchestrate.py --prompt "Add batch API support to all SDKs"

# Resume a previous run
uv run orchestrate.py --resume add-batch-api

# Skip to a specific phase (e.g. re-run only the headless parts)
uv run orchestrate.py --resume add-batch-api --skip-to engineer
```

## How it works

The orchestrator triages the input and routes it through one of three paths:

```
                                           Workspace setup
                                           (clone + worktrees)
                                                   │
                         ┌─ simple-bug ────────────┼──────────────────┐
                         │                         │                  │
Input ─> Triage ─────────┼─ complex-bug ──> Architect (light) ───────┤
                         │                         │                  │
                         └─ feature ──> PM ──> Debate ──> Designer? ─┤
                                                   ──> Architect     │
                                                                     v
                                              Build (per-repo, parallel)
                              ┌──────────────────┼──────────────────┐
                              v                  v                  v
                          any-llm            gateway           any-llm-ts
                        ┌──────────┐       ┌──────────┐      ┌──────────┐
                        │ engineer │       │ engineer │      │ engineer │
                        │ review   │       │ review   │      │ review   │
                        │ PR       │       │ PR       │      │ PR       │
                        │ CI watch │       │ CI watch │      │ CI watch │
                        └────┬─────┘       └────┬─────┘      └────┬─────┘
                             └──────────────────┼─────────────────┘
                                                v
                                       Cross-repo review
```

Workspace runs right after triage so that all subsequent agents have the repo code available under `specs/<slug>/repos/`. Each repo flows through its own build pipeline independently -- no waiting for other repos.

### Phases

| Phase | Mode | What happens |
|-------|------|-------------|
| **Intake + Triage** | Headless | Fetches the issue via `gh`, classifies as simple-bug / complex-bug / feature. You confirm or override. |
| **Workspace** | Automated | Runs right after triage. Clones missing repos, creates git worktrees via `wt`. |
| **Product Manager** | Interactive TUI | Creates a PRD. Asks clarifying questions if needed. |
| **Debate** | Interactive TUI | A reviewer agent critiques the PRD. You participate until satisfied. |
| **Designer** | Interactive TUI (conditional) | Creates UX/DX proposals if the feature has user-facing impact. |
| **Architect** | Interactive TUI | Creates tech spec with shared interface contracts and per-repo specs. |
| **Build** | Parallel tmux panes | One pane per repo, each running the full pipeline independently: engineer -> code review -> fix loop -> PR -> CI watch + fix. No repo waits for another. |
| **Cross-review** | Headless | After all repos finish, checks cross-repo interface alignment. |

### Context isolation

Each engineer agent runs in its own worktree directory with only its per-repo spec. It never sees other repos' code or specs. The architect's shared interface contract is copied into each per-repo spec so engineers can build independently without a massive shared context window.

## Project structure

```
any-llm-world/
├── orchestrate.py              # CLI entry point
├── dashboard.py                # Web dashboard server
├── lib/
│   ├── config.py               # Repo registry, paths, ecosystem context
│   ├── intake.py               # Issue fetching, triage classifier
│   ├── prd.py                  # PM, debate, designer phases
│   ├── architect.py            # Tech spec generation
│   ├── workspace.py            # Repo cloning, worktree creation
│   ├── engineer.py             # Tmux launcher, cross-repo review
│   ├── repo_runner.py         # Per-repo pipeline: engineer -> review -> PR -> CI
│   ├── pr.py                  # PR template detection, CI status helpers
│   └── status.py              # Status tracking for dashboard
├── .opencode/agents/           # Agent definitions
│   ├── product-manager.md
│   ├── reviewer.md
│   ├── designer.md
│   ├── architect.md
│   ├── code-reviewer.md
│   └── pr-creator.md
├── repos/                      # Cloned repositories (gitignored)
└── specs/                      # Feature specs and worktrees
    └── <slug>/
        ├── input.md            # Raw issue or prompt
        ├── triage.json         # Triage classification
        ├── prd.md              # Product requirements
        ├── design.md           # Design proposals (if applicable)
        ├── tech-spec.md        # Overall technical spec
        ├── <repo>-spec.md      # Per-repo implementation specs
        ├── <repo>-review.md    # Per-repo code reviews
        ├── cross-review.md     # Cross-repo consistency review
        ├── <repo>-ci-failures.md  # CI failure logs (when fixes needed)
        ├── status.json         # Phase progress (read by dashboard)
        ├── repos/              # Git worktrees (gitignored)
        └── logs/               # Agent output logs (gitignored)
```

## Dashboard

Monitor all active features from a browser:

```sh
uv run dashboard.py              # http://localhost:8080
uv run dashboard.py --port 9090  # custom port
```

The dashboard auto-refreshes every 5 seconds and shows:
- Phase progress bar per feature (color coded: green=done, blue=running, gray=pending)
- Per-repo status within the active phase
- Active tmux sessions
- PR links and CI status

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

To re-run only the headless phases (e.g. after editing a spec manually):

```sh
uv run orchestrate.py --resume add-batch-api --skip-to engineer
```

File locking on `repos/` ensures parallel orchestrators don't corrupt shared git state during clone or worktree creation.

## Resumability

Every phase writes its output to `specs/<slug>/`. If a phase's output already exists, it is skipped on re-run. Use `--resume <slug>` to pick up where you left off.

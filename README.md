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
```

## How it works

The orchestrator triages the input and routes it through one of three paths:

```
                         ┌─ simple-bug ──────────────────────────────┐
                         │                                           │
Input ─> Triage ─────────┼─ complex-bug ──> Architect (light) ──────┤
                         │                                           │
                         └─ feature ──> PM ──> Debate ──> Designer? ─┤
                                                    ──> Architect    │
                                                                     v
                                                              Workspace setup
                                                              (clone + worktrees)
                                                                     │
                                                                     v
                                                              Engineers (tmux)
                                                                     │
                                                                     v
                                                              Code review loop
                                                              (max 2 rounds)
```

### Phases

| Phase | Mode | What happens |
|-------|------|-------------|
| **Intake + Triage** | Headless | Fetches the issue via `gh`, classifies as simple-bug / complex-bug / feature. You confirm or override. |
| **Product Manager** | Interactive TUI | Creates a PRD. Asks you clarifying questions if needed. |
| **Debate** | Interactive TUI | A reviewer agent critiques the PRD. You participate until satisfied. |
| **Designer** | Interactive TUI (conditional) | Creates UX/DX proposals if the feature has user-facing impact. Skipped for pure technical changes. |
| **Architect** | Interactive TUI | Creates a tech spec with shared interface contracts and per-repo implementation specs. |
| **Workspace** | Automated | Clones missing repos into `repos/`, creates git worktrees via `wt` into `specs/<slug>/repos/`. |
| **Engineers** | Parallel tmux panes | One `opencode run` per repo. Each sees only its own code and spec. |
| **Code Review** | Parallel tmux panes | Per-repo review, then cross-repo consistency check. Auto-loops back to engineers if issues are found (max 2 rounds). |

### Context isolation

Each engineer agent runs in its own worktree directory with only its per-repo spec. It never sees other repos' code or specs. The architect's shared interface contract is copied into each per-repo spec so engineers can build independently without a massive shared context window.

## Project structure

```
any-llm-world/
├── orchestrate.py              # CLI entry point
├── lib/
│   ├── config.py               # Repo registry, paths, ecosystem context
│   ├── intake.py               # Issue fetching, triage classifier
│   ├── prd.py                  # PM, debate, designer phases
│   ├── architect.py            # Tech spec generation
│   ├── workspace.py            # Repo cloning, worktree creation
│   └── engineer.py             # Tmux orchestration, review loop
├── .opencode/agents/           # Agent definitions
│   ├── product-manager.md
│   ├── reviewer.md
│   ├── designer.md
│   ├── architect.md
│   └── code-reviewer.md
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
        ├── repos/              # Git worktrees (gitignored)
        └── logs/               # Agent output logs (gitignored)
```

## Resumability

Every phase writes its output to `specs/<slug>/`. If a phase's output already exists, it is skipped on re-run. Use `--resume <slug>` to pick up where you left off.

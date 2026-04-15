"""Repository registry and path configuration for the any-llm ecosystem."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RepoInfo:
    """Metadata for a single repository in the ecosystem."""

    name: str
    github_url: str
    language: str
    description: str
    default_branch: str = "main"
    scope_notes: str = ""
    test_hints: str = ""

    @property
    def github_slug(self) -> str:
        """Return 'org/repo' from the full URL."""
        return "/".join(self.github_url.rstrip("/").split("/")[-2:])


# ── Repository registry ──────────────────────────────────────────────

REPOS: tuple[RepoInfo, ...] = (
    RepoInfo(
        name="any-llm",
        github_url="https://github.com/mozilla-ai/any-llm",
        language="python",
        description=(
            "Python SDK providing a common interface for LLM calls. "
            "Supports direct provider calls and gateway communication."
        ),
        scope_notes=(
            "This repo contains a gateway provider (client code for talking "
            "to the gateway). That provider code IS in scope. However, the "
            "gateway server code has moved to the standalone 'gateway' "
            "repository -- do NOT add or modify gateway server code in this "
            "repo. Only the gateway provider/client code lives here."
        ),
        test_hints=(
            "Run ONLY the tests related to your changes first: "
            "uv run pytest tests/unit/<relevant_file> -x -q. "
            "The full test suite is slow. Run it once at the end: "
            "uv run pytest tests/unit -x -q --timeout=60. "
            "Do NOT run integration tests. "
            "For linting use: uv run ruff check . && uv run mypy."
        ),
    ),
    RepoInfo(
        name="gateway",
        github_url="https://github.com/mozilla-ai/gateway",
        language="python",
        description=(
            "LLM gateway service. Routes requests through the any-llm SDK "
            "to various LLM providers. Captures observability data."
        ),
        test_hints=(
            "Run targeted tests first: uv run pytest tests/<relevant_file> -x -q. "
            "Full suite: uv run pytest -x -q --timeout=60. "
            "For linting: uv run ruff check . && uv run mypy."
        ),
    ),
    RepoInfo(
        name="any-llm-rust",
        github_url="https://github.com/mozilla-ai/any-llm-rust",
        language="rust",
        description="Rust SDK for communicating with the any-llm gateway.",
        test_hints=(
            "Run: cargo test --all-features. "
            "Lint: cargo clippy --all-features -- -D warnings && cargo fmt --check."
        ),
    ),
    RepoInfo(
        name="any-llm-go",
        github_url="https://github.com/mozilla-ai/any-llm-go",
        language="go",
        description="Go SDK for communicating with the any-llm gateway.",
        test_hints=("Run: go test ./... -race -count=1. Lint: golangci-lint run."),
    ),
    RepoInfo(
        name="any-llm-ts",
        github_url="https://github.com/mozilla-ai/any-llm-ts",
        language="typescript",
        description="TypeScript SDK for communicating with the any-llm gateway.",
        test_hints=(
            "Run: npm test (or the test script in package.json). "
            "Lint: npx biome check . or the lint script in package.json."
        ),
    ),
    RepoInfo(
        name="any-llm-platform",
        github_url="https://github.com/mozilla-ai/any-llm-platform",
        language="python",
        description=(
            "Managed platform for budgets, users, and observability. "
            "Pulls observability data from the gateway."
        ),
        default_branch="develop",
        test_hints=(
            "Run targeted tests first: uv run pytest tests/<relevant_file> -x -q. "
            "Full suite: uv run pytest -x -q --timeout=60. "
            "For linting: uv run ruff check . && uv run mypy."
        ),
    ),
)

REPO_BY_NAME: dict[str, RepoInfo] = {r.name: r for r in REPOS}

# ── Ecosystem context (shared with all agents) ───────────────────────

ECOSYSTEM_CONTEXT = """\
# any-llm Ecosystem

## Repositories and relationships

| Repo | Language | Role |
|------|----------|------|
| any-llm | Python | Core SDK -- common interface for LLM calls, supports direct provider calls AND gateway communication |
| gateway | Python | Gateway service -- routes LLM requests via the any-llm SDK, captures observability data |
| any-llm-rust | Rust | Rust SDK -- talks to the gateway |
| any-llm-go | Go | Go SDK -- talks to the gateway |
| any-llm-ts | TypeScript | TypeScript SDK -- talks to the gateway |
| any-llm-platform | Python | Managed platform -- budgets, users, observability; pulls data from the gateway |

## Dependency graph

```
any-llm-platform --> gateway --> any-llm (Python SDK)
any-llm-rust -----> gateway
any-llm-go -------> gateway
any-llm-ts -------> gateway
any-llm (Python) -> providers (OpenAI, Anthropic, etc.) directly OR via gateway
```

## Key facts
- The Python SDK (any-llm) is the most capable: it talks to providers directly AND through the gateway.
- The Rust, Go, and TypeScript SDKs primarily talk to the gateway.
- The gateway uses the Python SDK internally to reach LLM providers.
- The platform sits on top and manages budgets/users/observability by querying the gateway.
- Changes to the gateway API surface affect ALL SDKs.
- Changes to the Python SDK can affect the gateway (which imports it).
"""

# ── Pipeline tunables ─────────────────────────────────────────────────
# All values can be overridden via environment variables.


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key, "")
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return default


MAX_REVIEW_ROUNDS: int = _env_int("ORCHESTRATOR_MAX_REVIEW_ROUNDS", 2)
"""Maximum engineer -> review -> fix cycles before proceeding to PR."""

MAX_CI_FIX_ROUNDS: int = _env_int("ORCHESTRATOR_MAX_CI_FIX_ROUNDS", 2)
"""Maximum CI failure -> fix -> re-push cycles."""

CI_POLL_INTERVAL: int = _env_int("ORCHESTRATOR_CI_POLL_INTERVAL", 30)
"""Seconds between CI status polls."""

CLASSIFIER_TIMEOUT: int = _env_int("ORCHESTRATOR_CLASSIFIER_TIMEOUT", 120)
"""Seconds before a headless classifier call is considered timed out."""


# ── Caveman prompt (token-saving mode for headless agents) ────────────

CAVEMAN_PROMPT = (
    "Terse like caveman. Technical substance exact. Only fluff die. "
    "Drop: articles, filler (just/really/basically), pleasantries, hedging. "
    "Fragments OK. Short synonyms. Code unchanged. "
    "Pattern: [thing] [action] [reason]. [next step]. "
    "ACTIVE EVERY RESPONSE. No revert after many turns. No filler drift. "
    "Code/commits/PRs: write normal. "
    "NEVER create an AGENTS.md file in the repository unless explicitly "
    "asked to do so. "
)


# ── Path helpers ──────────────────────────────────────────────────────


@dataclass
class ProjectPaths:
    """All paths derived from the project root."""

    root: Path

    @property
    def repos_dir(self) -> Path:
        return self.root / "repos"

    @property
    def specs_dir(self) -> Path:
        return self.root / "specs"

    @property
    def agents_dir(self) -> Path:
        return self.root / ".opencode" / "agents"

    def repo_path(self, repo_name: str) -> Path:
        return self.repos_dir / repo_name

    def spec_dir(self, slug: str) -> Path:
        return self.specs_dir / slug

    def spec_file(self, slug: str, filename: str) -> Path:
        return self.spec_dir(slug) / filename

    def worktree_dir(self, slug: str) -> Path:
        return self.spec_dir(slug) / "repos"

    def worktree_path(self, slug: str, repo_name: str) -> Path:
        return self.worktree_dir(slug) / repo_name

    def logs_dir(self, slug: str) -> Path:
        return self.spec_dir(slug) / "logs"

    def ensure_spec_dirs(self, slug: str) -> None:
        """Create the full directory tree for a spec."""
        self.spec_dir(slug).mkdir(parents=True, exist_ok=True)
        self.worktree_dir(slug).mkdir(parents=True, exist_ok=True)
        self.logs_dir(slug).mkdir(parents=True, exist_ok=True)


def get_project_paths() -> ProjectPaths:
    """Return paths rooted at the directory containing this project."""
    root = Path(__file__).resolve().parent.parent
    return ProjectPaths(root=root)

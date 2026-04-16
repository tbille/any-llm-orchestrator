# Cross-Repo Review: rename-auth-header-anyllm-key

## Interface Alignment

All 5 repositories consistently rename the HTTP authentication header:

| Repo | Constant/Variable | New Value | Consistent |
|------|------------------|-----------|------------|
| any-llm (provider) | `GATEWAY_HEADER_NAME` | `"AnyLLM-Key"` | Yes |
| any-llm (gateway server) | `API_KEY_HEADER` | `"AnyLLM-Key"` | Yes |
| any-llm-rust | `GATEWAY_HEADER_NAME` | `"AnyLLM-Key"` | Yes |
| any-llm-go | `apiKeyHeaderName` | `"AnyLLM-Key"` | Yes |
| any-llm-ts | `GATEWAY_HEADER_NAME` | `"AnyLLM-Key"` | Yes |
| any-llm-platform | (docs only) | `AnyLLM-Key` | Yes |

The wire-level contract is aligned: all SDKs send `AnyLLM-Key: Bearer <token>` in non-platform mode. The `Authorization: Bearer <token>` fallback remains untouched across all repos. No type mismatches or version incompatibilities exist.

## Per-Repo Findings

### any-llm — Clean

The 13-file diff covers exactly the spec scope: 2 constant renames, 4 docstring updates, CORS config update (including `x-api-key` removal), 3 test file updates, and 6 documentation files. No out-of-scope changes. The per-repo review correctly identifies PASS.

**Build failure note**: The pre-review build check failed due to a worktree virtual environment mismatch (`ModuleNotFoundError: No module named 'uvicorn'`). This is an orchestrator environment issue, not a code defect. The per-repo review confirmed tests pass in the repo's own environment.

### any-llm-rust — Clean

Minimal 2-file diff: constant rename, 2 doc comment updates, test function rename, and wiremock header matcher update. Exactly matches the spec. No issues.

### any-llm-go — Clean

Minimal 2-file diff: constant rename, 2 doc comment updates, 1 test comment update. All test assertions use the constant by reference so they automatically validate the new value. No issues.

### any-llm-ts — Out-of-scope changes (Minor)

The diff includes 8 files but only 4 are spec-related (`src/client.ts`, `src/types.ts`, `tests/unit/client.test.ts`, `README.md`). The additional files are:

- **`AGENTS.md`** (new file, 131 lines): Orchestrator-injected spec file. Should be removed before merge or added to `.gitignore`. This is a known orchestrator artifact.
- **`.github/workflows/ci.yml`**: Modified (2 lines changed). Not part of the spec.
- **`package.json`** and **`package-lock.json`**: Dependency changes (package.json 2 lines, package-lock.json 117 lines). Not part of the spec.

**CI failure**: The Node 18 test matrix fails with `SyntaxError: The requested module 'node:util' does not provide an export named 'styleText'`. This is caused by the vitest/rolldown dependency upgrade in `package-lock.json` — `styleText` was added in Node 21.7.0/22.0.0 and is not available in Node 18. This is **not related to the header rename** but was introduced by the out-of-scope dependency changes. The Node 20+ matrix likely passes.

**Recommendation**: Revert the `package.json`, `package-lock.json`, and `.github/workflows/ci.yml` changes, and remove the `AGENTS.md` file. The header rename changes themselves are correct.

### any-llm-platform — Significant out-of-scope changes (Major)

The diff shows **56 files changed** but only **6 files** are spec-related (the gateway documentation markdown files under `frontend/src/content/imported-docs/gateway/`). The remaining ~50 files are backend test modifications:

- **`AGENTS.md`** (new file, 102 lines): Orchestrator-injected spec file. Should be removed before merge.
- **~46 backend test files**: Widespread changes including blank line removals, unused import removals (`from sqlmodel import Session`), test logic modifications in `test_login_extended.py`, `test_managed_models_pricing.py`, `test_organization_service.py`, `test_wallet_service_extended.py`, `test_webauthn_service.py`, `test_otel_trace_repository.py`, `test_model_pricing_service.py`, `test_playground_service.py`, and others.
- **`backend/tests/conftest.py`**: Modified (3 lines changed).

These backend test changes are completely unrelated to the documentation-only header rename spec. The per-repo review only verified the 6 markdown files and gave a PASS, which is correct for the spec-scoped changes. However, the unrelated changes risk introducing regressions in backend tests.

**CI failure**: The `check-has-label` CI job fails because the PR has no labels. This is a process issue, not a code defect.

**Recommendation**: The out-of-scope backend test changes should be reverted from this PR. They appear to be linting/cleanup changes the engineer made opportunistically. The 6 markdown file changes are correct and match the spec. The `AGENTS.md` file should also be removed.

## Integration Assessment

The header rename itself is fully consistent across all repos. All SDKs will send `AnyLLM-Key: Bearer <token>` and the gateway server code (in both the standalone gateway repo and the legacy code in `any-llm`) expects this header. No integration gaps exist for the core change.

The repos can be merged in any order since there are no cross-repo runtime dependencies for this change and the gateway has no live deployments.

## Summary

| Repo | Spec Changes | Out-of-Scope Changes | Verdict |
|------|-------------|---------------------|---------|
| any-llm | Correct | None | Ready |
| any-llm-rust | Correct | None | Ready |
| any-llm-go | Correct | None | Ready |
| any-llm-ts | Correct | CI config, deps, AGENTS.md | Needs cleanup |
| any-llm-platform | Correct | ~50 backend test files, AGENTS.md | Needs cleanup |

## Actionable Findings

### any-llm-ts
1. **Remove `AGENTS.md`** from the branch before merge.
2. **Revert `package.json` and `package-lock.json`** dependency changes — they break Node 18 CI and are unrelated to the header rename.
3. **Revert `.github/workflows/ci.yml`** changes if unrelated to the header rename.

### any-llm-platform
1. **Remove `AGENTS.md`** from the branch before merge.
2. **Revert all backend test file changes** (~50 files) — they are unrelated to the documentation-only header rename spec and risk introducing test regressions.

```json
{"affected_repos": ["any-llm-ts", "any-llm-platform"]}
```

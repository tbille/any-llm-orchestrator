# Tech Spec: Rename Auth Header from X-AnyLLM-Key to AnyLLM-Key

## Architecture Overview

The gateway (mozilla-ai/gateway) has renamed its authentication header from `X-AnyLLM-Key` to `AnyLLM-Key` to comply with RFC 6648 (deprecation of the `X-` prefix for custom HTTP headers). This change was merged in [gateway PR #45](https://github.com/mozilla-ai/gateway/pull/45).

Since the gateway is not yet live in production, there is **no backward-compatibility requirement**. This is a simple rename across all SDK clients and documentation that reference the old header name.

The change affects every SDK that acts as a gateway client. Each SDK has a constant or literal string `"X-AnyLLM-Key"` that needs to become `"AnyLLM-Key"`. The gateway server code that still lives in the `any-llm` repo (under `src/any_llm/gateway/`) also needs updating to match the standalone gateway repo.

### What does NOT change

- The `Authorization: Bearer <token>` header (standard HTTP auth) is unaffected.
- Platform mode authentication (which uses `Authorization`) is unaffected.
- The `x-api-key` Anthropic-compat fallback has been removed from the gateway; SDKs never sent this header anyway.

## Shared Interface Contracts

### HTTP Header Name

| Before | After |
|--------|-------|
| `X-AnyLLM-Key` | `AnyLLM-Key` |

The header value format remains unchanged: `Bearer <token>`.

### Constant Name Convention (per-repo)

Each repo defines a constant for this header name. The constant name stays the same; only its value changes:

| Repo | Constant | Location | Old Value | New Value |
|------|----------|----------|-----------|-----------|
| any-llm (provider) | `GATEWAY_HEADER_NAME` | `src/any_llm/providers/gateway/gateway.py` | `"X-AnyLLM-Key"` | `"AnyLLM-Key"` |
| any-llm (gateway server) | `API_KEY_HEADER` | `src/any_llm/gateway/core/config.py` | `"X-AnyLLM-Key"` | `"AnyLLM-Key"` |
| any-llm-rust | `GATEWAY_HEADER_NAME` | `src/providers/gateway/mod.rs` | `"X-AnyLLM-Key"` | `"AnyLLM-Key"` |
| any-llm-go | `apiKeyHeaderName` | `providers/gateway/gateway.go` | `"X-AnyLLM-Key"` | `"AnyLLM-Key"` |
| any-llm-ts | `GATEWAY_HEADER_NAME` | `src/client.ts` | `"X-AnyLLM-Key"` | `"AnyLLM-Key"` |

### Wire-level Contract

All SDKs sending requests to the gateway in non-platform mode MUST send:

```
AnyLLM-Key: Bearer <api-key>
```

The gateway accepts this header with highest priority, then falls back to `Authorization: Bearer <token>`.

## Implementation Order

All repos can be updated **in parallel** since:
1. The gateway PR #45 is already merged.
2. There are no live deployments, so no coordination window is needed.
3. Each SDK is a client of the gateway; they do not depend on each other.

Recommended order (for logical clarity, not strict dependency):

1. **any-llm** (Python SDK + gateway server code) - This is the reference implementation.
2. **any-llm-rust**, **any-llm-go**, **any-llm-ts** - SDK clients, can be done in parallel with each other and with step 1.
3. **any-llm-platform** - Documentation-only changes, can land any time.

## Per-repo Summary

| Repo | Changes needed | Complexity | Dependencies |
|------|---------------|------------|--------------|
| any-llm | Rename constant value in gateway provider client and gateway server code; update CORS config; update all docs and tests referencing `X-AnyLLM-Key` | Low | gateway PR #45 (already merged) |
| any-llm-rust | Rename constant value in gateway provider; update doc comments and tests | Low | gateway PR #45 (already merged) |
| any-llm-go | Rename constant value in gateway provider; update doc comments and test comments | Low | gateway PR #45 (already merged) |
| any-llm-ts | Rename constant value in client; update doc comments, types, README, and tests | Low | gateway PR #45 (already merged) |
| any-llm-platform | Update imported gateway documentation (markdown files) | Low | gateway PR #45 (already merged) |

## Migration Strategy

No migration is needed. The gateway has no live deployments, and the PR description explicitly states: "No need for backward compatibility."

All changes are a simple string rename from `X-AnyLLM-Key` to `AnyLLM-Key`. No API signatures, function names, environment variables, or configuration keys change.

## Testing Strategy

Each repo should:

1. **Run existing tests after the rename** to verify nothing breaks. Tests that hardcode the header string need updating first.
2. **Verify the constant value** in unit tests (most repos already do this via header-assertion tests).
3. **No new integration tests** are needed since this is a rename of a constant, not a behavioral change.

### Per-repo test commands

| Repo | Test command | Specific test files to verify |
|------|-------------|------------------------------|
| any-llm | `uv run pytest tests/unit/providers/test_gateway_provider.py tests/gateway/ -v` | `test_gateway_provider.py`, `test_provider_kwargs_override.py`, `test_client_args.py`, `test_key_management.py` |
| any-llm-rust | `cargo test --all-features` | `tests/test_gateway.rs` |
| any-llm-go | `make test` (or `go test ./providers/gateway/ -v -count=1`) | `providers/gateway/gateway_test.go` |
| any-llm-ts | `npm test` | `tests/unit/client.test.ts` |
| any-llm-platform | No code tests needed (docs-only change) | N/A |

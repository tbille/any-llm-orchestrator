# Implementation Spec: any-llm-go

## Context

The gateway (standalone repo) renamed its authentication header from `X-AnyLLM-Key` to `AnyLLM-Key` (RFC 6648 compliance, no `X-` prefix) in [gateway PR #45](https://github.com/mozilla-ai/gateway/pull/45). The Go SDK contains a gateway provider (`providers/gateway/`) that sends this header when authenticating in non-platform mode. The constant and all references to the old header name need to be updated.

No backward compatibility is required since the gateway is not yet live.

## Shared Interface Contract

### HTTP Header Name

| Before | After |
|--------|-------|
| `X-AnyLLM-Key` | `AnyLLM-Key` |

The header value format remains: `Bearer <token>`.

All SDKs sending requests to the gateway in non-platform mode MUST send:
```
AnyLLM-Key: Bearer <api-key>
```

The gateway accepts this header with highest priority, then falls back to `Authorization: Bearer <token>`.

## Changes Required

### 1. Gateway Provider Source

**File: `providers/gateway/gateway.go`**

- **Line 12**: Update package doc comment from `"header (X-AnyLLM-Key)"` to `"header (AnyLLM-Key)"`
- **Line 34**: Change `apiKeyHeaderName = "X-AnyLLM-Key"` to `apiKeyHeaderName = "AnyLLM-Key"`
- **Line 253**: Update doc comment on `WithGatewayKey` from `"header (X-AnyLLM-Key)"` to `"header (AnyLLM-Key)"`

No other source changes needed. The constant `apiKeyHeaderName` is used by reference throughout (lines 208, 393), so all usages automatically pick up the new value.

### 2. Tests

**File: `providers/gateway/gateway_test.go`**

- **Line 278**: Update test struct field comment from `"expected X-AnyLLM-Key value"` to `"expected AnyLLM-Key value"`

No other test changes needed. All test assertions use the `apiKeyHeaderName` constant by reference (lines 186, 374, 392, 394, 444, 456, 491, 527), so they automatically validate the new header name after the constant changes.

## Implementation Steps

1. **Update the constant in gateway provider:**
   - Open `providers/gateway/gateway.go`
   - Change line 34: `apiKeyHeaderName = "AnyLLM-Key"`
   - Update the two doc comments on lines 12 and 253

2. **Update the test comment:**
   - Open `providers/gateway/gateway_test.go`
   - Update the struct field comment on line 278

3. **Build and test:**
   ```bash
   make build
   make test
   ```

## Testing Requirements

### Existing Tests (pass after constant rename, no code changes needed)

**File: `providers/gateway/gateway_test.go`**

The test suite is comprehensive and uses the `apiKeyHeaderName` constant by reference throughout. Key tests that validate the header:

- `TestNew/"forwards custom HTTP client transport in non-platform mode"` (line 160): Captures actual HTTP headers from a test server and asserts `capturedHeaders.Get(apiKeyHeaderName)` equals `bearerPrefix + "gw_key"`.
- `TestExtraValueHandling` (line 268): Table-driven test with multiple scenarios asserting `capturedHeaders.Get(apiKeyHeaderName)` matches expected values for gateway key forwarding, silent ignoring of wrong types, env var fallback, and platform mode suppression.
- `TestHeaderTransport` (line 380): Directly tests the `headerTransport` round-tripper injects `apiKeyHeaderName` and does not mutate the original request.
- `TestNonPlatformModeSendsCustomHeader` (line 460): End-to-end test creating a provider with `WithGatewayKey`, making a completion call, and asserting the captured header value.
- `TestPlatformModeSendsBearerAuth` (line 494): Asserts that `apiKeyHeaderName` header is **empty** in platform mode (negative test).

All of these tests reference `apiKeyHeaderName` as a Go constant, not as a hardcoded string, so they will automatically assert against `"AnyLLM-Key"` after the constant is updated.

### Test Commands

```bash
# Run the directly impacted gateway provider tests
go test ./providers/gateway/ -v -count=1

# Run the full test suite (includes lint)
make test

# Run tests without lint
make test-only

# Run lint separately
make lint

# Verify compilation
make build
```

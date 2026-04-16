# Implementation Spec: any-llm-rust

## Context

The gateway (standalone repo) renamed its authentication header from `X-AnyLLM-Key` to `AnyLLM-Key` (RFC 6648 compliance, no `X-` prefix) in [gateway PR #45](https://github.com/mozilla-ai/gateway/pull/45). The Rust SDK contains a gateway provider that sends this header when authenticating in non-platform mode. The constant and all references to the old header name need to be updated.

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

**File: `src/providers/gateway/mod.rs`**

- **Line 12**: Update doc comment from `` `X-AnyLLM-Key: Bearer <key>` `` to `` `AnyLLM-Key: Bearer <key>` ``
- **Line 29**: Change `const GATEWAY_HEADER_NAME: &str = "X-AnyLLM-Key";` to `const GATEWAY_HEADER_NAME: &str = "AnyLLM-Key";`
- **Line 157**: Update doc comment from `"non-platform mode with optional X-AnyLLM-Key header"` to `"non-platform mode with optional AnyLLM-Key header"`

No other source changes needed. The constant `GATEWAY_HEADER_NAME` is used by reference on line 209 in the `resolve_auth` function, so its usage automatically picks up the new value.

### 2. Tests

**File: `tests/test_gateway.rs`**

- **Line 157**: Rename test function from `non_platform_mode_sends_x_anyllm_key_header` to `non_platform_mode_sends_anyllm_key_header`
- **Line 162**: Change `.and(header("X-AnyLLM-Key", "Bearer my-api-key"))` to `.and(header("AnyLLM-Key", "Bearer my-api-key"))`

## Implementation Steps

1. **Update the constant in gateway provider:**
   - Open `src/providers/gateway/mod.rs`
   - Change line 29: `const GATEWAY_HEADER_NAME: &str = "AnyLLM-Key";`
   - Update the two doc comments on lines 12 and 157

2. **Update the test:**
   - Open `tests/test_gateway.rs`
   - Rename the test function (line 157) and update the header matcher (line 162)

3. **Build and test:**
   ```bash
   cargo build --all-features
   cargo test --all-features
   cargo clippy --all-features -- -D warnings
   cargo fmt --check
   ```

## Testing Requirements

### Existing Test (needs header string update)

**File: `tests/test_gateway.rs`**

The test `non_platform_mode_sends_x_anyllm_key_header` (renamed to `non_platform_mode_sends_anyllm_key_header`) uses `wiremock` to assert the exact header name and value sent by the gateway provider:

```rust
Mock::given(method("POST"))
    .and(path("/v1/chat/completions"))
    .and(header("AnyLLM-Key", "Bearer my-api-key"))  // updated
    .respond_with(ResponseTemplate::new(200).set_body_json(chat_completion_json()))
    .expect(1)
    .mount(&server)
    .await;
```

This test verifies the gateway provider sends the correct header when an API key is provided (non-platform mode). After the update, it confirms `AnyLLM-Key` is used.

### Test Commands

```bash
# Run the directly impacted gateway tests
cargo test test_gateway --all-features -- --nocapture

# Run the full test suite
cargo test --all-features

# Run linting
cargo fmt --check && cargo clippy --all-features -- -D warnings
```

# Implementation Spec: any-llm

## Context

The gateway (standalone repo) renamed its authentication header from `X-AnyLLM-Key` to `AnyLLM-Key` (RFC 6648 compliance, no `X-` prefix) in [gateway PR #45](https://github.com/mozilla-ai/gateway/pull/45). The `any-llm` repo contains two areas that reference the old header name:

1. **Gateway provider client** (`src/any_llm/providers/gateway/gateway.py`): The SDK's client-side code for talking to the gateway. This is in scope.
2. **Gateway server code** (`src/any_llm/gateway/`): The legacy gateway server code that still lives in this repo. This also needs updating to stay consistent.
3. **Documentation** (`docs/`): Gateway docs reference the old header in curl examples and descriptions.
4. **Tests**: Both unit and gateway integration tests use the old header name.

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

### 1. Gateway Provider Client (SDK)

**File: `src/any_llm/providers/gateway/gateway.py`**

- Change `GATEWAY_HEADER_NAME = "X-AnyLLM-Key"` to `GATEWAY_HEADER_NAME = "AnyLLM-Key"` (line 9)

No other changes needed in this file. The constant is used throughout by reference, so the rename propagates automatically.

### 2. Gateway Server Code

**File: `src/any_llm/gateway/core/config.py`**

- Change `API_KEY_HEADER = "X-AnyLLM-Key"` to `API_KEY_HEADER = "AnyLLM-Key"` (line 10)

**File: `src/any_llm/gateway/api/deps.py`**

- Update docstring on `_extract_bearer_token` (line 41): change `"Checks X-AnyLLM-Key first"` to `"Checks AnyLLM-Key first"`
- Update docstring on `verify_api_key` (line 121): change `"Verify API key from X-AnyLLM-Key header"` to `"Verify API key from AnyLLM-Key header"`
- Update docstring on `verify_master_key` (line 143): change `"Verify master key from X-AnyLLM-Key header"` to `"Verify master key from AnyLLM-Key header"`
- Update docstring on `verify_api_key_or_master_key` (line 173): change `"Verify either API key or master key from X-AnyLLM-Key header"` to `"Verify either API key or master key from AnyLLM-Key header"`

**File: `src/any_llm/gateway/main.py`**

- Change CORS `allow_headers` (line 166): replace `"X-AnyLLM-Key"` with `"AnyLLM-Key"` in the list
- Also remove `"x-api-key"` from the CORS `allow_headers` list (the x-api-key fallback was removed in gateway PR #45)

### 3. Tests

**File: `tests/unit/providers/test_gateway_provider.py`**

- No code changes needed. This file imports `GATEWAY_HEADER_NAME` from the provider module and uses the constant by reference. Once the constant value changes, all assertions will automatically check for the new value.

**File: `tests/gateway/test_provider_kwargs_override.py`**

- Line 99: Change `{"X-AnyLLM-Key": "Bearer test-master-key"}` to `{"AnyLLM-Key": "Bearer test-master-key"}`
- Line 135: Change `{"X-AnyLLM-Key": "Bearer test-master-key"}` to `{"AnyLLM-Key": "Bearer test-master-key"}`

**File: `tests/gateway/test_client_args.py`**

- Line 84: Change `{"X-AnyLLM-Key": "Bearer test-master-key"}` to `{"AnyLLM-Key": "Bearer test-master-key"}`

**File: `tests/gateway/test_key_management.py`**

- Line 251: Update comment from `"Use Authorization header instead of X-AnyLLM-Key"` to `"Use Authorization header instead of AnyLLM-Key"`
- Note: This file imports `API_KEY_HEADER` from `any_llm.gateway.core.config` and uses it via the constant reference (e.g., line 244: `headers={API_KEY_HEADER: f"Bearer {api_key['key']}"}`), so those usages update automatically.

### 4. Documentation

**File: `docs/src/content/docs/gateway/authentication.md`**

Replace all occurrences of `X-AnyLLM-Key` with `AnyLLM-Key`. This affects:
- Lines 19, 22: Header description text
- Lines 67, 76, 95, 114, 142, 155, 168, 174, 182: curl examples using `-H "X-AnyLLM-Key: Bearer ..."`

**File: `docs/src/content/docs/gateway/overview.md`**

- Line 31: Change `-H "X-AnyLLM-Key: Bearer your-secure-master-key"` to `-H "AnyLLM-Key: Bearer your-secure-master-key"`

**File: `docs/src/content/docs/gateway/quickstart.md`**

- Lines 157, 187, 266: Change `-H "X-AnyLLM-Key: Bearer ${GATEWAY_MASTER_KEY}"` to `-H "AnyLLM-Key: Bearer ${GATEWAY_MASTER_KEY}"`

**File: `docs/src/content/docs/gateway/configuration.md`**

- Line 90: Change `-H "X-AnyLLM-Key: Bearer ${GATEWAY_MASTER_KEY}"` to `-H "AnyLLM-Key: Bearer ${GATEWAY_MASTER_KEY}"`

**File: `docs/src/content/docs/gateway/budget-management.md`**

- Lines 13, 46, 56: Change `-H "X-AnyLLM-Key: Bearer ${GATEWAY_MASTER_KEY}"` to `-H "AnyLLM-Key: Bearer ${GATEWAY_MASTER_KEY}"`

**File: `docs/src/content/docs/gateway/troubleshooting.md`**

- Line 19: Change `X-AnyLLM-Key` to `AnyLLM-Key`

## Implementation Steps

1. **Update the two constant definitions:**
   - `src/any_llm/providers/gateway/gateway.py`: `GATEWAY_HEADER_NAME = "AnyLLM-Key"`
   - `src/any_llm/gateway/core/config.py`: `API_KEY_HEADER = "AnyLLM-Key"`

2. **Update gateway server code:**
   - `src/any_llm/gateway/api/deps.py`: Update four docstrings
   - `src/any_llm/gateway/main.py`: Update CORS `allow_headers` list (rename header and remove `x-api-key`)

3. **Update test files with hardcoded header strings:**
   - `tests/gateway/test_provider_kwargs_override.py` (2 occurrences)
   - `tests/gateway/test_client_args.py` (1 occurrence)
   - `tests/gateway/test_key_management.py` (1 comment)

4. **Update documentation:**
   - All `.md` files listed above (6 files, ~20 occurrences total)

5. **Run tests:**
   ```bash
   uv run pytest tests/unit/providers/test_gateway_provider.py -v
   uv run pytest tests/gateway/ -v
   ```

6. **Run linting and type checks:**
   ```bash
   uv run pre-commit run --all-files --verbose
   ```

## Testing Requirements

### Unit Tests (already exist, will pass after constant rename)

**File: `tests/unit/providers/test_gateway_provider.py`**

These tests import `GATEWAY_HEADER_NAME` and verify the header is set correctly on the OpenAI client. No test code changes needed; they will automatically validate the new value:

- `test_gateway_init_with_api_key`: Checks `call_kwargs["default_headers"][GATEWAY_HEADER_NAME] == "Bearer test-key"`
- `test_gateway_init_header_override_warning`: Checks override behavior with `GATEWAY_HEADER_NAME`
- `test_gateway_init_with_env_api_key`: Checks env var flow through `GATEWAY_HEADER_NAME`
- `test_gateway_init_without_any_api_key`: Checks `GATEWAY_HEADER_NAME` not present when no key
- `test_gateway_client_initialization_with_custom_headers`: Checks `GATEWAY_HEADER_NAME` alongside custom headers
- `test_gateway_passes_kwargs_to_parent`: Checks `GATEWAY_HEADER_NAME` alongside extra kwargs

### Gateway Integration Tests (need hardcoded string updates)

**File: `tests/gateway/test_provider_kwargs_override.py`**
**File: `tests/gateway/test_client_args.py`**
**File: `tests/gateway/test_key_management.py`**

These tests use hardcoded header strings in HTTP requests. After updating them to `"AnyLLM-Key"`, they verify the gateway server accepts the new header name.

### Test Commands

```bash
# Run the directly impacted tests
uv run pytest tests/unit/providers/test_gateway_provider.py -v
uv run pytest tests/gateway/test_provider_kwargs_override.py -v
uv run pytest tests/gateway/test_client_args.py -v
uv run pytest tests/gateway/test_key_management.py -v

# Full unit test suite
uv run pytest tests/unit -v

# Full gateway test suite
uv run pytest tests/gateway -v
```

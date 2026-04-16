# Implementation Spec: any-llm-platform

## Context

The gateway (standalone repo) renamed its authentication header from `X-AnyLLM-Key` to `AnyLLM-Key` (RFC 6648 compliance, no `X-` prefix) in [gateway PR #45](https://github.com/mozilla-ai/gateway/pull/45). The `any-llm-platform` repo contains imported documentation from the gateway that references the old header name in curl examples and descriptions. These are documentation-only changes; no application code is affected.

No backward compatibility is required since the gateway is not yet live.

## Shared Interface Contract

### HTTP Header Name

| Before | After |
|--------|-------|
| `X-AnyLLM-Key` | `AnyLLM-Key` |

The header value format remains: `Bearer <token>`.

## Changes Required

All changes are in `frontend/src/content/imported-docs/gateway/` markdown files. These are imported copies of the gateway documentation displayed on the platform frontend.

### 1. Authentication docs

**File: `frontend/src/content/imported-docs/gateway/authentication.md`**

Replace all occurrences of `X-AnyLLM-Key` with `AnyLLM-Key`. This affects:
- **Line 15**: `"**\`X-AnyLLM-Key\`** (preferred)"` becomes `"**\`AnyLLM-Key\`** (preferred)"`
- **Line 18**: `"X-AnyLLM-Key takes precedence"` becomes `"AnyLLM-Key takes precedence"`
- **Lines 63, 72, 91, 110, 138, 151, 163, 169, 177**: curl examples with `-H "X-AnyLLM-Key: Bearer ..."` become `-H "AnyLLM-Key: Bearer ..."`

### 2. Overview docs

**File: `frontend/src/content/imported-docs/gateway/overview.md`**

- **Line 28**: Change `-H "X-AnyLLM-Key: Bearer your-secure-master-key"` to `-H "AnyLLM-Key: Bearer your-secure-master-key"`

### 3. Troubleshooting docs

**File: `frontend/src/content/imported-docs/gateway/troubleshooting.md`**

- **Line 16**: Change `` `X-AnyLLM-Key` `` to `` `AnyLLM-Key` ``

### 4. Quickstart docs

**File: `frontend/src/content/imported-docs/gateway/quickstart.md`**

- **Lines 154, 184, 262**: Change `-H "X-AnyLLM-Key: Bearer ${GATEWAY_MASTER_KEY}"` to `-H "AnyLLM-Key: Bearer ${GATEWAY_MASTER_KEY}"`

### 5. Configuration docs

**File: `frontend/src/content/imported-docs/gateway/configuration.md`**

- **Line 87**: Change `-H "X-AnyLLM-Key: Bearer ${GATEWAY_MASTER_KEY}"` to `-H "AnyLLM-Key: Bearer ${GATEWAY_MASTER_KEY}"`

### 6. Budget management docs

**File: `frontend/src/content/imported-docs/gateway/budget-management.md`**

- **Lines 10, 41, 51**: Change `-H "X-AnyLLM-Key: Bearer ${GATEWAY_MASTER_KEY}"` to `-H "AnyLLM-Key: Bearer ${GATEWAY_MASTER_KEY}"`

## Implementation Steps

1. **Find-and-replace across all 6 markdown files:**
   - In `frontend/src/content/imported-docs/gateway/`, replace all literal occurrences of `X-AnyLLM-Key` with `AnyLLM-Key` (approximately 20 occurrences across 6 files).

2. **Verify the build (if applicable):**
   ```bash
   # If the platform has a build step for the frontend:
   cd frontend && npm run build
   ```

3. **Spot-check** rendered pages to confirm curl examples look correct.

## Testing Requirements

These are documentation-only changes. No unit or integration tests are affected.

If the platform frontend has a build step, run it to verify the markdown files are valid:

```bash
cd frontend && npm run build
```

No other test commands are necessary since no application logic is changed.

**Note:** The `any-llm-platform` repo uses the `develop` branch as its default branch, not `main`. Ensure the PR targets `develop`.

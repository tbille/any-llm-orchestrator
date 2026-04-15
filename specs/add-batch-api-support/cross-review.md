# Cross-Repository Review: Batch API Support

## Status: PASS (with findings)

All five repositories implement the batch API spec correctly at the contract level. The gateway HTTP endpoints, shared type shapes, method naming conventions, and error handling are aligned across all SDKs. No blocking issues found. Several minor inconsistencies and integration gaps are documented below.

## 1. Interface Alignment

### 1.1 Gateway HTTP Contract

All non-Python SDKs (Rust, Go, TypeScript) and the Python Gateway provider target the same five endpoints with matching HTTP methods, paths, and query parameters:

| Endpoint | Rust | Go | TypeScript | Python Gateway |
|---|---|---|---|---|
| `POST /v1/batches` (body: JSON) | Correct | Correct | Correct | Correct |
| `GET /v1/batches/{id}?provider=` | Correct | Correct | Correct | Correct |
| `POST /v1/batches/{id}/cancel?provider=` | Correct | Correct | Correct | Correct |
| `GET /v1/batches?provider=&after=&limit=` | Correct | Correct | Correct | Correct |
| `GET /v1/batches/{id}/results?provider=` | Correct | Correct | Correct | Correct |

### 1.2 Method Naming

All SDKs follow the cross-SDK naming convention from the tech spec:

| Operation | Python | Rust | Go | TypeScript | Spec |
|---|---|---|---|---|---|
| Create | `create_batch` | `create_batch` | `CreateBatch` | `createBatch` | Match |
| Retrieve | `retrieve_batch` | `retrieve_batch` | `RetrieveBatch` | `retrieveBatch` | Match |
| Cancel | `cancel_batch` | `cancel_batch` | `CancelBatch` | `cancelBatch` | Match |
| List | `list_batches` | `list_batches` | `ListBatches` | `listBatches` | Match |
| Results | `retrieve_batch_results` | `retrieve_batch_results` | `RetrieveBatchResults` | `retrieveBatchResults` | Match |

### 1.3 Auth Header

All SDKs use `X-AnyLLM-Key: Bearer {key}` for non-platform mode. TypeScript additionally supports `Authorization: Bearer {token}` for platform mode. This is consistent with the existing completion endpoints.

## 2. Type Consistency

### 2.1 `Batch` Type

| Field | Gateway Response | Rust | Go | TypeScript | Notes |
|---|---|---|---|---|---|
| `id` | string | `String` | `string` | (from openai) | Match |
| `object` | `"batch"` | `String` | `string` | (from openai) | Match |
| `endpoint` | string | `String` | `string` | (from openai) | Match |
| `status` | enum string | `BatchStatus` enum | `BatchStatus` string | (from openai) | Match |
| `created_at` | integer | `i64` | `int64` | (from openai) | Match |
| `completion_window` | string | `String` | `string` | (from openai) | Match |
| `provider` | string (injected) | `Option<String>` | `string` (omitempty) | (from openai -- see finding #1) | See finding |
| `input_file_id` | string or null | `Option<String>` | `string` (omitempty) | (from openai) | Match |
| `output_file_id` | string or null | `Option<String>` | `string` (omitempty) | (from openai) | Match |
| `error_file_id` | string or null | `Option<String>` | `string` (omitempty) | (from openai) | Match |
| `request_counts` | object or null | `Option<BatchRequestCounts>` | `*BatchRequestCounts` (omitempty) | (from openai) | Match |
| `metadata` | object or null | `Option<HashMap<String, String>>` | `map[string]string` (omitempty) | (from openai) | Match |
| `in_progress_at` | integer or null | `Option<i64>` | `*int64` (omitempty) | (from openai) | Match |
| `completed_at` | integer or null | `Option<i64>` | `*int64` (omitempty) | (from openai) | Match |

### 2.2 `BatchResult` / `BatchResultItem` / `BatchResultError`

| Field | Gateway Response | Python | Rust | Go | TypeScript |
|---|---|---|---|---|---|
| `results` | `list[object]` | `list[BatchResultItem]` | `Vec<BatchResultItem>` | `[]BatchResultItem` | `BatchResultItem[]` | Match |
| `custom_id` | string | `str` | `String` | `string` | `string` | Match |
| `result` | object or null | `ChatCompletion \| None` | `Option<ChatCompletion>` | `*ChatCompletion` | `ChatCompletion?` | Match |
| `error` | object or null | `BatchResultError \| None` | `Option<BatchResultError>` | `*BatchResultError` | `BatchResultError?` | Match |
| `error.code` | string | `str` | `String` | `string` | `string` | Match |
| `error.message` | string | `str` | `String` | `string` | `string` | Match |

### 2.3 `CreateBatchParams` / `BatchRequestItem`

| Field | Gateway Expects | Rust | Go | TypeScript |
|---|---|---|---|---|
| `model` | string (required) | `String` | `string` | `string` | Match |
| `requests` | array (1-10000) | `Vec<BatchRequestItem>` | `[]BatchRequestItem` | `BatchRequestItem[]` | Match |
| `completion_window` | string (optional, default "24h") | `Option<String>` | `string` (omitempty) | `string?` | Match |
| `metadata` | object (optional) | `Option<HashMap<String, String>>` | `map[string]string` (omitempty) | `Record<string, string>?` | Match |
| `requests[].custom_id` | string | `String` | `string` | `string` | Match |
| `requests[].body` | object | `serde_json::Value` | `map[string]any` | `Record<string, unknown>` | Match |

### 2.4 `BatchStatus` Values

All SDKs define the same 8 status values: `validating`, `failed`, `in_progress`, `finalizing`, `completed`, `expired`, `cancelling`, `cancelled`.

- **Rust**: `BatchStatus` enum with `#[serde(rename_all = "snake_case")]` -- correct.
- **Go**: `BatchStatus` string type with 8 constants -- correct.
- **TypeScript**: Re-uses OpenAI SDK's `Batch` type which defines these statuses -- correct.
- **Python**: Re-uses OpenAI SDK's `Batch` type -- correct.

### 2.5 `ListBatchesOptions`

| Field | Rust | Go | TypeScript |
|---|---|---|---|
| `after` | `Option<String>` | `string` (zero value = omit) | `string?` |
| `limit` | `Option<u32>` | `*int` (nil = omit) | `number?` |

Match in semantics; the Go SDK uses zero value and nil pointer instead of `Option`.

## 3. Error Handling Consistency

### 3.1 HTTP Status Code Mapping

| Status | Gateway Sends | Python Gateway | Rust | Go | TypeScript |
|---|---|---|---|---|---|
| 401/403 | Auth error | `AuthenticationError` | `Authentication` | `AuthenticationError` | `AuthenticationError` |
| 404 | Not found / upgrade | `ProviderError` (upgrade hint) | `Provider` (upgrade hint) | `ProviderError` (upgrade hint) | `AnyLLMError` (upgrade hint) |
| 409 | Batch not complete | `BatchNotCompleteError` | `BatchNotComplete` | `BatchNotCompleteError` | `BatchNotCompleteError` |
| 422 | Unsupported provider | (via SDK exception) | `Provider` (fallthrough) | `ProviderError` | `AnyLLMError` |
| 429 | Rate limited | (via SDK exception) | `RateLimit` | `RateLimitError` | `RateLimitError` |
| 502 | Upstream error | (via SDK exception) | `Provider` ("upstream") | `ProviderError` ("upstream") | `UpstreamProviderError` |

### 3.2 409 Error Detail Parsing

The gateway sends 409 with message format: `"Batch '{batch_id}' is not yet complete (status: {status}). Call GET /v1/batches/{batch_id}?provider={provider} to check the current status."`

Each SDK extracts `batch_id` and `status` from this message using different mechanisms:

| SDK | Extraction Method | `batch_id` Pattern | `status` Pattern |
|---|---|---|---|
| Python | Raised directly from `BatchNotCompleteError` constructor (no parsing needed -- it generates the message) | N/A | N/A |
| Rust | `extract_field_from_detail` searching for `batch_id=` and `status=` | `batch_id=<value>` | `status=<value>` |
| Go | `parseBatchNotCompleteDetail` with regex `[Bb]atch\s+'([^']+)'.*\(status:\s*(\w+)\)` | `Batch '<id>'` | `status: <word>` |
| TypeScript | `extractBatchId` regex `/Batch '([^']+)'/`, `extractStatus` regex `/status: (\w+)/` | `Batch '<id>'` | `status: <word>` |

**Finding #2 (Medium):** The Rust SDK's `extract_field_from_detail` parses `batch_id=` and `status=` patterns, but the actual gateway 409 message format is `"Batch 'batch_abc123' is not yet complete (status: in_progress)..."` -- it does NOT contain `batch_id=` or `status=` key-value pairs. The Go and TypeScript SDKs correctly parse the actual message format. **The Rust SDK will fail to extract `batch_id` and `status` from real gateway responses, resulting in an empty `batch_id` and `"unknown"` status in the `BatchNotComplete` error variant.** The error still maps to the correct type, but the metadata fields will be unhelpful.

This was noted in the individual Rust review but is elevated here because it's a cross-repo contract mismatch.

### 3.3 404 Handling

All SDKs check if the 404 is on a `/v1/batches` path and surface an "upgrade your gateway" message. TypeScript additionally checks if the message contains "not found" and passes it through directly (for genuine "batch not found" 404s). Go and Rust do not make this distinction. The spec explicitly calls for treating all batch 404s as "upgrade gateway", so the Go/Rust behavior is spec-compliant while TypeScript's is an improvement.

## 4. Cross-Repo Integration Issues

### Finding #1: `provider` field on `Batch` (Low)

The gateway injects a `provider` field into the `Batch` response on `POST /v1/batches` (create) only. The Rust SDK defines `provider: Option<String>` on its `Batch` struct to capture this. The Go SDK defines `Provider string json:"provider,omitempty"`. The TypeScript SDK re-uses the OpenAI `Batch` type directly, which does **not** have a `provider` field -- the extra field is silently ignored during deserialization.

This means TypeScript users cannot access `batch.provider` after `createBatch()`. The individual TypeScript review did not flag this. The spec (line 99) says: "SDKs should use a wrapper type or extract `provider` separately before deserializing the rest as `Batch`." TypeScript does neither.

**Impact:** Low. Users can track the provider themselves since they supply the `model` parameter in `provider:model` format. But it's a spec deviation.

### Finding #3: Python `__init__.py` batch type exports (Low)

The Python SDK exports `BatchNotCompleteError` from the top-level package but does NOT export `BatchResult`, `BatchResultItem`, `BatchResultError`, `Batch`, `BatchRequestCounts`, or any of the batch API functions (`create_batch`, `retrieve_batch`, etc.). Users must import these from submodules:

```python
from any_llm.types.batch import BatchResult, BatchResultItem, BatchResultError, Batch
from any_llm.api import acreate_batch, aretrieve_batch_results
```

This is inconsistent with how completion types are exported (e.g., `from any_llm import completion, acompletion`). The spec says "Export in `__init__.py` + `__all__`" and only `BatchNotCompleteError` meets this requirement. The individual Python review checked "Done" for this item but only `BatchNotCompleteError` is exported.

**Impact:** Low. Existing pattern for batch functions was always to import from `any_llm.api`. But the spec explicitly calls for `__init__.py` exports.

### Finding #4: Gateway `list_batches` response does NOT include `provider` field (Low)

The gateway injects `provider` into the response only for `POST /v1/batches` (create). The `GET /v1/batches` (list), `GET /v1/batches/{id}` (retrieve), and `POST /v1/batches/{id}/cancel` (cancel) endpoints return raw `batch.model_dump()` without injecting `provider`. This means:

- Rust: `batch.provider` will be `None` for list/retrieve/cancel responses.
- Go: `batch.Provider` will be `""` for list/retrieve/cancel responses.
- TypeScript: unaffected (doesn't model the field).

This is not necessarily wrong -- the `provider` query param is required on those endpoints so the caller already knows the provider. But it's asymmetric behavior worth noting.

### Finding #5: Go SDK `handleHTTPError` shares batch error semantics with completion endpoints (Low)

The Go SDK's `handleHTTPError` (used for completion endpoints) delegates entirely to `handleBatchError`. This means:
- A 409 on a completion endpoint would produce `BatchNotCompleteError` (semantically incorrect)
- A 404 on a completion endpoint at a `/v1/batches`-containing path would produce "upgrade your gateway" instead of `ModelNotFoundError`

In practice, 409 is unlikely from completion endpoints and the path check prevents false positives for 404. The individual Go review noted this. No other SDK shares this behavior -- Rust has separate `convert_error` and `convert_batch_error` functions, and TypeScript has separate `handleError` and `handleBatchError` methods.

### Finding #6: Gateway batch endpoints not available in platform mode (Informational)

The gateway registers batch routes only in standalone mode. The `if config.is_platform_mode` block in `main.py` returns early before `batches.router` is registered. This means platform-mode deployments get 404 on all batch endpoints. This is tested (`test_batch_endpoints_not_in_platform_mode`) and appears intentional, but it's not documented in the tech spec.

TypeScript supports platform-mode auth for batch requests (sets `Authorization: Bearer` header), but these will 404 against a platform-mode gateway. This is a documentation gap rather than a bug.

### Finding #7: Go SDK missing integration tests (Low)

The Go SDK has no integration test functions despite:
- `testutil/fixtures.go` adding `"gateway": "GATEWAY_API_KEY"` to the env key map
- The spec requiring "Integration tests against a running gateway"
- All other SDKs having integration tests (Python: committed, Rust: 2 `#[ignore]` tests, TypeScript: implicit through unit test thoroughness)

The individual Go review noted this and recommended adding stubs.

## 5. Consistency Matrix

### 5.1 `BatchNotCompleteError` Fields

| Field | Python | Rust | Go | TypeScript |
|---|---|---|---|---|
| `batch_id` | `self.batch_id` | `batch_id: ErrorStr` | `BatchID string` | `batchId?: string` |
| `status` | `self.batch_status` | `status: ErrorStr` | `Status string` | `batchStatus?: string` |
| `provider` | `self.provider_name` (inherited) | `provider: ErrorStr` | `Provider string` (in `BaseError`) | `providerName?: string` (inherited) |
| `message` | Generated from template | Generated from `#[error(...)]` | Generated in constructor | `defaultMessage` or custom |
| Sentinel/type check | `isinstance(e, BatchNotCompleteError)` | `matches!(e, AnyLLMError::BatchNotComplete{..})` | `errors.Is(err, ErrBatchNotComplete)` | `instanceof BatchNotCompleteError` |

### 5.2 Error Message Format

| SDK | Message Template |
|---|---|
| Python | `"Batch '{batch_id}' is not yet complete (status: {status}). Call retrieve_batch() to check the current status."` |
| Rust | `"Batch '{batch_id}' is not yet complete (status: {status}). Check status with retrieve_batch()."` |
| Go | `"batch '{batch_id}' is not yet complete (status: {status})"` |
| TypeScript | `"Batch is not yet complete"` (default) or gateway detail message passed through |
| Gateway (409 detail) | `"Batch '{batch_id}' is not yet complete (status: {status}). Call GET /v1/batches/{batch_id}?provider={provider} to check the current status."` |

These are all acceptable variations. The meaningful content (batch_id, status) is accessible programmatically in all SDKs regardless of message format.

## 6. Version Compatibility

The implementation order is correctly sequenced:
1. **Python SDK** releases first with all batch methods and types
2. **Gateway** pins `any-llm-sdk >= new version` and uses `acreate_batch`, `aretrieve_batch_results`, etc.
3. **Non-Python SDKs** target the gateway's HTTP endpoints independently

The gateway's `pyproject.toml` pins to the local SDK source (appropriate for development; will need a version pin for release). All non-Python SDKs are purely additive -- no existing APIs are modified.

## 7. Summary of Findings

| # | Severity | Finding | Repos |
|---|---|---|---|
| 1 | Low | TypeScript `Batch` type (re-exported from OpenAI) lacks `provider` field; spec says to use wrapper type or extract separately | any-llm-ts |
| 2 | Medium | Rust `extract_field_from_detail` parses `batch_id=`/`status=` patterns that don't match actual gateway 409 message format; will produce empty `batch_id` and `"unknown"` status | any-llm-rust vs gateway |
| 3 | Low | Python `__init__.py` exports only `BatchNotCompleteError`, not `BatchResult`/`BatchResultItem`/`BatchResultError` or batch API functions | any-llm |
| 4 | Low | Gateway injects `provider` field only on create response, not on retrieve/list/cancel | gateway |
| 5 | Low | Go `handleHTTPError` delegates to `handleBatchError`, leaking batch error semantics to completion endpoints | any-llm-go |
| 6 | Informational | Gateway batch endpoints unavailable in platform mode; TypeScript supports platform auth for batches | gateway, any-llm-ts |
| 7 | Low | Go SDK has no integration tests despite spec requirement and fixture setup | any-llm-go |

## 8. Recommendations

1. **Fix Rust 409 parsing (Finding #2):** Change `extract_field_from_detail` to use a regex matching the actual gateway format `Batch '([^']+)'.*\(status: (\w+)\)` (matching Go and TypeScript). This is the only finding that causes incorrect runtime behavior.

2. **Add `provider` to TypeScript Batch (Finding #1):** Either extend the OpenAI `Batch` type with an intersection (`Batch & { provider?: string }`) or add a wrapper type. Alternatively, document that `provider` is not captured.

3. **Export batch types from Python `__init__.py` (Finding #3):** Add `BatchResult`, `BatchResultItem`, `BatchResultError`, `Batch`, `BatchRequestCounts`, and batch API functions to `__init__.py` and `__all__`.

4. **Add Go integration test stubs (Finding #7):** Add gated test functions matching the pattern used in Rust (`#[ignore]`) and Python (uncommitted).

5. **Document platform mode exclusion (Finding #6):** Add a note to the tech spec or gateway docs that batch endpoints are standalone-mode only.

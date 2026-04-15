# Tech Spec: Batch API Support Across All SDKs

## Architecture Overview

This feature adds batch processing support across the any-llm ecosystem, enabling users to submit, monitor, cancel, and retrieve results of batch LLM jobs through any SDK. The architecture has three tiers:

1. **Python SDK (any-llm)** — The foundation. Adds Anthropic batch support, result retrieval for all providers, Gateway provider overrides for the new batch endpoints, and graduates the batch API from experimental.
2. **Gateway** — Adds batch proxy endpoints (`/v1/batches/*`) that accept JSON requests and delegate to the Python SDK. The gateway is a thin proxy: it constructs JSONL files from request arrays, delegates to provider-specific batch implementations in the SDK, and returns normalized responses.
3. **Non-Python SDKs (Rust, Go, TypeScript)** — Add HTTP client methods that call the gateway's batch endpoints. The Go SDK additionally requires building a new Gateway provider from scratch.

```
┌──────────────────────────────────────────────────────────────────┐
│                         LLM Providers                            │
│                   OpenAI / Anthropic / Mistral                   │
└──────────────┬───────────────────────────────────┬───────────────┘
               │ Provider SDKs                     │
┌──────────────▼───────────────────────────────────▼───────────────┐
│                       any-llm (Python SDK)                       │
│  ┌─────────────┐ ┌──────────────┐ ┌─────────────┐ ┌───────────┐ │
│  │ OpenAI Batch│ │Anthropic Bat.│ │ Mistral Bat.│ │Gateway Pr.│ │
│  │ (existing)  │ │ (NEW)        │ │ (existing)  │ │ (override)│ │
│  └─────────────┘ └──────────────┘ └─────────────┘ └─────┬─────┘ │
│  + retrieve_batch_results() on all providers             │       │
│  + BatchResult, BatchResultItem, BatchResultError types   │       │
│  + Graduate from @experimental                           │       │
└──────────────────────────────────────────────────────────┼───────┘
                                                           │
                    ┌──────────────────────────────────────▼───────┐
                    │              Gateway Service                  │
                    │  POST /v1/batches         (create)           │
                    │  GET  /v1/batches/{id}    (retrieve status)  │
                    │  POST /v1/batches/{id}/cancel  (cancel)      │
                    │  GET  /v1/batches         (list)             │
                    │  GET  /v1/batches/{id}/results (get results) │
                    └──────────┬──────────┬──────────┬─────────────┘
                               │          │          │
                    ┌──────────▼──┐ ┌─────▼────┐ ┌──▼──────────┐
                    │ any-llm-rust│ │any-llm-go│ │ any-llm-ts  │
                    │  Gateway    │ │ Gateway  │ │ GatewayClient│
                    │  .create_   │ │ (NEW     │ │ .createBatch│
                    │   batch()   │ │ provider)│ │ ()          │
                    └─────────────┘ └──────────┘ └─────────────┘
```

## Shared Interface Contracts

### Gateway Batch API Contract

All non-Python SDKs and the Python SDK's Gateway provider communicate with the gateway via these HTTP endpoints. This is the single coordination point across all repositories.

#### `POST /v1/batches` — Create a batch

**Request body (JSON):**
```json
{
  "model": "openai:gpt-4o-mini",
  "requests": [
    {
      "custom_id": "req-1",
      "body": {
        "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 100
      }
    }
  ],
  "completion_window": "24h",
  "metadata": {"team": "ml-ops"}
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `model` | string | Yes | `provider:model` format |
| `requests` | array of `BatchRequestItem` | Yes | Min 1, max 10,000 items |
| `completion_window` | string | No | Default `"24h"` |
| `metadata` | object (string→string) | No | Arbitrary key-value pairs |

**`BatchRequestItem`:**
| Field | Type | Required |
|-------|------|----------|
| `custom_id` | string | Yes |
| `body` | object | Yes (chat completion parameters) |

**Response: `200 OK`**
```json
{
  "id": "batch_abc123",
  "object": "batch",
  "endpoint": "/v1/chat/completions",
  "status": "validating",
  "created_at": 1714502400,
  "completion_window": "24h",
  "request_counts": {"total": 2, "completed": 0, "failed": 0},
  "metadata": {"team": "ml-ops"},
  "provider": "openai"
}
```

The response is a standard OpenAI `Batch` object with an additional `provider` field injected by the gateway. SDKs should use a wrapper type or extract `provider` separately before deserializing the rest as `Batch`.

#### `GET /v1/batches/{batch_id}?provider={provider}` — Retrieve batch status

**Query params:** `provider` (required, e.g., `"openai"`)
**Response: `200 OK`** — `Batch` object

#### `POST /v1/batches/{batch_id}/cancel?provider={provider}` — Cancel a batch

**Query params:** `provider` (required)
**Response: `200 OK`** — `Batch` object (updated status)

#### `GET /v1/batches?provider={provider}&after={cursor}&limit={n}` — List batches

**Query params:** `provider` (required), `after` (optional cursor), `limit` (optional integer)
**Response: `200 OK`**
```json
{
  "data": [{ /* Batch */ }, { /* Batch */ }]
}
```

#### `GET /v1/batches/{batch_id}/results?provider={provider}` — Retrieve batch results

**Query params:** `provider` (required)
**Response: `200 OK`** — `BatchResult` object (see below)
**Error: `409 Conflict`** — If batch status is not `completed`:
```json
{
  "detail": "Batch 'batch_abc123' is not yet complete (status: in_progress). Call GET /v1/batches/batch_abc123?provider=openai to check the current status."
}
```

#### Error Responses

| HTTP Code | Condition | Example `detail` |
|-----------|-----------|-----------------|
| 400 | Invalid input | `"Invalid request: model is required"` |
| 401/403 | Auth failure | `"Invalid API key"` |
| 404 | Batch not found | `"Batch 'batch_xyz' not found for provider 'openai'"` |
| 409 | Incompatible state | `"Batch 'batch_abc' is not yet complete (status: in_progress)..."` |
| 413 | Too many requests | `"Requests array exceeds maximum size of 10,000 items"` |
| 422 | Unsupported provider | `"Provider 'ollama' does not support batch operations"` |
| 429 | Rate limited | Upstream rate limit (proxied) |
| 502 | Upstream error | `"Upstream provider error: <detail>"` |

### Shared Types

#### `Batch` (OpenAI format — the unified return type)

All providers normalize their batch responses to this format. It is the `openai.types.Batch` Pydantic model from the OpenAI Python SDK.

```
Batch:
  id: string
  object: "batch"
  endpoint: string
  status: "validating" | "failed" | "in_progress" | "finalizing" | "completed" | "expired" | "cancelling" | "cancelled"
  created_at: integer (unix timestamp)
  completion_window: string
  input_file_id: string | null
  output_file_id: string | null
  error_file_id: string | null
  request_counts: BatchRequestCounts | null
  metadata: object | null
  in_progress_at: integer | null
  completed_at: integer | null
```

```
BatchRequestCounts:
  total: integer
  completed: integer
  failed: integer
```

#### `BatchResult` (new — the result retrieval type)

```
BatchResult:
  results: list[BatchResultItem]

BatchResultItem:
  custom_id: string
  result: ChatCompletion | null    # present on success
  error: BatchResultError | null   # present on failure

BatchResultError:
  code: string
  message: string
```

Each `BatchResultItem` has either `result` (success) or `error` (failure), never both, and never neither.

### Cross-SDK Method Naming

| Operation | Python | Rust | Go | TypeScript | Gateway Endpoint |
|-----------|--------|------|----|------------|-----------------|
| Create | `create_batch()` | `create_batch()` | `CreateBatch()` | `createBatch()` | `POST /v1/batches` |
| Retrieve | `retrieve_batch()` | `retrieve_batch()` | `RetrieveBatch()` | `retrieveBatch()` | `GET /v1/batches/{id}` |
| Cancel | `cancel_batch()` | `cancel_batch()` | `CancelBatch()` | `cancelBatch()` | `POST /v1/batches/{id}/cancel` |
| List | `list_batches()` | `list_batches()` | `ListBatches()` | `listBatches()` | `GET /v1/batches` |
| Results | `retrieve_batch_results()` | `retrieve_batch_results()` | `RetrieveBatchResults()` | `retrieveBatchResults()` | `GET /v1/batches/{id}/results` |

### Cross-SDK Type Naming

| Concept | Python | Rust | Go | TypeScript |
|---------|--------|------|----|------------|
| Batch job | `Batch` (from openai) | `Batch` | `Batch` | `Batch` (from openai) |
| Request counts | `BatchRequestCounts` | `BatchRequestCounts` | `BatchRequestCounts` | (inline in `Batch`) |
| Result container | `BatchResult` | `BatchResult` | `BatchResult` | `BatchResult` |
| Single result | `BatchResultItem` | `BatchResultItem` | `BatchResultItem` | `BatchResultItem` |
| Result error | `BatchResultError` | `BatchResultError` | `BatchResultError` | `BatchResultError` |
| Create params | positional args | `CreateBatchParams` | `CreateBatchParams` | `CreateBatchParams` |
| Request item | dict in JSONL | `BatchRequestItem` | `BatchRequestItem` | `BatchRequestItem` |
| List options | `after`/`limit` kwargs | `ListBatchesOptions` | `ListBatchesOptions` | `ListBatchesOptions` |
| Not-complete error | `BatchNotCompleteError` | `AnyLLMError::BatchNotComplete` | `*errors.BatchNotCompleteError` | `BatchNotCompleteError` |

## Implementation Order

```
Step 0:  Contract freeze — This tech spec serves as the frozen contract
           |
Step 1:  any-llm (Python SDK)
           |  - Anthropic batch provider
           |  - BatchResult types + retrieve_batch_results() on all providers
           |  - Gateway provider batch overrides
           |  - Graduate from @experimental
           |  (Must be released as a new minor version before Step 2)
           |
Step 2:  gateway
           |  - POST/GET /v1/batches/* endpoints
           |  - Auth, usage logging, error handling
           |  - OpenAPI spec regeneration
           |  - Pin any-llm-sdk >= new version from Step 1
           |  (Must be deployed before Step 3)
           |
Step 3:  any-llm-rust  ─┐
         any-llm-go    ─┤ (parallel, no cross-dependencies)
         any-llm-ts    ─┘
```

**Why this order is strict:**
- Step 1→2: The gateway imports `any-llm-sdk[all]` and calls `acreate_batch()`, `aretrieve_batch_results()`, etc. These must exist before the gateway can use them.
- Step 2→3: All non-Python SDKs target the gateway's HTTP endpoints. The endpoints must be live and tested before SDK client code can be integration-tested.
- Step 3 repos are independent: they each implement HTTP clients against the same frozen contract.

## Per-repo Summary

| Repo | Changes Needed | Complexity | Dependencies |
|------|---------------|------------|--------------|
| **any-llm** | Anthropic batch provider, `BatchResult` types, `retrieve_batch_results()` on all providers, Gateway provider overrides, remove `@experimental` | High | None |
| **gateway** | 5 new route handlers in `batches.py`, Pydantic request models, JSONL construction, usage logging, OpenAPI spec update | Medium | any-llm release |
| **any-llm-rust** | `Batch`/`BatchResult` types, 5 async methods on `Gateway`, `BatchNotComplete` error variant | Medium | Gateway deployed |
| **any-llm-go** | New `BatchProvider` interface, new `gateway` provider package (completions + batch), batch types, error types | High | Gateway deployed |
| **any-llm-ts** | 5 methods on `GatewayClient`, `BatchResult` types, `BatchNotCompleteError`, private HTTP helper | Low-Medium | Gateway deployed |

## Migration Strategy

### Backwards Compatibility

1. **Python SDK**: All existing `create_batch()`, `retrieve_batch()`, `cancel_batch()`, `list_batches()` signatures are unchanged. `retrieve_batch_results()` is additive. The `Batch` return type is unchanged. The only behavior change is removing `@experimental` (no more `FutureWarning`), which is intentional and documented in the changelog.

2. **Gateway**: All existing endpoints are unchanged. New `/v1/batches/*` endpoints are additive. The gateway's `pyproject.toml` must pin `any-llm-sdk >= <new-version>`.

3. **Non-Python SDKs**: All changes are additive (new types, new methods). No existing APIs are modified.

### Partial Deployment Behavior

| State | Behavior | Risk |
|-------|----------|------|
| Python SDK updated, gateway not yet | Python Gateway provider's batch overrides call `/v1/batches/*` which doesn't exist → HTTP 404. Error message should say "Upgrade your gateway." Same broken state as today but with correct code paths. | Low — existing broken behavior, now with better error messages |
| Gateway updated, non-Python SDKs not yet | Python SDK users get full batch support. Non-Python SDK users cannot use batch yet. | None — expected transition state |
| Mixed non-Python SDK versions | Each SDK is independent. Old versions simply lack batch methods. | None |

### Feature Detection

- **Python SDK Gateway provider**: On 404 from `/v1/batches/*`, raises `ProviderError` with message: "This gateway does not support batch operations. Upgrade your gateway to v<X.Y.0> or later."
- **Non-Python SDKs**: Same pattern — detect 404 on batch endpoints and surface a clear "upgrade your gateway" message rather than a generic HTTP error.

### Versioning

| Repo | Version Change | Notes |
|------|---------------|-------|
| any-llm | Minor bump (e.g., 1.13.0 → 1.14.0) | Additive changes only |
| gateway | Minor bump | New endpoints, pin new SDK version |
| any-llm-rust | Minor bump (0.1.0 → 0.2.0) | New types and methods |
| any-llm-go | Minor bump (0.9.0 → 0.10.0) | New provider + interface |
| any-llm-ts | Minor bump (0.1.0 → 0.2.0) | New methods and types |

## Testing Strategy

### Unit Tests (per-repo)

| Repo | Unit Test Focus |
|------|----------------|
| **any-llm** | Anthropic batch type conversion (status mapping, edge cases, unknown statuses). Gateway provider batch method overrides (correct HTTP calls, provider query param). `BatchResult` construction from each provider's raw format. |
| **gateway** | Route handlers with mocked SDK calls (mock `acreate_batch`, `aretrieve_batch_results`, etc.). Auth verification. Input validation (empty requests, too many requests, missing model, unsupported provider). Error mapping (404→batch not found, 409→not complete). |
| **any-llm-rust** | `Batch`/`BatchResult` deserialization from JSON fixtures. HTTP call construction with wiremock (correct URLs, query params, headers). Error mapping for 404, 409, 422 status codes. |
| **any-llm-go** | Gateway provider construction and auth. HTTP calls with `httptest` fake server (correct URLs, headers, body). Error type assertions. `BatchProvider` interface satisfaction (compile-time check). |
| **any-llm-ts** | Method delegation and HTTP call construction with vitest mocks. Error mapping (409→`BatchNotCompleteError`, 404→gateway upgrade message). Type construction from JSON fixtures. |

### Integration Tests

| Scope | Approach |
|-------|----------|
| **Python SDK ↔ Providers** | Integration tests for Anthropic batch create/retrieve/cancel/list/results (requires `ANTHROPIC_API_KEY`). Result retrieval for OpenAI and Mistral. |
| **Gateway ↔ Python SDK** | Gateway integration tests with mocked providers. End-to-end test with at least one real provider (OpenAI) if API key is available. |
| **Non-Python SDKs ↔ Gateway** | Integration tests against a running gateway with at least OpenAI configured. At least one test per SDK against a non-OpenAI provider (Anthropic or Mistral) to verify type conversion round-trips. These tests require a live gateway and are gated by environment variables. |

### Cross-Repo Validation

1. **Contract conformance**: Each non-Python SDK's integration tests validate against the actual gateway HTTP responses, ensuring the gateway's JSON output matches what SDKs expect.
2. **Error round-trip**: Each SDK must have a test that verifies 409 (batch not complete) from the gateway produces the correct typed error with `batch_id` and `status` fields populated.
3. **Type fidelity**: The `BatchResult` JSON from the gateway must round-trip through each SDK's type system without data loss. Integration tests should verify `custom_id`, `result.choices`, and `error.code`/`error.message` survive the round-trip.

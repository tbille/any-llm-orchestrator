# PRD: Batch API Support Across All SDKs

## Problem Statement

Users of the any-llm ecosystem who need to process large volumes of LLM requests cost-effectively cannot do so through the gateway or non-Python SDKs. The Python SDK has experimental batch support for OpenAI and Mistral, but three critical gaps remain:

1. **Anthropic is unsupported.** Anthropic offers a Message Batches API (typically 50% cheaper, 24h window), but the Python SDK has no implementation for it.
2. **The gateway has no batch endpoints.** Batch requests cannot flow through the gateway, meaning there is no centralized auth, routing, or observability for batch jobs.
3. **Non-Python SDKs have zero batch functionality.** The Rust, Go, and TypeScript SDKs cannot create, monitor, or retrieve batch jobs at all.

Additionally, the Python SDK is missing a `retrieve_batch_results` operation, making the existing batch workflow incomplete: users can create and monitor batches but have no SDK-level way to download the results.

There is also an existing correctness issue: the Python SDK's Gateway provider sets `SUPPORTS_BATCH = True` (inherited from `BaseOpenAIProvider`) despite the gateway having no batch endpoints. Calling batch methods via the Gateway provider currently results in HTTP 404 errors. This must be resolved as part of this work.

This forces users to either use the Python SDK directly against providers (bypassing the gateway), build custom provider-specific integrations, or avoid batch processing entirely.

## User Stories

- As a **developer using any non-Python SDK**, I want to submit batch jobs through the gateway so that I can process large request volumes at reduced cost without switching to Python.
- As a **Python SDK user**, I want to use Anthropic's batch processing so that I can batch Anthropic requests with the same interface I use for OpenAI and Mistral.
- As a **gateway operator**, I want batch requests to flow through the gateway so that all request types go through centralized auth and observability.
- As a **developer**, I want to retrieve batch results through the same SDK I used to create the batch so that I have a complete end-to-end workflow without manual file downloads.
- As a **developer**, I want a stable (non-experimental) batch API so that I can depend on it in production without worrying about breaking changes.
- As a **developer**, I want clear error messages when batch operations fail so that I can diagnose issues without consulting provider-specific documentation.

## Scope

### Repositories affected

| Repo | Change | Why |
|------|--------|-----|
| **any-llm** (Python SDK) | Add Anthropic batch provider. Add result retrieval. Override batch methods on Gateway provider. Graduate batch API from experimental. | Foundation that the gateway and all SDKs depend on. |
| **gateway** | Add batch proxy endpoints (`/v1/batches/*`). | Non-Python SDKs need a gateway endpoint to talk to. Gateway provides centralized auth. |
| **any-llm-rust** | Add batch client methods to the Gateway provider. | Rust users need batch access via gateway. |
| **any-llm-go** | **Add a new Gateway provider** with batch support. | Go users need batch access via gateway. The Go SDK currently has no Gateway provider (only a Platform provider), so this is a new provider, not just new methods. |
| **any-llm-ts** | Add batch client methods to GatewayClient. | TypeScript users need batch access via gateway. |

### Out of scope

- **Gateway-level fan-out** (send N requests, execute concurrently, return all results in one response). This is a different feature.
- **Gateway batch job state management.** The gateway proxies to providers; it does not store batch state in its own database.
- **Budget enforcement for batch requests.** May be a future enhancement once batch cost attribution is better understood. **Note:** this means the platform's cost tracking will undercount usage for batch operations until this is addressed.
- **Platform integration.** Batch observability in the platform dashboard is deferred.
- **Batch support for providers beyond OpenAI, Mistral, and Anthropic.** Other providers can be added incrementally.
- **Batch support for embeddings or responses endpoints.** Completions-only for this iteration.
- **Documentation beyond API reference.** A batch usage guide for the MkDocs site is deferred to a follow-up; however, API reference docs (docstrings, OpenAPI spec) are in scope.

## Design Decisions

The following decisions were evaluated during PRD review. They are prerequisites for implementation and must not be reopened without re-evaluating all downstream SDK impact.

### DD1: Gateway batch input format

**Decision: JSON body with a `requests` array.** The gateway accepts a JSON body containing a `model` field (using `provider:model` format) and a `requests` array of completion request objects. The gateway internally constructs the JSONL file and passes it to the Python SDK's `acreate_batch()`.

**Rationale:** This is the simplest interface for SDK consumers (no file upload mechanics needed on the client side). It is consistent with how the gateway handles `/v1/chat/completions` (JSON in, JSON out).

**Implication:** The Python SDK's Gateway provider cannot use the inherited `BaseOpenAIProvider._acreate_batch` (which expects a local file path and performs a file upload to `/v1/files`). The Gateway provider must override `_acreate_batch` to POST a JSON body to `/v1/batches` instead. See requirement #7 below.

### DD2: Provider identification for retrieve/cancel/list

**Decision: Require `provider` as a query parameter on all batch endpoints.** All batch endpoints that operate on an existing batch (`GET /v1/batches/{batch_id}`, `POST /v1/batches/{batch_id}/cancel`, `GET /v1/batches/{batch_id}/results`) require a `?provider=` query parameter. `GET /v1/batches` (list) also requires `?provider=`.

**Rationale:** This is the simplest approach and aligns with the gateway's "thin proxy" philosophy -- no database table to store batch-to-provider mappings, no encoding conventions to maintain. The minor ergonomic cost (requiring `provider` on each call) is acceptable because batch operations are low-frequency (create once, poll occasionally, retrieve once).

**Implication:** All SDKs must pass `provider` on every batch call. The `create_batch` response should echo back the provider for client-side caching.

### DD3: Batch result format

**Decision: Return a structured `BatchResult` object containing a list of `BatchResultItem` entries, where each entry has a `custom_id`, an optional `ChatCompletion` (for successes), and an optional `BatchResultError` (for failures).** This is the most useful format because batch operations inherently produce per-request results, and callers need to correlate results with their original requests.

```
BatchResult:
  results: list[BatchResultItem]

BatchResultItem:
  custom_id: str
  result: ChatCompletion | None  # present on success
  error: BatchResultError | None  # present on failure

BatchResultError:
  code: str
  message: str
```

**Rationale:** OpenAI returns results in a JSONL output file with `custom_id` + response pairs. Anthropic returns results inline with `custom_id` + result/error. Mistral follows a similar pattern. A structured object that normalizes these formats gives users a consistent experience. Returning raw JSONL would push parsing responsibility to every caller; returning only successes would lose error information.

**Implication:** New types (`BatchResult`, `BatchResultItem`, `BatchResultError`) must be defined in the Python SDK's `types/` module and mirrored in all SDK type systems.

### DD4: Go SDK Gateway provider

**Decision: Add a new dedicated `Gateway` provider in the Go SDK.** This is a new provider package under `providers/gateway/` that implements both the existing `Provider` interface (for completions) and the new `BatchProvider` interface.

**Rationale:** Extending `CompatibleProvider` would conflate two responsibilities. A dedicated provider is cleaner, testable in isolation, and consistent with how Rust and TypeScript structure their Gateway providers. The additional code is justified by the long-term value -- once the Go Gateway provider exists, future gateway features (responses API, embeddings, etc.) have a natural home.

**Implication:** This is larger scope than just "add batch methods." The Go SDK work includes a full Gateway provider with completion support (delegating to `/v1/chat/completions`), plus batch methods. This should be estimated accordingly.

## Requirements

### Functional requirements

#### any-llm (Python SDK)

1. **Add Anthropic Message Batches support.** Implement `_acreate_batch`, `_aretrieve_batch`, `_acancel_batch`, `_alist_batches` on the Anthropic provider, converting Anthropic's batch response format to the unified `Batch` return type (same pattern Mistral already uses via `_convert_batch_job_to_openai`).
2. **Set `SUPPORTS_BATCH = True`** on the Anthropic provider class.
3. **Implement Anthropic batch status mapping.** Map Anthropic's `MessageBatch` statuses to OpenAI `Batch` statuses. At minimum: `in_progress` to `in_progress`, `ended` (with all succeeded) to `completed`, `ended` (with failures) to `completed` (with appropriate `request_counts`), `canceling` to `cancelling`, `canceled` to `cancelled`, `expired` to `expired`. Log a warning for unknown statuses and default to `in_progress` (consistent with the Mistral precedent).
4. **Add result retrieval types.** Define `BatchResult`, `BatchResultItem`, and `BatchResultError` in `src/any_llm/types/batch.py`. See DD3 for the structure.
5. **Add result retrieval methods.** Add `retrieve_batch_results()` and `aretrieve_batch_results()` to the `AnyLLM` base class and top-level API (`api.py`). These return `BatchResult`. The base class must add `_aretrieve_batch_results` as an overridable private stub (following the existing pattern for `_acreate_batch` etc.).
6. **Implement `_aretrieve_batch_results`** on all batch-capable providers:
   - **OpenAI:** Download the output file via `self.client.files.content(output_file_id)`, parse the JSONL, and construct `BatchResult`.
   - **Mistral:** Use the Mistral SDK to retrieve job results and convert to `BatchResult`.
   - **Anthropic:** Use the Anthropic SDK to retrieve batch results (which are inline, not file-based) and convert to `BatchResult`.
   - **Gateway:** POST/GET to the gateway's `/v1/batches/{batch_id}/results` endpoint and deserialize the response.
   - **Platform:** Delegate to the wrapped provider's `_aretrieve_batch_results` (following the existing delegation pattern for the other 4 batch operations).
7. **Override batch methods on the Gateway provider.** The Gateway provider currently inherits `_acreate_batch` from `BaseOpenAIProvider`, which uploads a file to `/v1/files` then creates a batch. This does not work with the gateway's JSON-body-based batch endpoint (DD1). Override `_acreate_batch` to POST a JSON body (with `model` and `requests` fields) to the gateway's `/v1/batches`. Also override `_aretrieve_batch`, `_acancel_batch`, `_alist_batches` to pass the `provider` query parameter (DD2).
8. **Graduate batch API from experimental.** Remove the `@experimental` decorator from all batch methods (including the new `retrieve_batch_results`) once the API surface is confirmed stable. Note: this removes the `FutureWarning` emitted on each call, which is a user-visible behavior change. Document this in the changelog.
9. **Error handling for `retrieve_batch_results`.** Raise a clear error (e.g., `BatchNotCompleteError` or equivalent mapped to the SDK's exception hierarchy) when `retrieve_batch_results` is called on a batch whose status is not `completed`. Do not silently return empty results.
10. **Add tests.**
    - Unit tests for Anthropic batch type conversion (status mapping, field mapping, edge cases for unknown statuses).
    - Unit tests for Gateway provider batch method overrides (verify correct HTTP calls, provider query param).
    - Integration tests for Anthropic batch create/retrieve/cancel/list/results.
    - Integration tests for result retrieval on OpenAI and Mistral.
    - Unit tests for `BatchResult`/`BatchResultItem` construction from each provider's raw format.

#### gateway

11. **`POST /v1/batches`** -- Create a batch. Accepts a JSON body with:
    - `model` (required, string): Provider and model in `provider:model` format.
    - `requests` (required, array): List of completion request objects (each must include `custom_id` and `body` with the chat completion parameters).
    - `completion_window` (optional, string, default `"24h"`): Processing time window.
    - `metadata` (optional, object): Arbitrary key-value metadata.

    The gateway must: parse `model` to extract the provider, construct a JSONL file from the `requests` array, write it to a temporary file, call the Python SDK's `acreate_batch()`, and return the `Batch` object as JSON. The response must include a `provider` field so SDKs can cache it for subsequent calls.

12. **`GET /v1/batches/{batch_id}?provider=`** -- Retrieve batch status. Requires `provider` query param. Delegates to `aretrieve_batch()`.
13. **`POST /v1/batches/{batch_id}/cancel?provider=`** -- Cancel a batch. Requires `provider` query param. Delegates to `acancel_batch()`.
14. **`GET /v1/batches?provider=`** -- List batches. Requires `provider` query param. Supports pagination via `after` and `limit` query params. Delegates to `alist_batches()`.
15. **`GET /v1/batches/{batch_id}/results?provider=`** -- Retrieve batch results. Requires `provider` query param. Delegates to `aretrieve_batch_results()`. Returns a `BatchResult` JSON object.
16. **Authentication.** All batch endpoints require API key or master key authentication via `verify_api_key_or_master_key`, consistent with existing LLM proxy endpoints (`/v1/chat/completions`, `/v1/messages`, etc.).
17. **Usage logging.** Log batch create and result retrieval operations to `UsageLog` (provider, model, endpoint, status). Token counts and cost can be logged when results are retrieved if available.
18. **Prometheus metrics.** Add batch operations to existing `gateway_requests` counter with appropriate endpoint labels.
19. **Error responses.** The gateway must return appropriate HTTP error codes:
    - `400` for invalid input (missing model, empty requests array, malformed request objects).
    - `401/403` for authentication failures (consistent with existing endpoints).
    - `404` for batch not found.
    - `409` for operations on batches in incompatible states (e.g., cancelling an already completed batch).
    - `422` for unsupported provider (provider does not support batch).
    - `502` for upstream provider errors.
20. **Request size limits.** Enforce a maximum `requests` array size (recommend 10,000 items to stay within Anthropic's limit, which is the most restrictive). Return `413` if exceeded. Document the limit in the OpenAPI spec.
21. **Temporary file cleanup.** The JSONL file created from the `requests` array must be cleaned up after `acreate_batch()` completes (or fails). Use a context manager or try/finally to ensure cleanup.

#### any-llm-rust

22. **Add batch methods to the `Gateway` provider**: `create_batch`, `retrieve_batch`, `cancel_batch`, `list_batches`, `retrieve_batch_results` (all async). These call the gateway's batch endpoints over HTTP, passing `provider` as a query parameter where required.
23. **Add Rust types**: `Batch`, `BatchStatus`, `BatchRequestCounts`, `BatchResult`, `BatchResultItem`, `BatchResultError`.
24. **Add tests.** Unit tests with mocked gateway responses (including error responses). Integration tests against a live gateway.

#### any-llm-go

25. **Add a new `Gateway` provider** under `providers/gateway/` that implements the `Provider` interface (for completions via `/v1/chat/completions`) and the new `BatchProvider` interface (for batch operations via `/v1/batches/*`). This provider authenticates using `X-AnyLLM-Key` header, consistent with the Rust and TS SDKs.
26. **Define a `BatchProvider` interface** in `providers/types.go` with `CreateBatch`, `RetrieveBatch`, `CancelBatch`, `ListBatches`, `RetrieveBatchResults` methods, following Go conventions and the optional-interface pattern used by `EmbeddingProvider`.
27. **Add Go types** for `Batch`, `BatchStatus`, `BatchRequestCounts`, `BatchResult`, `BatchResultItem`, `BatchResultError`.
28. **Add tests.** Unit tests with HTTP mocks (including error responses). Integration tests against a live gateway.

#### any-llm-ts

29. **Add batch methods to `GatewayClient`**: `createBatch()`, `retrieveBatch()`, `cancelBatch()`, `listBatches()`, `retrieveBatchResults()`. These methods make HTTP calls to the gateway's `/v1/batches/*` endpoints. Since the gateway's batch endpoints use a custom JSON format (DD1, not the OpenAI file-upload format), these methods must use direct HTTP calls (e.g., via `fetch` or the underlying HTTP client) rather than delegating to `this.openai.batches.*`.
30. **Export TypeScript types** for `Batch`, `BatchResult`, `BatchResultItem`, `BatchResultError`. Re-export `Batch` from the `openai` package; define `BatchResult*` types locally.
31. **Add tests.** Unit tests with mocked HTTP (including error responses). Integration tests against a live gateway.

### Non-functional requirements

1. **Backwards compatibility.** The Python SDK's existing `create_batch`, `retrieve_batch`, `cancel_batch`, `list_batches` signatures must not change. New methods (`retrieve_batch_results`) are additive. The `Batch` return type (OpenAI-format) remains the unified response type across all providers. Removing `@experimental` removes the `FutureWarning` on each call; this is an intentional behavior change and must be noted in the changelog.
2. **Consistency.** All SDKs expose the same 5 batch operations (create, retrieve status, cancel, list, retrieve results) with naming conventions idiomatic to each language.
3. **Error handling.** Provider-specific batch errors must map to each SDK's unified exception hierarchy. At minimum, the following error cases must produce clear, actionable errors:
   - Provider does not support batch operations.
   - Batch not found (invalid batch ID or wrong provider).
   - Batch not yet complete (calling `retrieve_batch_results` prematurely).
   - Invalid batch input (malformed requests, mixed models for Mistral).
   - Provider rate limit exceeded during batch creation.
   - Gateway running an older version without batch endpoints (SDKs should surface the 404 as a clear "batch not supported by this gateway" message, not a generic HTTP error).
4. **Timeouts.** Batch creation involves file upload and may take longer than standard completions. SDKs and gateway must support configurable timeouts for batch operations. The gateway should set a generous default timeout for the `POST /v1/batches` endpoint (recommend 120s) since it involves file construction and upload to the provider.
5. **Auth consistency.** Gateway batch endpoints use the same authentication mechanism as `/v1/chat/completions` (API key or master key via `Authorization`, `X-AnyLLM-Key`, or `x-api-key` headers).
6. **Result size.** For large batches (thousands of results), `retrieve_batch_results` may return a large JSON payload. For this iteration, the full result set is returned in a single response. Pagination of results is deferred but the `BatchResult` type should be designed to allow adding pagination fields (e.g., `has_more`, `next_cursor`) in a future minor version without breaking changes.

## Success Criteria

1. A user can create, monitor, cancel, and retrieve results of a batch job through the gateway using any of the 4 SDKs (Python, Rust, Go, TypeScript).
2. A Python SDK user can create Anthropic batch jobs using the same `create_batch()` interface used for OpenAI and Mistral, and get back a unified `Batch` object.
3. `retrieve_batch_results()` works end-to-end for OpenAI, Mistral, and Anthropic providers in the Python SDK, returning a `BatchResult` with correctly populated `custom_id`, result, and error fields.
4. All batch methods in the Python SDK are stable (not marked `@experimental`).
5. All non-Python SDK integration tests pass against a running gateway instance with at least OpenAI as the batch-capable provider. At least one test must also run against a non-OpenAI provider (Mistral or Anthropic) to verify type conversion round-trips through the gateway correctly.
6. Gateway batch endpoints appear in the OpenAPI spec (`docs/public/openapi.json`) and respond with proper error codes for auth failures (401), invalid input (400), unsupported providers (422), and batch not found (404).
7. Calling `retrieve_batch_results()` on a non-completed batch returns a clear error (not empty results or a generic exception) in all SDKs.
8. The Gateway provider in the Python SDK correctly calls the gateway's batch endpoints (not the inherited OpenAI file-upload flow), verified by unit tests with mocked HTTP.

## Resolved Design Decisions

See the "Design Decisions" section above (DD1-DD4) for the full rationale on each.

## Open Questions

1. **Anthropic batch type mapping details.** Anthropic's `MessageBatch` response structure differs from OpenAI's `Batch` type (different status names, no file IDs, results inline vs. file download). The mapping needs careful design, similar to how `_convert_batch_job_to_openai` works for Mistral. This should be resolved during implementation of requirement #1 with a mapping table reviewed in the PR.
2. **Result pagination (future).** For very large batches (10,000+ results), a single JSON response may be impractical. Should the gateway and SDKs support a paginated `retrieve_batch_results` in a future iteration? If so, the `BatchResult` type should reserve room for pagination fields. *Recommendation: design the type to be extensible but defer pagination to a follow-up.*

## Cross-repo Impact Analysis

### Rollout order (strict sequence)

```
Step 0:  Design freeze                -- Gateway OpenAPI spec for batch endpoints published
           |
Step 1:  any-llm (Python SDK)         -- Anthropic batch + result retrieval + Gateway
           |                              provider overrides + stabilize API
Step 2:  gateway                       -- Batch proxy endpoints (depends on updated SDK)
           |
Step 3:  any-llm-rust  -+
         any-llm-go    -+- (parallel, depend on gateway batch endpoints)
         any-llm-ts    -+
```

**Step 0: Design freeze.** The gateway batch endpoint contract (URL paths, request/response schemas, error codes) must be documented as an OpenAPI spec fragment and reviewed by all SDK maintainers before any implementation begins. This is the single source of truth for Step 3.

**Step 1 must land and be released before Step 2 begins.** The gateway's `pyproject.toml` depends on `any-llm-sdk[all]` (currently locked to v1.13.0), so the SDK must be published with Anthropic batch support, result retrieval types/methods, and Gateway provider overrides before the gateway can use them.

**Step 2 must land before Step 3 begins.** All non-Python SDKs target the gateway's batch endpoints, so the gateway contract must be final first.

**Step 3 repos can proceed in parallel** since they have no dependencies on each other.

### Partial deployment behavior

During the rollout, the following transitional states will exist:

- **After Step 1, before Step 2:** The Python SDK's Gateway provider will have batch overrides that call `/v1/batches/*` on the gateway, but the gateway won't have those endpoints yet. Batch calls via the Gateway provider will fail with HTTP 404. This is the same as the current (broken) behavior, but now with correct Gateway-specific code paths rather than inherited OpenAI file-upload logic. **Mitigation:** The Gateway provider should set `SUPPORTS_BATCH = True` only in Step 1 (it already is), and the error message for 404 should clearly indicate "gateway does not support batch endpoints -- upgrade your gateway."
- **After Step 2, before Step 3:** The gateway has batch endpoints but non-Python SDKs cannot use them yet. Python SDK users get full batch support. This is acceptable and expected.

### Dependency details

| Change | Depends on | Blocks |
|--------|-----------|--------|
| Design freeze: gateway batch OpenAPI spec | None | All implementation |
| Python SDK: Anthropic batch support | None | Gateway (uses SDK internally) |
| Python SDK: `BatchResult` type + `retrieve_batch_results()` | None | Gateway results endpoint, all SDK type definitions |
| Python SDK: Gateway provider batch overrides | DD1, DD2 decisions | Gateway endpoint contract validation |
| Python SDK: graduate from experimental | Anthropic batch + results working | Communicates stability to users |
| Gateway: batch endpoints | Python SDK with results support | All non-Python SDKs |
| Rust SDK: batch via gateway | Gateway batch endpoints live + OpenAPI spec | None |
| Go SDK: **full Gateway provider** + batch | Gateway batch endpoints live + OpenAPI spec | None |
| TS SDK: batch on GatewayClient | Gateway batch endpoints live + OpenAPI spec | None |

### Versioning

- **Python SDK**: Minor version bump (e.g., 1.13.0 -> 1.14.0). All changes are additive (new provider support, new methods, new types). No breaking changes to existing signatures. Removing `@experimental` is a behavior change (no more `FutureWarning`) but not a breaking API change.
- **Gateway**: Minor version bump. New endpoints only; existing API unchanged. Update `docs/public/openapi.json`. Minimum `any-llm-sdk` version must be pinned in `pyproject.toml` (e.g., `any-llm-sdk[all]>=1.14.0`).
- **Rust SDK**: Minor version bump. New types and methods.
- **Go SDK**: Minor version bump. New `BatchProvider` interface and new `gateway` provider package.
- **TS SDK**: Minor version bump. New methods on existing client and new types.
- **No database migrations** needed in the gateway (thin pass-through, no batch state stored).

### Risk: Go SDK scope is larger than the other SDKs

The Go SDK requires building an entire Gateway provider from scratch (completions + batch), not just adding batch methods to an existing provider. This is roughly 2-3x the effort of the Rust or TS SDK work. Consider whether the Go Gateway provider's completion support can ship first (without batch) to de-risk the timeline, with batch methods added as a fast follow.

### Risk: Gateway API contract is the coordination bottleneck

The gateway batch endpoint contract (URL paths, request/response schemas, error codes) must be **designed and frozen before** non-Python SDK work begins. All 3 SDKs will implement clients against this contract. Changes after SDK work starts require coordinated updates across 3 repos. *Mitigation: Step 0 publishes the gateway OpenAPI spec fragment for batch endpoints as the single source of truth. SDK PRs must link to this spec.*

### Provider-specific constraints (informational)

These provider limits affect implementation but do not need to be enforced by the SDK (providers enforce their own limits). They should be documented for users:

| Provider | Max requests per batch | Processing window | Result delivery |
|----------|----------------------|-------------------|-----------------|
| OpenAI | 50,000 | 24h | File download via `output_file_id` |
| Anthropic | 10,000 | 24h | Inline in batch response |
| Mistral | Varies | Configurable (`timeout_hours`) | File download |

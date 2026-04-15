# Code Review: any-llm-ts Batch API Support

## Status: PASS

The implementation is spec-compliant, well-tested, and backwards-compatible. All 77 tests pass and TypeScript compiles without errors.

## Issues Found

No blocking issues found. The implementation faithfully follows the spec across all areas.

## Detailed Compliance Check

### 1. Types (`src/types.ts`) -- PASS

All seven spec-required types are present and correctly defined:
- `Batch` re-exported from `openai/resources/batches` (line 9)
- `BatchRequestItem` with `custom_id: string` and `body: Record<string, unknown>` (lines 39-42)
- `CreateBatchParams` with `model`, `requests`, optional `completion_window`, optional `metadata` (lines 44-49)
- `ListBatchesOptions` with optional `after` and `limit` (lines 51-54)
- `BatchResultError` with `code` and `message` (lines 56-59)
- `BatchResultItem` with `custom_id`, optional `result?: ChatCompletion`, optional `error?: BatchResultError` (lines 61-65)
- `BatchResult` with `results: BatchResultItem[]` (lines 67-69)

The `ChatCompletion` import required for `BatchResultItem.result` is correctly imported (line 6).

### 2. Error Class (`src/errors.ts`) -- PASS

`BatchNotCompleteError` (lines 79-89):
- Extends `AnyLLMError` as specified
- `static override defaultMessage = "Batch is not yet complete"` matches spec
- `readonly batchId?: string` and `readonly batchStatus?: string` present
- Constructor signature matches spec: `options: AnyLLMErrorOptions & { batchId?: string; batchStatus?: string } = {}`
- Calls `super(options)` and assigns both fields
- JSDoc comment describes the HTTP 409 use case

### 3. Private Properties on `GatewayClient` (`src/client.ts`) -- PASS

- `private readonly baseUrl: string` declared (line 90)
- `private readonly authHeaders: Record<string, string>` declared (line 93)
- Constructor stores `baseUrl` from the resolved `apiBase` (line 146)
- Auth headers correctly branch on platform vs non-platform mode (lines 147-155):
  - Platform mode: `Authorization: Bearer ${platformToken}`
  - Non-platform mode: `X-AnyLLM-Key: Bearer ${apiKey}`
  - `defaultHeaders` merged via `Object.assign` (lines 153-155)

### 4. Batch Methods (`src/client.ts`) -- PASS

All five public methods implemented exactly per spec:
- `createBatch(params: CreateBatchParams): Promise<Batch>` -- POST to `/batches` with body (lines 339-341)
- `retrieveBatch(batchId: string, provider: string): Promise<Batch>` -- GET with `?provider=` query param, `encodeURIComponent` on both params (lines 350-355)
- `cancelBatch(batchId: string, provider: string): Promise<Batch>` -- POST to `/batches/{id}/cancel?provider=` (lines 364-369)
- `listBatches(provider: string, options?: ListBatchesOptions): Promise<Batch[]>` -- GET with URLSearchParams, returns `response.data` (lines 378-387)
- `retrieveBatchResults(batchId: string, provider: string): Promise<BatchResult>` -- GET to `/batches/{id}/results?provider=` (lines 397-402)

All methods have correct JSDoc comments with `@param` and `@returns` tags. `retrieveBatchResults` includes `@throws {BatchNotCompleteError}`.

### 5. Private HTTP Helper (`src/client.ts`) -- PASS

`batchRequest<T>` (lines 411-433):
- Constructs URL from `this.baseUrl` + path
- Sets `Content-Type: application/json` header
- Spreads `this.authHeaders`
- Uses global `fetch`
- Conditionally JSON-stringifies body
- Calls `this.handleBatchError(response)` on non-OK responses
- Returns `response.json() as T`

### 6. Batch Error Handler (`src/client.ts`) -- PASS

`handleBatchError` (lines 439-502):
- Return type `Promise<never>` correctly signals it always throws
- Parses response body with `.catch(() => ({}))` fallback
- Extracts `detail` field from body, falls back to `statusText`
- Appends `correlation_id` from `x-correlation-id` header when present
- Switch statement covers all spec-required status codes:
  - 401/403 -> `AuthenticationError`
  - 404 -> `AnyLLMError` with upgrade hint (or pass-through if message contains "not found")
  - 409 -> `BatchNotCompleteError` with `extractBatchId` and `extractStatus`
  - 422 -> `AnyLLMError`
  - 429 -> `RateLimitError` with `retryAfter` from `retry-after` header
  - 502 -> `UpstreamProviderError`
  - 504 -> `GatewayTimeoutError`
  - default -> `AnyLLMError`

Helper functions `extractBatchId` and `extractStatus` (lines 505-512) are module-level as spec allows, with correct regex patterns.

### 7. Exports (`src/index.ts`) -- PASS

- `BatchNotCompleteError` exported as a class export (line 25)
- All seven batch types exported as type-only exports: `Batch`, `BatchRequestItem`, `BatchResult`, `BatchResultError`, `BatchResultItem`, `CreateBatchParams`, `ListBatchesOptions` (lines 34-47)
- Existing exports unchanged (no regression)

### 8. Test Coverage -- PASS

**`tests/unit/client.test.ts`** (830 lines, batch tests from line 399):

Batch method tests (describe "GatewayClient batch methods", line 418):
- `createBatch sends correct request` -- verifies POST URL, method, JSON body, Content-Type header
- `createBatch returns Batch object` -- verifies response fields
- `retrieveBatch sends provider query param` -- verifies GET URL with `?provider=openai`
- `retrieveBatch encodes special characters` -- bonus test beyond spec
- `cancelBatch sends correct request` -- verifies POST URL and response status
- `listBatches sends pagination params` -- verifies all three query params
- `listBatches sends only provider when no options` -- bonus test
- `listBatches returns array of Batch` -- verifies array length and IDs
- `retrieveBatchResults returns BatchResult` -- verifies URL, results array, error fields

Batch error handling tests (describe "GatewayClient batch error handling", line 574):
- 409 -> `BatchNotCompleteError` with `batchId`, `batchStatus`, `statusCode`, `providerName`
- 404 -> `AnyLLMError` with upgrade message
- 404 with "not found" -> passes message through (bonus test)
- 401 -> `AuthenticationError`
- 403 -> `AuthenticationError` (bonus test)
- 429 -> `RateLimitError` with `retryAfter`
- 502 -> `UpstreamProviderError`
- 504 -> `GatewayTimeoutError`
- 422 -> `AnyLLMError` (bonus test)
- Unrecognized status -> `AnyLLMError` (bonus test)
- `correlation_id` included in error message (bonus test)
- Falls back to statusText on unparseable body (bonus test)

Batch auth mode tests (describe "GatewayClient batch auth modes", line 746):
- Non-platform mode uses `X-AnyLLM-Key` header
- Platform mode uses `Authorization` header
- `defaultHeaders` included in batch requests (bonus test)

**`tests/unit/errors.test.ts`** (describe "BatchNotCompleteError", line 132):
- Has correct `defaultMessage`
- Stores `batchId` and `batchStatus`
- Fields undefined by default
- `instanceof AnyLLMError` and `instanceof Error`
- Stores `statusCode` and `providerName`

All spec-required tests are present. Implementation includes several additional tests beyond the spec.

### 9. Backwards Compatibility -- PASS

- No existing public APIs were modified
- `GatewayClient` retains all existing methods (`completion`, `response`, `embedding`, `listModels`)
- Existing error classes unchanged
- Existing type exports unchanged (only additive changes)
- New private fields (`baseUrl`, `authHeaders`) don't affect the public interface
- All 37 pre-existing tests continue to pass alongside 40 new tests (77 total)

### 10. Code Quality -- PASS

- TypeScript compiles without errors (`tsc --noEmit` clean)
- Consistent coding style with existing codebase
- Proper use of `encodeURIComponent` for URL parameters
- `URLSearchParams` used for query string construction in `listBatches`
- `globalThis.Response` type annotation for cross-environment compatibility
- Error handler uses `Promise<never>` return type for exhaustiveness
- Section comments (`// -- Batch operations --`) consistent with existing code organization

## Recommendations

1. **Minor style nit**: In the constructor (lines 148-152), the platform-mode condition `platformToken && !options.apiKey` is duplicated from the earlier auth resolution block (line 121). Consider extracting a local `isPlatformMode` boolean to reduce duplication, though this is cosmetic and not a correctness issue.

2. **Consider adding a `no-body` guard for GET requests**: The `batchRequest` helper always sets `Content-Type: application/json` even for GET requests that have no body. While this is harmless, some proxies or servers may be strict about it. A minor improvement would be to only set `Content-Type` when there's a body.

3. **Test for `listBatches` with `limit: 0`**: The spec tests `limit: 10` but not edge cases like `limit: 0`. The current implementation handles this correctly (since `0 !== undefined`), but an explicit test would document the behavior.

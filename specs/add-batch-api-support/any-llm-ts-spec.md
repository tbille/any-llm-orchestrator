# Implementation Spec: any-llm-ts

## Context

The any-llm-ts TypeScript SDK provides a `GatewayClient` class that communicates with the any-llm gateway. It currently supports completions, responses, embeddings, and model listing, all delegated through the OpenAI Node.js SDK client. This work adds five batch methods to `GatewayClient`. Unlike existing methods (which delegate to `this.openai.*`), batch methods use direct HTTP calls via `fetch` because the gateway's batch API uses a custom JSON format (not the OpenAI file-upload format).

## Shared Interface Contract

### Gateway Batch HTTP Endpoints

| Endpoint | HTTP Method | Request | Response |
|----------|------------|---------|----------|
| `POST /v1/batches` | POST | JSON body: `CreateBatchParams` | `Batch` JSON + `provider` field |
| `GET /v1/batches/{id}?provider=X` | GET | Query param | `Batch` JSON |
| `POST /v1/batches/{id}/cancel?provider=X` | POST | Query param | `Batch` JSON |
| `GET /v1/batches?provider=X&after=Y&limit=N` | GET | Query params | `{"data": [Batch]}` |
| `GET /v1/batches/{id}/results?provider=X` | GET | Query param | `BatchResult` JSON |

### Create Batch Request Body

```json
{
  "model": "openai:gpt-4o-mini",
  "requests": [
    {"custom_id": "req-1", "body": {"messages": [...], "max_tokens": 100}}
  ],
  "completion_window": "24h",
  "metadata": {"key": "value"}
}
```

### Batch Response (JSON)

Standard OpenAI `Batch` type plus a `provider` string field:
```json
{
  "id": "batch_abc123",
  "object": "batch",
  "endpoint": "/v1/chat/completions",
  "status": "validating",
  "created_at": 1714502400,
  "completion_window": "24h",
  "request_counts": {"total": 2, "completed": 0, "failed": 0},
  "metadata": {},
  "provider": "openai"
}
```

### BatchResult Response (JSON)

```json
{
  "results": [
    {"custom_id": "req-1", "result": { /* ChatCompletion */ }, "error": null},
    {"custom_id": "req-2", "result": null, "error": {"code": "rate_limit", "message": "..."}}
  ]
}
```

### Error Responses

| HTTP Status | Meaning | TypeScript Error |
|-------------|---------|-----------------|
| 401/403 | Auth failure | `AuthenticationError` |
| 404 | Batch not found / gateway too old | `AnyLLMError` with upgrade hint |
| 409 | Batch not complete | `BatchNotCompleteError` (new) |
| 422 | Unsupported provider | `AnyLLMError` |
| 429 | Rate limited | `RateLimitError` |
| 502 | Upstream error | `UpstreamProviderError` |
| 504 | Timeout | `GatewayTimeoutError` |

### Authentication

The `X-AnyLLM-Key: Bearer <key>` header (non-platform mode) or `Authorization: Bearer <token>` (platform mode), consistent with existing `GatewayClient` auth.

## Changes Required

### 1. New types in `src/types.ts`

```typescript
// Re-export Batch from openai
export type { Batch } from "openai/resources/batches";

// New batch-specific types
export interface BatchRequestItem {
  custom_id: string;
  body: Record<string, unknown>;
}

export interface CreateBatchParams {
  model: string;
  requests: BatchRequestItem[];
  completion_window?: string;
  metadata?: Record<string, string>;
}

export interface ListBatchesOptions {
  after?: string;
  limit?: number;
}

export interface BatchResultError {
  code: string;
  message: string;
}

export interface BatchResultItem {
  custom_id: string;
  result?: ChatCompletion;
  error?: BatchResultError;
}

export interface BatchResult {
  results: BatchResultItem[];
}
```

### 2. New error class in `src/errors.ts`

```typescript
export class BatchNotCompleteError extends AnyLLMError {
  static override defaultMessage = "Batch is not yet complete";
  readonly batchId?: string;
  readonly batchStatus?: string;

  constructor(
    options: AnyLLMErrorOptions & { batchId?: string; batchStatus?: string } = {},
  ) {
    super(options);
    this.batchId = options.batchId;
    this.batchStatus = options.batchStatus;
  }
}
```

### 3. Private properties on `GatewayClient` (`src/client.ts`)

The batch methods need direct HTTP access (not through `this.openai`). Store the base URL and auth headers as private fields during construction:

```typescript
private readonly baseUrl: string;        // The resolved base URL (with /v1)
private readonly authHeaders: Record<string, string>;  // Auth headers for batch calls
```

In the constructor, after resolving the base URL and auth mode:

```typescript
// Store for batch method direct HTTP calls
this.baseUrl = resolvedBaseUrl;  // e.g. "http://localhost:8000/v1"
this.authHeaders = {};
if (isPlatformMode) {
  this.authHeaders["Authorization"] = `Bearer ${platformToken}`;
} else if (apiKey) {
  this.authHeaders[GATEWAY_HEADER_NAME] = `Bearer ${apiKey}`;
}
// Merge any defaultHeaders
if (options.defaultHeaders) {
  Object.assign(this.authHeaders, options.defaultHeaders);
}
```

**Note**: The constructor already resolves `resolvedBaseUrl`, `apiKey`, and platform mode. This just stores those values for batch use. The `this.openai` client continues to work as before for existing methods.

### 4. New batch methods on `GatewayClient` (`src/client.ts`)

```typescript
/**
 * Create a batch job.
 *
 * @param params - Batch creation parameters including model and requests array.
 * @returns The created batch object.
 */
async createBatch(params: CreateBatchParams): Promise<Batch> {
  return this.batchRequest<Batch>("POST", "/batches", { body: params });
}

/**
 * Retrieve the status of a batch job.
 *
 * @param batchId - The ID of the batch to retrieve.
 * @param provider - The provider name (e.g., "openai").
 * @returns The batch object with current status.
 */
async retrieveBatch(batchId: string, provider: string): Promise<Batch> {
  return this.batchRequest<Batch>(
    "GET",
    `/batches/${encodeURIComponent(batchId)}?provider=${encodeURIComponent(provider)}`,
  );
}

/**
 * Cancel a batch job.
 *
 * @param batchId - The ID of the batch to cancel.
 * @param provider - The provider name (e.g., "openai").
 * @returns The batch object with updated status.
 */
async cancelBatch(batchId: string, provider: string): Promise<Batch> {
  return this.batchRequest<Batch>(
    "POST",
    `/batches/${encodeURIComponent(batchId)}/cancel?provider=${encodeURIComponent(provider)}`,
  );
}

/**
 * List batch jobs for a provider.
 *
 * @param provider - The provider name (e.g., "openai").
 * @param options - Optional pagination parameters.
 * @returns Array of batch objects.
 */
async listBatches(provider: string, options?: ListBatchesOptions): Promise<Batch[]> {
  const params = new URLSearchParams({ provider });
  if (options?.after) params.set("after", options.after);
  if (options?.limit !== undefined) params.set("limit", String(options.limit));
  const response = await this.batchRequest<{ data: Batch[] }>(
    "GET",
    `/batches?${params.toString()}`,
  );
  return response.data;
}

/**
 * Retrieve the results of a completed batch job.
 *
 * @param batchId - The ID of the batch to retrieve results for.
 * @param provider - The provider name (e.g., "openai").
 * @returns The batch results containing per-request outcomes.
 * @throws {BatchNotCompleteError} If the batch is not yet complete.
 */
async retrieveBatchResults(batchId: string, provider: string): Promise<BatchResult> {
  return this.batchRequest<BatchResult>(
    "GET",
    `/batches/${encodeURIComponent(batchId)}/results?provider=${encodeURIComponent(provider)}`,
  );
}
```

### 5. Private HTTP helper on `GatewayClient`

```typescript
/**
 * Make a direct HTTP request for batch operations.
 * Unlike completion/embedding methods which use this.openai, batch methods
 * use direct fetch because the gateway batch API has a custom JSON format.
 */
private async batchRequest<T = unknown>(
  method: string,
  path: string,
  options?: { body?: unknown },
): Promise<T> {
  const url = `${this.baseUrl}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...this.authHeaders,
  };

  const response = await fetch(url, {
    method,
    headers,
    body: options?.body ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    await this.handleBatchError(response);
  }

  return (await response.json()) as T;
}
```

### 6. Batch error handler on `GatewayClient`

```typescript
/**
 * Map batch HTTP errors to typed SDK errors.
 * This is used by batch methods which use direct fetch (not this.openai).
 */
private async handleBatchError(response: globalThis.Response): Promise<never> {
  const body = await response.json().catch(() => ({}));
  const detail = (body as Record<string, unknown>)?.detail ?? response.statusText;
  const message = typeof detail === "string" ? detail : response.statusText;
  const correlationId = response.headers.get("x-correlation-id");
  const fullMessage = correlationId
    ? `${message} (correlation_id=${correlationId})`
    : message;

  switch (response.status) {
    case 401:
    case 403:
      throw new AuthenticationError({
        message: fullMessage,
        statusCode: response.status,
        providerName: PROVIDER_NAME,
      });
    case 404:
      throw new AnyLLMError({
        message: fullMessage.includes("not found")
          ? fullMessage
          : `This gateway does not support batch operations. Upgrade your gateway. (${fullMessage})`,
        statusCode: 404,
        providerName: PROVIDER_NAME,
      });
    case 409:
      throw new BatchNotCompleteError({
        message: fullMessage,
        statusCode: 409,
        providerName: PROVIDER_NAME,
        batchId: extractBatchId(message),
        batchStatus: extractStatus(message),
      });
    case 422:
      throw new AnyLLMError({
        message: fullMessage,
        statusCode: 422,
        providerName: PROVIDER_NAME,
      });
    case 429:
      throw new RateLimitError({
        message: fullMessage,
        statusCode: 429,
        providerName: PROVIDER_NAME,
        retryAfter: response.headers.get("retry-after") ?? undefined,
      });
    case 502:
      throw new UpstreamProviderError({
        message: fullMessage,
        statusCode: 502,
        providerName: PROVIDER_NAME,
      });
    case 504:
      throw new GatewayTimeoutError({
        message: fullMessage,
        statusCode: 504,
        providerName: PROVIDER_NAME,
      });
    default:
      throw new AnyLLMError({
        message: fullMessage,
        statusCode: response.status,
        providerName: PROVIDER_NAME,
      });
  }
}
```

**Helper functions** (module-level or private):

```typescript
function extractBatchId(message: string): string | undefined {
  // Parse: "Batch 'batch_abc' is not yet complete..."
  const match = message.match(/Batch '([^']+)'/);
  return match?.[1];
}

function extractStatus(message: string): string | undefined {
  // Parse: "...(status: in_progress)..."
  const match = message.match(/status: (\w+)/);
  return match?.[1];
}
```

### 7. Updated exports in `src/index.ts`

Add to class exports:
```typescript
export { BatchNotCompleteError } from "./errors.js";
```

Add to type-only exports:
```typescript
export type {
  Batch,
  BatchRequestItem,
  BatchResult,
  BatchResultError,
  BatchResultItem,
  CreateBatchParams,
  ListBatchesOptions,
} from "./types.js";
```

## Implementation Steps

1. Add batch types to `src/types.ts` (`Batch` re-export, `BatchRequestItem`, `CreateBatchParams`, `ListBatchesOptions`, `BatchResult`, `BatchResultItem`, `BatchResultError`).
2. Add `BatchNotCompleteError` class to `src/errors.ts`.
3. Add `baseUrl` and `authHeaders` private properties to `GatewayClient` constructor.
4. Add the `batchRequest` private helper method.
5. Add the `handleBatchError` private method.
6. Add all five public batch methods (`createBatch`, `retrieveBatch`, `cancelBatch`, `listBatches`, `retrieveBatchResults`).
7. Update `src/index.ts` exports.
8. Write unit tests.
9. Write integration tests (if test infrastructure supports live gateway).

## Testing Requirements

### Unit Tests (`tests/unit/client.test.ts`, extend existing)

Follow the existing vitest pattern with `vi.spyOn` and mock responses.

**New describe block: "GatewayClient batch methods"**

Since batch methods use `fetch` directly (not `this.openai`), tests should mock `global.fetch`:

```typescript
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);
```

**Tests:**

- **`createBatch sends correct request`**: Verify POST to `${baseUrl}/batches` with JSON body, correct auth headers.
- **`createBatch returns Batch object`**: Mock 200 response with Batch JSON.
- **`retrieveBatch sends provider query param`**: Verify GET URL includes `?provider=openai`.
- **`cancelBatch sends correct request`**: Verify POST to `/batches/{id}/cancel?provider=...`.
- **`listBatches sends pagination params`**: Verify `?provider=openai&after=cursor&limit=10`.
- **`listBatches returns array of Batch`**: Mock 200 with `{"data": [...]}`.
- **`retrieveBatchResults returns BatchResult`**: Mock 200 with BatchResult JSON.

**Error handling tests:**

- **`batch 409 throws BatchNotCompleteError`**: Mock 409, verify error type, `batchId`, `batchStatus`.
- **`batch 404 throws with upgrade message`**: Mock 404, verify error message mentions "upgrade".
- **`batch 401 throws AuthenticationError`**: Mock 401.
- **`batch 429 throws RateLimitError with retryAfter`**: Mock 429 with `retry-after` header.
- **`batch 502 throws UpstreamProviderError`**: Mock 502.
- **`batch 504 throws GatewayTimeoutError`**: Mock 504.

**Auth tests:**

- **`batch methods use X-AnyLLM-Key header (non-platform)`**: Verify header in fetch call.
- **`batch methods use Authorization header (platform mode)`**: Verify header in fetch call.

**New describe block: "GatewayClient batch error class"** (in `tests/unit/errors.test.ts`):

- **`BatchNotCompleteError has correct defaultMessage`**.
- **`BatchNotCompleteError stores batchId and batchStatus`**.
- **`BatchNotCompleteError is instance of AnyLLMError`**.

### Integration Tests

If the project adds an `integration/` test directory, add:
- `batch.test.ts` — Full create → retrieve → cancel flow against live gateway.

## Acceptance Criteria

1. `GatewayClient.createBatch()` sends a POST to `/v1/batches` with JSON body and correct auth.
2. `GatewayClient.retrieveBatch()` sends a GET with `?provider=` query param.
3. `GatewayClient.cancelBatch()` sends a POST with `?provider=` query param.
4. `GatewayClient.listBatches()` sends a GET with `?provider=`, `?after=`, `?limit=` params.
5. `GatewayClient.retrieveBatchResults()` returns a properly typed `BatchResult`.
6. 409 responses produce `BatchNotCompleteError` with `batchId` and `batchStatus`.
7. 404 responses on batch endpoints suggest gateway upgrade.
8. All types (`Batch`, `BatchResult`, `CreateBatchParams`, etc.) are exported from the package.
9. `BatchNotCompleteError` is exported and works with `instanceof`.
10. All existing tests continue to pass (no regression).
11. Both platform and non-platform auth modes work for batch methods.

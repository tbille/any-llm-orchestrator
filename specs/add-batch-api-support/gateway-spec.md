# Implementation Spec: gateway

## Context

The gateway is a FastAPI service that proxies LLM requests through the any-llm Python SDK. It currently has endpoints for chat completions, messages, responses, embeddings, and models, but no batch endpoints. This work adds five batch endpoints under `/v1/batches` that accept JSON requests, delegate to the Python SDK's batch methods, and return normalized responses. The gateway acts as a thin proxy: it does not store batch state, only passes through to providers.

## Shared Interface Contract

### Gateway Batch API Endpoints

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

**Pydantic request model:**
```python
class BatchRequestItem(BaseModel):
    custom_id: str
    body: dict[str, Any]

class CreateBatchRequest(BaseModel):
    model: str  # "provider:model" format
    requests: list[BatchRequestItem] = Field(min_length=1, max_length=10_000)
    completion_window: str = "24h"
    metadata: dict[str, str] | None = None
```

**Response: `200 OK`** — JSON with all `Batch` fields plus a `provider` field:
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

#### `GET /v1/batches/{batch_id}?provider={provider}` — Retrieve batch status

**Query params:** `provider` (required)
**Response: `200 OK`** — `Batch` object JSON.

#### `POST /v1/batches/{batch_id}/cancel?provider={provider}` — Cancel a batch

**Query params:** `provider` (required)
**Response: `200 OK`** — `Batch` object JSON.

#### `GET /v1/batches?provider={provider}&after={cursor}&limit={n}` — List batches

**Query params:** `provider` (required), `after` (optional), `limit` (optional)
**Response: `200 OK`** — `{"data": [Batch, ...]}`

#### `GET /v1/batches/{batch_id}/results?provider={provider}` — Retrieve results

**Query params:** `provider` (required)
**Response: `200 OK`** — `BatchResult` JSON:
```json
{
  "results": [
    {
      "custom_id": "req-1",
      "result": { /* ChatCompletion */ },
      "error": null
    },
    {
      "custom_id": "req-2",
      "result": null,
      "error": {"code": "rate_limit", "message": "Rate limit exceeded"}
    }
  ]
}
```
**Error: `409 Conflict`** — If batch not completed:
```json
{
  "detail": "Batch 'batch_abc123' is not yet complete (status: in_progress). Call GET /v1/batches/batch_abc123?provider=openai to check the current status."
}
```

#### Error Responses

| HTTP Code | Condition | Example `detail` |
|-----------|-----------|-----------------|
| 400 | Missing/invalid field | `"Invalid request: model is required"` |
| 401/403 | Auth failure | Existing auth error behavior |
| 404 | Batch not found | `"Batch 'batch_xyz' not found for provider 'openai'"` |
| 409 | Batch not complete | See above |
| 413 | Too many requests in array | `"Requests array exceeds maximum size of 10,000 items"` |
| 422 | Provider doesn't support batch | `"Provider 'ollama' does not support batch operations"` |
| 502 | Upstream provider error | `"LLM provider error"` |

### Types from Python SDK (used by the gateway)

The gateway imports these from `any_llm`:
- `Batch` (from `any_llm.types.batch`)
- `BatchResult`, `BatchResultItem`, `BatchResultError` (from `any_llm.types.batch`)
- `BatchNotCompleteError` (from `any_llm.exceptions`)
- `acreate_batch`, `aretrieve_batch`, `acancel_batch`, `alist_batches`, `aretrieve_batch_results` (from `any_llm.api`)

## Changes Required

### 1. New route file: `src/gateway/api/routes/batches.py`

Create a new route module following the pattern established by `chat.py`, `embeddings.py`, and `responses.py`.

**Router:**
```python
router = APIRouter(prefix="/v1/batches", tags=["batches"])
```

**Pydantic request models** (defined at the top of the file):

```python
class BatchRequestItem(BaseModel):
    custom_id: str
    body: dict[str, Any]

class CreateBatchRequest(BaseModel):
    model: str
    requests: list[BatchRequestItem] = Field(min_length=1, max_length=10_000)
    completion_window: str = "24h"
    metadata: dict[str, str] | None = None
```

**Pydantic response models** (for OpenAPI doc generation):

```python
class BatchResultErrorResponse(BaseModel):
    code: str
    message: str

class BatchResultItemResponse(BaseModel):
    custom_id: str
    result: dict[str, Any] | None = None
    error: BatchResultErrorResponse | None = None

class BatchResultResponse(BaseModel):
    results: list[BatchResultItemResponse]
```

### 2. Route handler: `POST /v1/batches` (create)

```python
@router.post("", response_model=None)
async def create_batch(
    raw_request: Request,
    background_tasks: BackgroundTasks,
    request: CreateBatchRequest,
    db: Annotated[AsyncSession | None, Depends(get_db_if_needed)],
    config: Annotated[GatewayConfig, Depends(get_config)],
    log_writer: Annotated[LogWriter, Depends(get_log_writer)],
) -> dict[str, Any]:
```

**Implementation flow:**
1. Auth: `api_key, is_master_key = await verify_api_key_or_master_key(raw_request, db, config)`
2. Parse provider: `provider, model = AnyLLM.split_model_provider(request.model)`
3. Validate provider supports batch:
   ```python
   provider_class = AnyLLM.get_provider_class(provider)
   if not getattr(provider_class, "SUPPORTS_BATCH", False):
       raise HTTPException(422, detail=f"Provider '{provider.value}' does not support batch operations")
   ```
4. Get provider kwargs: `provider_kwargs = get_provider_kwargs(config, provider)`
5. Build JSONL temp file from `request.requests`:
   ```python
   import tempfile
   import json

   with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp:
       for req_item in request.requests:
           line = {
               "custom_id": req_item.custom_id,
               "method": "POST",
               "url": "/v1/chat/completions",
               "body": {**req_item.body, "model": model},
           }
           tmp.write(json.dumps(line) + "\n")
       tmp_path = tmp.name
   ```
6. Call SDK:
   ```python
   try:
       batch = await acreate_batch(
           provider=provider,
           input_file_path=tmp_path,
           endpoint="/v1/chat/completions",
           completion_window=request.completion_window,
           metadata=request.metadata,
           **provider_kwargs,
       )
   finally:
       os.unlink(tmp_path)  # cleanup temp file
   ```
7. Log usage (in background or inline):
   ```python
   await log_batch_usage(
       db=db, log_writer=log_writer,
       api_key_id=api_key.id if api_key else None,
       model=model, provider=provider.value,
       endpoint="/v1/batches", user_id=user_id,
   )
   ```
8. Return response with injected `provider` field:
   ```python
   response_data = batch.model_dump()
   response_data["provider"] = provider.value
   return response_data
   ```

### 3. Route handler: `GET /v1/batches/{batch_id}` (retrieve)

```python
@router.get("/{batch_id}", response_model=None)
async def retrieve_batch(
    batch_id: str,
    provider: str,  # query param, required
    raw_request: Request,
    db: Annotated[AsyncSession | None, Depends(get_db_if_needed)],
    config: Annotated[GatewayConfig, Depends(get_config)],
) -> dict[str, Any]:
```

**Implementation:**
1. Auth
2. Resolve provider enum: `provider_enum = LLMProvider.from_string(provider)`
3. Get provider kwargs
4. Call SDK: `batch = await aretrieve_batch(provider=provider_enum, batch_id=batch_id, **provider_kwargs)`
5. Return `batch.model_dump()`

### 4. Route handler: `POST /v1/batches/{batch_id}/cancel` (cancel)

```python
@router.post("/{batch_id}/cancel", response_model=None)
async def cancel_batch(
    batch_id: str,
    provider: str,  # query param
    raw_request: Request,
    db: Annotated[AsyncSession | None, Depends(get_db_if_needed)],
    config: Annotated[GatewayConfig, Depends(get_config)],
) -> dict[str, Any]:
```

Similar pattern to retrieve.

### 5. Route handler: `GET /v1/batches` (list)

```python
@router.get("", response_model=None)
async def list_batches(
    provider: str,  # query param
    raw_request: Request,
    db: Annotated[AsyncSession | None, Depends(get_db_if_needed)],
    config: Annotated[GatewayConfig, Depends(get_config)],
    after: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
```

Returns `{"data": [batch.model_dump() for batch in batches]}`.

### 6. Route handler: `GET /v1/batches/{batch_id}/results` (results)

```python
@router.get("/{batch_id}/results", response_model=None)
async def retrieve_batch_results(
    batch_id: str,
    provider: str,  # query param
    raw_request: Request,
    db: Annotated[AsyncSession | None, Depends(get_db_if_needed)],
    config: Annotated[GatewayConfig, Depends(get_config)],
    log_writer: Annotated[LogWriter, Depends(get_log_writer)],
) -> dict[str, Any]:
```

**Implementation:**
1. Auth
2. Resolve provider, get kwargs
3. Call SDK:
   ```python
   try:
       result = await aretrieve_batch_results(provider=provider_enum, batch_id=batch_id, **provider_kwargs)
   except BatchNotCompleteError as e:
       raise HTTPException(
           status_code=409,
           detail=f"Batch '{batch_id}' is not yet complete (status: {e.batch_status}). "
                  f"Call GET /v1/batches/{batch_id}?provider={provider} to check the current status.",
       ) from e
   ```
4. Serialize `BatchResult` to JSON:
   ```python
   return {
       "results": [
           {
               "custom_id": item.custom_id,
               "result": item.result.model_dump() if item.result else None,
               "error": {"code": item.error.code, "message": item.error.message} if item.error else None,
           }
           for item in result.results
       ]
   }
   ```
5. Log usage for result retrieval.

### 7. Error handling pattern

Follow the established pattern from `chat.py`:

```python
try:
    # SDK call
except HTTPException:
    raise
except BatchNotCompleteError as e:
    raise HTTPException(status_code=409, detail=str(e)) from e
except Exception as e:
    logger.error("Batch operation failed for %s: %s", provider, e)
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="LLM provider error",
    ) from e
```

### 8. Register the router

**File**: `src/gateway/api/main.py`

Add the import and registration:

```python
from gateway.api.routes import batches  # add to imports

# In register_routers(), after embeddings.router and before models.router:
app.include_router(batches.router)
```

The batches router should be registered in standalone mode only (not in platform mode), consistent with other LLM proxy endpoints.

### 9. Update `src/gateway/api/routes/__init__.py`

Add `batches` to the `__init__.py` if it uses explicit imports (check existing pattern).

### 10. Usage logging

Create a simplified `log_batch_usage` function in `batches.py` (or reuse/adapt `log_usage` from `chat.py`):

```python
async def log_batch_usage(
    db: AsyncSession,
    log_writer: LogWriter,
    api_key_id: str | None,
    model: str,
    provider: str,
    endpoint: str,
    user_id: str | None = None,
    error: str | None = None,
) -> None:
    usage_log = UsageLog(
        id=str(uuid.uuid4()),
        api_key_id=api_key_id,
        user_id=user_id,
        timestamp=datetime.now(UTC),
        model=model,
        provider=provider,
        endpoint=endpoint,
        status="success" if error is None else "error",
        error_message=error,
    )
    await log_writer.put(usage_log)
```

Token counts and cost are not available at batch creation time. They could be logged at result retrieval time if `BatchResult` items contain usage data, but this is deferred for simplicity.

### 11. Regenerate OpenAPI spec

After adding the routes, run:
```bash
uv run python scripts/generate_openapi.py
```

This updates `docs/public/openapi.json` automatically. The CI check (`--check` flag) will fail until this is regenerated.

### 12. Update `pyproject.toml` dependency

Once the Python SDK is released with batch result types, pin the minimum version:
```toml
any-llm-sdk[all] >= <new-version>
```

## Implementation Steps

1. Create `src/gateway/api/routes/batches.py` with the Pydantic models and router.
2. Implement the `POST /v1/batches` handler (create), including JSONL temp file construction and cleanup.
3. Implement the `GET /v1/batches/{batch_id}` handler (retrieve).
4. Implement the `POST /v1/batches/{batch_id}/cancel` handler (cancel).
5. Implement the `GET /v1/batches` handler (list).
6. Implement the `GET /v1/batches/{batch_id}/results` handler (results), including `BatchNotCompleteError` → 409 mapping.
7. Add `log_batch_usage` helper function.
8. Register the router in `src/gateway/api/main.py`.
9. Write unit tests and integration tests.
10. Regenerate `docs/public/openapi.json`.
11. Update `pyproject.toml` to pin the new SDK version.

## Testing Requirements

### Unit Tests

**`tests/unit/test_batches_route.py`** (new file):
- Test `CreateBatchRequest` Pydantic validation:
  - Valid request passes
  - Empty `requests` array rejected (`min_length=1`)
  - More than 10,000 items rejected (`max_length=10_000`)
  - Missing `model` rejected
  - Missing `custom_id` in request item rejected

### Integration Tests

**`tests/integration/test_batches_endpoint.py`** (new file):

Follow the pattern from `test_embeddings_endpoint.py`: mock the SDK call, use the test client.

- **`test_create_batch_with_api_key`**: Mock `acreate_batch`, verify correct SDK call, verify response includes `provider` field.
- **`test_create_batch_with_master_key`**: Same with master key auth.
- **`test_create_batch_auth_required`**: No auth header → 401.
- **`test_create_batch_unsupported_provider`**: Mock provider class with `SUPPORTS_BATCH = False` → 422.
- **`test_create_batch_invalid_model_format`**: No colon in model → appropriate error.
- **`test_create_batch_empty_requests`**: Empty array → 422 (Pydantic validation).
- **`test_create_batch_provider_error`**: Mock SDK raises exception → 502.
- **`test_retrieve_batch`**: Mock `aretrieve_batch`, verify `?provider=` is passed.
- **`test_retrieve_batch_missing_provider`**: No provider query param → 422 (FastAPI validation).
- **`test_cancel_batch`**: Mock `acancel_batch`, verify behavior.
- **`test_list_batches`**: Mock `alist_batches`, verify pagination params forwarded.
- **`test_retrieve_batch_results`**: Mock `aretrieve_batch_results`, verify `BatchResult` serialized correctly.
- **`test_retrieve_batch_results_not_complete`**: Mock raises `BatchNotCompleteError` → 409 with descriptive detail.
- **`test_batch_endpoints_not_in_platform_mode`**: Verify batch endpoints return 404 in platform mode (if not registered).
- **`test_create_batch_logs_usage`**: Verify `UsageLog` is created after successful batch creation.
- **`test_batch_temp_file_cleanup`**: Verify temp file is removed after `acreate_batch` (even on error).

## Acceptance Criteria

1. All five batch endpoints respond correctly and appear in the OpenAPI spec.
2. `POST /v1/batches` accepts a JSON body with `model`, `requests`, constructs a JSONL temp file, calls the SDK, and cleans up the temp file.
3. All batch endpoints require authentication (`verify_api_key_or_master_key`).
4. `GET /v1/batches/{id}/results` returns 409 with descriptive message when batch is not complete.
5. Provider validation rejects providers without `SUPPORTS_BATCH = True` with 422.
6. The `provider` field is injected into the create batch response.
7. Usage is logged for batch create and result retrieval operations.
8. Existing endpoints are unaffected.
9. `docs/public/openapi.json` is regenerated and passes `--check`.
10. All integration tests pass with mocked SDK calls.

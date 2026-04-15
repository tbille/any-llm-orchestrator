# Gateway Batch API Review

## Status: NEEDS_CHANGES

## Summary

The implementation adds five batch endpoints under `/v1/batches` to the gateway. The overall structure is solid: Pydantic models, router registration, auth, error handling, usage logging, and tests all follow established codebase patterns. However, the `GET /v1/batches/{batch_id}/results` endpoint diverges significantly from the spec, and there are a few smaller gaps.

All 340 tests pass (331 passed, 9 skipped), the OpenAPI spec is regenerated and passes `--check`, and ruff reports no lint issues.

## Issues Found

### 1. CRITICAL: `retrieve_batch_results` does not use `aretrieve_batch_results` SDK function (Spec Non-Compliance)

**File:** `src/gateway/api/routes/batches.py:278-318`

The spec requires the results endpoint to call `aretrieve_batch_results` from `any_llm.api` and return a `BatchResult` object serialized as:

```json
{
  "results": [
    {"custom_id": "req-1", "result": { ... }, "error": null},
    {"custom_id": "req-2", "result": null, "error": {"code": "...", "message": "..."}}
  ]
}
```

Instead, the implementation calls `aretrieve_batch` (the status endpoint), checks `batch.status != "completed"`, and returns `batch.model_dump()` directly. This returns the batch metadata (id, status, request_counts, etc.) rather than the actual per-request results.

The spec also requires handling `BatchNotCompleteError` from `any_llm.exceptions`, but neither `aretrieve_batch_results` nor `BatchNotCompleteError` are imported.

**Root cause:** The SDK does not yet export `aretrieve_batch_results`, `BatchNotCompleteError`, `BatchResult`, `BatchResultItem`, or `BatchResultError`. These types are not available in the installed `any_llm` package:
- `any_llm.api` exports: `acreate_batch`, `aretrieve_batch`, `acancel_batch`, `alist_batches` (but NOT `aretrieve_batch_results`)
- `any_llm.types.batch` exports: `Batch`, `BatchRequestCounts`, `OpenAIBatch`, `OpenAIBatchRequestCounts` (but NOT `BatchResult`, `BatchResultItem`, `BatchResultError`)
- `any_llm.exceptions` does NOT export `BatchNotCompleteError`

The implementation worked around the missing SDK functions by using `aretrieve_batch` as a fallback, but the response shape is wrong and the Pydantic response models (`BatchResultResponse`, `BatchResultItemResponse`, `BatchResultErrorResponse`) defined in the file are unused.

**Impact:** The `/v1/batches/{batch_id}/results` endpoint returns batch metadata instead of actual per-request results, making it functionally equivalent to `GET /v1/batches/{batch_id}` with an added status check.

### 2. MEDIUM: `log_batch_usage` omits the `db` parameter (Spec Divergence)

**File:** `src/gateway/api/routes/batches.py:69-90`

The spec defines `log_batch_usage` with a `db: AsyncSession` parameter:

```python
async def log_batch_usage(db: AsyncSession, log_writer: LogWriter, ...)
```

The implementation omits `db` entirely. While the current `log_writer.put()` does not require a direct `db` reference (the `LogWriter` handles persistence internally), the spec explicitly includes it for consistency with `log_usage` in `chat.py`. This is a minor divergence since the function works correctly without it.

### 3. MEDIUM: Uses `get_db` instead of `get_db_if_needed` (Spec Divergence)

**File:** `src/gateway/api/routes/batches.py:103, 185, 216, 247, 285`

The spec calls for `Depends(get_db_if_needed)` which returns `AsyncSession | None`. The implementation uses `Depends(get_db)` which always returns `AsyncSession`. Since batch routes are only registered in standalone mode (not platform mode), this works correctly in practice. However, the spec explicitly requested `get_db_if_needed` for consistency. Using `get_db` is arguably more appropriate here since the routes are standalone-only.

### 4. LOW: `retrieve_batch_results` does not log usage (Spec Non-Compliance)

**File:** `src/gateway/api/routes/batches.py:278-318`

The spec states: "Log usage for result retrieval." The `log_writer` dependency is injected but never used in the `retrieve_batch_results` handler. The `create_batch` handler correctly logs usage on both success and error paths.

### 5. LOW: Missing integration test `test_create_batch_invalid_model_format` (Test Coverage Gap)

**File:** `tests/integration/test_batches_endpoint.py`

The spec lists `test_create_batch_invalid_model_format` as a required test: "No colon in model -> appropriate error." This test is not present in the integration test file. The behavior depends on how `AnyLLM.split_model_provider` handles malformed model strings, which could raise an unhandled exception resulting in a 500 instead of a clear 400/422.

### 6. LOW: Deprecation warning for `HTTP_422_UNPROCESSABLE_ENTITY`

**File:** `src/gateway/api/routes/batches.py:118`

The test output shows a `DeprecationWarning`: `'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.` The code uses `status.HTTP_422_UNPROCESSABLE_ENTITY` which is deprecated in newer FastAPI/Starlette versions.

### 7. LOW: `Batch` import from `any_llm.types.batch` is unused in type annotations

**File:** `src/gateway/api/routes/batches.py:12`

`Batch` is imported from `any_llm.types.batch` and used only as inline type annotations (`batch: Batch`). This is fine for runtime type hints but could be moved under `TYPE_CHECKING` following the pattern in `_helpers.py`. Minor style point.

## Recommendations

1. **Regarding the results endpoint (Issue 1):** This is a hard dependency on the SDK releasing `aretrieve_batch_results` and related types. Two options:
   - **(a)** Leave a clear `TODO` / `FIXME` comment explaining the workaround and add a tracking issue. Update the endpoint once the SDK ships the function.
   - **(b)** If the SDK release is imminent, block this PR until the SDK is updated, then implement the endpoint per spec.
   
   Either way, the test `test_retrieve_batch_results` should be updated to document that it's testing the workaround behavior, not the spec-intended behavior.

2. **Add the missing `test_create_batch_invalid_model_format` test** to verify graceful handling of malformed model strings (e.g., `"gpt-4o-mini"` without a provider prefix). If this currently results in a 500, add error handling to return 400/422.

3. **Add usage logging to `retrieve_batch_results`** as the spec requires, even with the current workaround implementation.

4. **Replace `HTTP_422_UNPROCESSABLE_ENTITY` with `HTTP_422_UNPROCESSABLE_CONTENT`** to silence the deprecation warning.

5. **Pin `any-llm-sdk` minimum version** in `pyproject.toml` once the batch types SDK release is available: `"any-llm-sdk[all]>=<version-with-batch-support>"`.

6. The `get_db` vs `get_db_if_needed` choice (Issue 3) is acceptable as-is since batch routes are standalone-only. No change needed unless the architecture changes.

## What Works Well

- **Router registration:** Correctly placed in standalone mode only, after `embeddings.router` and before `models.router`.
- **Auth pattern:** Uses `Annotated[..., Depends(verify_api_key_or_master_key)]` consistently, matching the cleaner pattern from `embeddings.py`.
- **JSONL temp file construction and cleanup:** Properly uses `tempfile.NamedTemporaryFile(delete=False)` with `os.unlink` in a `finally` block, ensuring cleanup even on SDK errors.
- **Error handling:** Follows the established `except HTTPException: raise` / `except Exception` / 502 pattern from `chat.py`.
- **Provider validation:** Correctly checks `SUPPORTS_BATCH` attribute with `getattr` fallback.
- **Test coverage:** 8 unit tests and 15 integration tests cover auth, provider validation, pagination, error paths, temp file cleanup, usage logging, and platform mode exclusion.
- **OpenAPI spec:** Regenerated and passes `--check`.
- **Code quality:** Clean imports, proper typing, consistent naming, concise docstrings.
- **All 340 tests pass** with no regressions.

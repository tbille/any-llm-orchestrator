# Code Review: add-batch-api-support (any-llm)

## Status: NEEDS_CHANGES

## Summary

The implementation covers the vast majority of the spec requirements with good code quality. All 38 new unit tests pass, all 573 existing unit tests pass (1 pre-existing failure in `test_voyage_provider.py` unrelated to these changes), and ruff reports no lint issues. However, there are several issues that need addressing before this is merge-ready.

## Issues Found

### 1. [MEDIUM] Missing integration tests (spec non-compliance)

**Location**: `tests/integration/test_batch.py`

The spec requires the following integration test additions that are entirely missing:

- Anthropic should be added to the parameterized batch create/retrieve/cancel test. Currently the integration test relies on `SUPPORTS_BATCH` to determine which providers are tested, so with Anthropic now having `SUPPORTS_BATCH = True`, it will be picked up automatically, but the `input_file_id` assertion on line 79 (`assert batch.input_file_id is not None`) will fail for Anthropic since it uses `input_file_id=""` (empty string, which is falsy). This needs to be updated to `assert batch.input_file_id is not None or batch.input_file_id == ""` or similar.
- `test_retrieve_batch_results` for OpenAI, Mistral, and Anthropic is missing entirely.
- `test_retrieve_batch_results_not_complete` that verifies `BatchNotCompleteError` is raised for a fresh batch is missing entirely.

### 2. [LOW] Mistral provider uses `response.text` instead of `content.decode()` (spec deviation)

**Location**: `src/any_llm/providers/mistral/mistral.py:318`

The spec says:
```python
content = await self.client.files.download_async(file_id=batch_job.output_file)
...
for line in content.decode().strip().split("\n"):
```

The implementation uses:
```python
response = await self.client.files.download_async(file_id=batch_job.output_file)
...
for line in response.text.strip().split("\n"):
```

The test mocks use `.text`, so tests pass. However, the actual Mistral SDK v2 `files.download_async` may return bytes (as the spec suggests with `.decode()`) or an httpx Response (which has `.text`). This needs verification against the actual Mistral SDK v2 return type. If the SDK returns bytes, this will fail at runtime. The test mock at `tests/unit/providers/test_mistral_batch_results.py:66` uses `mock_response.text` which may not reflect the actual SDK behavior.

### 3. [LOW] `BatchResult.results` field default differs from spec

**Location**: `src/any_llm/types/batch.py:39`

The spec defines:
```python
@dataclass
class BatchResult:
    results: list[BatchResultItem]
```

The implementation uses:
```python
@dataclass
class BatchResult:
    results: list[BatchResultItem] = field(default_factory=list)
```

This is actually an improvement over the spec (allows `BatchResult()` with no args, which is used in `test_batch_result_empty`), but it's a deviation. Since it only adds convenience and doesn't break anything, this is acceptable.

### 4. [LOW] Anthropic batch `input_file_id` uses empty string instead of `None`

**Location**: `src/any_llm/providers/anthropic/base.py:92`

The spec says `input_file_id=None` but the implementation uses `input_file_id=""`. This is actually correct because `Batch.input_file_id` is typed as `str` (not `Optional[str]`) in the OpenAI SDK, so `None` would fail Pydantic validation. The implementation correctly handles this constraint. However, this means the existing integration test assertion `assert batch.input_file_id is not None` at `tests/integration/test_batch.py:79` will pass but is semantically misleading (empty string is not a real file ID).

### 5. [LOW] Gateway `_aretrieve_batch_results` has unused variable

**Location**: `src/any_llm/providers/gateway/gateway.py` (409 response handler)

```python
if response.status_code == 409:
    raise BatchNotCompleteError(
        batch_id=batch_id,
        status="unknown",
        provider_name=self.PROVIDER_NAME,
    )
```

The spec includes `detail = response.json().get("detail", "")` but it's unused in the raise. The implementation correctly omits this dead code, but a more useful approach would be to try parsing the actual status from the response body rather than hardcoding `"unknown"`.

### 6. [LOW] `retrieve_batch_results`/`aretrieve_batch_results` not exported in `api.py`'s public API

**Location**: `src/any_llm/api.py`

The new functions are defined but there's no `__all__` in `api.py` to explicitly export them. This matches the existing pattern (no `__all__` in `api.py`), so it's consistent. However, the spec mentions these should be added to the top-level API. They are not re-exported from `src/any_llm/__init__.py` either (same as other api.py functions, which are accessed via `any_llm.api.retrieve_batch_results`). This is consistent with existing patterns.

### 7. [INFO] Anthropic error access pattern may be fragile

**Location**: `src/any_llm/providers/anthropic/base.py:336-340`

```python
err = entry.result.error
item.error = BatchResultError(
    code=err.error.type if err and err.error else "unknown",
    message=err.error.message if err and err.error else "Unknown error",
)
```

The double-nested `err.error.type` access pattern relies on the Anthropic SDK's specific structure where `result.error` contains an `error` property that itself has `type` and `message`. This is correctly defensive with the `if err and err.error` guard, and matches the spec. No change needed, but worth noting for future SDK version changes.

## Recommendations

### 1. Add missing integration tests (required by spec)

Add the following to `tests/integration/test_batch.py`:
- A `test_retrieve_batch_results_not_complete` test that creates a batch and immediately calls `retrieve_batch_results` to verify `BatchNotCompleteError` is raised.
- Update the `input_file_id` assertion to handle Anthropic's empty string.

### 2. Verify Mistral SDK `files.download_async` return type

Check whether the Mistral SDK v2 returns bytes or an httpx-like response from `files.download_async`. If it returns bytes, the implementation needs `.decode()` instead of `.text`. If it returns an httpx Response, `.text` is correct. Update the mock to match.

### 3. Consider extracting JSONL parsing into a shared utility

The OpenAI, Mistral, and Gateway providers all contain nearly identical JSONL parsing logic for batch results:
```python
for line in content.text.strip().split("\n"):
    if not line.strip():
        continue
    entry = json.loads(line)
    item = BatchResultItem(custom_id=entry["custom_id"])
    if entry.get("response") and entry["response"].get("status_code") == 200:
        ...
```

This could be extracted into a shared utility function in `src/any_llm/types/batch.py` or a new `src/any_llm/utils/batch.py` to reduce duplication.

### 4. Consider adding type annotation for `_ANTHROPIC_TO_OPENAI_STATUS_MAP`

The status map at `src/any_llm/providers/anthropic/base.py:48` is well-typed already. No action needed.

### 5. `BATCH_API_EXPERIMENTAL_MESSAGE` constant is now orphaned

**Location**: `src/any_llm/utils/decorators.py:10`

The constant `BATCH_API_EXPERIMENTAL_MESSAGE` is no longer used anywhere in the codebase. Consider removing it to avoid dead code. The `experimental` decorator import was also removed from `any_llm.py` and `api.py`, which is correct. But the constant itself remains in `decorators.py`.

## Test Coverage Assessment

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_batch_types.py` | 8 | Types + exception construction |
| `test_anthropic_batch.py` | 11 | Status mapping, create, results, not-complete |
| `test_gateway_batch.py` | 12 | All 5 methods, error cases, missing kwargs |
| `test_openai_batch_results.py` | 4 | Success, not-complete, empty, unexpected format |
| `test_mistral_batch_results.py` | 3 | Success, not-complete, empty output |
| `test_platform_provider.py` | 1 (new) | Delegation test |
| **Total new tests** | **39** | |

Unit test coverage is solid for the new code. The main gap is the missing integration tests specified in the spec.

## Backwards Compatibility

- Removing `@experimental` decorators eliminates `FutureWarning` emissions. This is an intentional breaking change in behavior (warnings disappear), but is backwards compatible in terms of API surface.
- The `BATCH_API_EXPERIMENTAL_MESSAGE` import removal from `any_llm.py` and `api.py` is safe since it was only used by the removed decorators.
- All existing public method signatures are unchanged.
- New methods (`retrieve_batch_results`, `aretrieve_batch_results`) are purely additive.
- `SUPPORTS_BATCH = True` on `BaseAnthropicProvider` means Anthropic providers now report batch support, which could affect code that checks this flag. This is intentional per the spec.

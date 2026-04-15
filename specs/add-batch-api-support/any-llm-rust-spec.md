# Implementation Spec: any-llm-rust

## Context

The any-llm-rust SDK provides a Rust interface for communicating with the any-llm gateway. It currently supports chat completions (streaming and non-streaming) via the `Gateway` provider. This work adds batch operations: create, retrieve, cancel, list, and retrieve results. All batch methods live on the `Gateway` struct (not on the `Provider` trait, since batch is a gateway-specific concept in this SDK) and call the gateway's `/v1/batches/*` HTTP endpoints.

## Shared Interface Contract

### Gateway Batch HTTP Endpoints

| Endpoint | HTTP Method | Request | Response |
|----------|------------|---------|----------|
| `/v1/batches` | POST | JSON body: `CreateBatchParams` | `Batch` JSON + `provider` field |
| `/v1/batches/{id}?provider=X` | GET | Query param | `Batch` JSON |
| `/v1/batches/{id}/cancel?provider=X` | POST | Query param | `Batch` JSON |
| `/v1/batches?provider=X&after=Y&limit=N` | GET | Query params | `{"data": [Batch]}` |
| `/v1/batches/{id}/results?provider=X` | GET | Query param | `BatchResult` JSON |

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

| HTTP Status | Meaning | Maps To |
|-------------|---------|---------|
| 401/403 | Auth failure | `AnyLLMError::Authentication` |
| 404 | Batch not found (or gateway too old) | `AnyLLMError::Provider` with upgrade hint if on `/v1/batches` |
| 409 | Batch not complete | `AnyLLMError::BatchNotComplete` (new variant) |
| 422 | Unsupported provider | `AnyLLMError::Provider` |
| 429 | Rate limited | `AnyLLMError::RateLimit` |
| 502 | Upstream provider error | `AnyLLMError::Provider` |

## Changes Required

### 1. New types file: `src/types/batch.rs`

```rust
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Status of a batch job.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BatchStatus {
    Validating,
    Failed,
    InProgress,
    Finalizing,
    Completed,
    Expired,
    Cancelling,
    Cancelled,
}

/// Request counts for a batch job.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BatchRequestCounts {
    pub total: u32,
    pub completed: u32,
    pub failed: u32,
}

/// A batch job returned by the gateway.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Batch {
    pub id: String,
    pub object: String,
    pub endpoint: String,
    pub status: BatchStatus,
    pub created_at: i64,
    pub completion_window: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub input_file_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub output_file_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error_file_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub request_counts: Option<BatchRequestCounts>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata: Option<HashMap<String, String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub in_progress_at: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub completed_at: Option<i64>,
}

/// Parameters for creating a batch job.
#[derive(Debug, Clone, Serialize)]
pub struct CreateBatchParams {
    pub model: String,
    pub requests: Vec<BatchRequestItem>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub completion_window: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata: Option<HashMap<String, String>>,
}

impl CreateBatchParams {
    /// Create new batch params with required fields.
    pub fn new(model: impl Into<String>, requests: Vec<BatchRequestItem>) -> Self {
        Self {
            model: model.into(),
            requests,
            completion_window: None,
            metadata: None,
        }
    }

    /// Set the completion window (e.g., "24h").
    pub fn completion_window(mut self, window: impl Into<String>) -> Self {
        self.completion_window = Some(window.into());
        self
    }

    /// Set metadata key-value pairs.
    pub fn metadata(mut self, metadata: HashMap<String, String>) -> Self {
        self.metadata = Some(metadata);
        self
    }
}

/// A single request within a batch.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BatchRequestItem {
    pub custom_id: String,
    pub body: serde_json::Value,
}

/// Options for listing batch jobs.
#[derive(Debug, Clone, Default)]
pub struct ListBatchesOptions {
    pub after: Option<String>,
    pub limit: Option<u32>,
}

/// An error for a single request within a batch.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BatchResultError {
    pub code: String,
    pub message: String,
}

/// The result of a single request within a batch.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BatchResultItem {
    pub custom_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<super::completion::ChatCompletion>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<BatchResultError>,
}

/// The results of a completed batch job.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BatchResult {
    pub results: Vec<BatchResultItem>,
}
```

### 2. Register the module in `src/types/mod.rs`

Add:
```rust
mod batch;
pub use batch::*;
```

### 3. Re-export types in `src/lib.rs`

Add to the `pub use types::` block:
```rust
pub use types::{
    Batch, BatchRequestCounts, BatchRequestItem, BatchResult, BatchResultError,
    BatchResultItem, BatchStatus, CreateBatchParams, ListBatchesOptions,
    // ... existing exports
};
```

### 4. New error variant in `src/error.rs`

Add to the `AnyLLMError` enum:
```rust
/// Batch not yet complete: results cannot be retrieved.
#[error("Batch '{batch_id}' is not yet complete (status: {status}). Check status with retrieve_batch().")]
BatchNotComplete {
    batch_id: ErrorStr,
    status: ErrorStr,
    provider: ErrorStr,
},
```

### 5. Update `convert_error` in `src/providers/gateway/mod.rs`

Add 409 handling to the existing `convert_error` function:

```rust
409 => {
    // Extract batch_id and status from detail message if possible
    let batch_id = extract_batch_id(&detail_with_retry).unwrap_or_default();
    let batch_status = extract_status(&detail_with_retry).unwrap_or("unknown".to_string());
    AnyLLMError::BatchNotComplete {
        batch_id: batch_id.into(),
        status: batch_status.into(),
        provider: "gateway".into(),
    }
}
```

Also update the 404 handling to detect batch endpoint URLs and provide an "upgrade your gateway" message:

```rust
404 => {
    // Check if this is a batch endpoint 404 (gateway too old)
    if url_path.contains("/v1/batches") {
        AnyLLMError::Provider {
            message: "This gateway does not support batch operations. Upgrade your gateway.".into(),
            provider: Gateway::NAME.into(),
        }
    } else {
        AnyLLMError::ModelNotFound {
            model: detail_with_retry.into(),
            provider: Gateway::NAME.into(),
        }
    }
}
```

Note: The `convert_error` function currently takes only a `reqwest::Response`. It may need to be extended to also accept the URL path for the 404 disambiguation. Alternatively, the batch methods can catch the `ModelNotFound` error and re-map it.

### 6. Batch methods on `Gateway` struct

Add to `impl Gateway` in `src/providers/gateway/mod.rs`:

```rust
/// Create a batch job.
pub async fn create_batch(&self, params: CreateBatchParams) -> Result<Batch> {
    let url = format!("{}/v1/batches", self.api_base);
    let response = self.client.post(&url).json(&params).send().await?;
    let status = response.status().as_u16();
    if status != 200 {
        return Err(self.convert_batch_error(response, "/v1/batches").await);
    }
    // Deserialize, ignoring the extra "provider" field
    Ok(response.json::<Batch>().await?)
}

/// Retrieve the status of a batch job.
pub async fn retrieve_batch(&self, batch_id: &str, provider: &str) -> Result<Batch> {
    let url = format!("{}/v1/batches/{}", self.api_base, batch_id);
    let response = self.client.get(&url)
        .query(&[("provider", provider)])
        .send().await?;
    let status = response.status().as_u16();
    if status != 200 {
        return Err(self.convert_batch_error(response, &format!("/v1/batches/{}", batch_id)).await);
    }
    Ok(response.json::<Batch>().await?)
}

/// Cancel a batch job.
pub async fn cancel_batch(&self, batch_id: &str, provider: &str) -> Result<Batch> {
    let url = format!("{}/v1/batches/{}/cancel", self.api_base, batch_id);
    let response = self.client.post(&url)
        .query(&[("provider", provider)])
        .send().await?;
    let status = response.status().as_u16();
    if status != 200 {
        return Err(self.convert_batch_error(response, &format!("/v1/batches/{}/cancel", batch_id)).await);
    }
    Ok(response.json::<Batch>().await?)
}

/// List batch jobs for a provider.
pub async fn list_batches(&self, provider: &str, options: ListBatchesOptions) -> Result<Vec<Batch>> {
    let url = format!("{}/v1/batches", self.api_base);
    let mut query: Vec<(&str, String)> = vec![("provider", provider.to_string())];
    if let Some(after) = &options.after {
        query.push(("after", after.clone()));
    }
    if let Some(limit) = options.limit {
        query.push(("limit", limit.to_string()));
    }
    let response = self.client.get(&url).query(&query).send().await?;
    let status = response.status().as_u16();
    if status != 200 {
        return Err(self.convert_batch_error(response, "/v1/batches").await);
    }
    #[derive(Deserialize)]
    struct ListResponse { data: Vec<Batch> }
    let list_resp: ListResponse = response.json().await?;
    Ok(list_resp.data)
}

/// Retrieve the results of a completed batch job.
pub async fn retrieve_batch_results(&self, batch_id: &str, provider: &str) -> Result<BatchResult> {
    let url = format!("{}/v1/batches/{}/results", self.api_base, batch_id);
    let response = self.client.get(&url)
        .query(&[("provider", provider)])
        .send().await?;
    let status = response.status().as_u16();
    if status != 200 {
        return Err(self.convert_batch_error(response, &format!("/v1/batches/{}/results", batch_id)).await);
    }
    Ok(response.json::<BatchResult>().await?)
}
```

**Private helper** for batch-specific error conversion:

```rust
async fn convert_batch_error(&self, response: reqwest::Response, path: &str) -> AnyLLMError {
    let status = response.status().as_u16();
    // Reuse existing error extraction logic
    let detail = // ... extract detail from response body

    match status {
        409 => AnyLLMError::BatchNotComplete {
            batch_id: extract_batch_id_from_detail(&detail).unwrap_or_default().into(),
            status: extract_status_from_detail(&detail).unwrap_or("unknown").into(),
            provider: "gateway".into(),
        },
        404 if path.contains("/v1/batches") => AnyLLMError::Provider {
            message: format!(
                "This gateway does not support batch operations. Upgrade your gateway. ({})",
                detail
            ).into(),
            provider: Gateway::NAME.into(),
        },
        _ => convert_error(response).await, // fall back to existing logic
    }
}
```

Note: Since `convert_error` consumes the response, the `convert_batch_error` method needs to read the response body first if it needs to check the status before delegating. Consider refactoring to extract the body once and then branch.

### 7. Serde handling for the `provider` field on `Batch`

The gateway's create batch response includes an extra `provider` field that is not part of the `Batch` struct. Use `#[serde(deny_unknown_fields)]` is NOT appropriate here. Instead, add `#[serde(default)]` behavior: serde will simply ignore unknown fields by default, which is the correct behavior. However, to also capture the provider for SDK callers, consider either:

- **Option A**: Add an optional `provider` field to `Batch`: `pub provider: Option<String>` with `#[serde(skip_serializing_if = "Option::is_none")]`. This is the simplest approach.
- **Option B**: Use a wrapper struct for the create response only. More type-safe but adds complexity.

**Recommendation**: Option A. Add `pub provider: Option<String>` to `Batch`.

## Implementation Steps

1. Create `src/types/batch.rs` with all type definitions.
2. Register the module in `src/types/mod.rs` and re-export in `src/lib.rs`.
3. Add `BatchNotComplete` variant to `AnyLLMError` in `src/error.rs`.
4. Add the 5 batch methods to `impl Gateway` in `src/providers/gateway/mod.rs`.
5. Add batch-specific error conversion (409 handling, 404 "upgrade gateway" hint).
6. Write unit tests with wiremock.
7. Write integration tests (gated behind API key / live gateway).

## Testing Requirements

### Unit Tests (in `tests/test_gateway.rs`, extend existing)

Follow the existing wiremock-based test pattern:

**Type tests:**
- `batch_deserializes_from_json` — Verify `Batch` deserializes from a gateway JSON fixture.
- `batch_result_deserializes_from_json` — Verify `BatchResult` with mixed success/error items.
- `create_batch_params_serializes_correctly` — Verify `CreateBatchParams` produces correct JSON.
- `batch_status_enum_values` — Verify all status values round-trip.

**HTTP method tests (wiremock):**
- `create_batch_sends_correct_request` — Verify POST to `/v1/batches` with JSON body, correct auth headers.
- `retrieve_batch_sends_provider_query_param` — Verify GET with `?provider=openai`.
- `cancel_batch_sends_correct_request` — Verify POST to `/v1/batches/{id}/cancel?provider=openai`.
- `list_batches_sends_pagination_params` — Verify GET with `?provider=openai&after=cursor&limit=10`.
- `retrieve_batch_results_returns_batch_result` — Verify GET and deserialization.

**Error tests (wiremock):**
- `batch_409_returns_batch_not_complete` — Verify 409 maps to `AnyLLMError::BatchNotComplete`.
- `batch_404_returns_upgrade_gateway_hint` — Verify 404 on batch endpoint gives "upgrade" message.
- `batch_401_returns_authentication_error` — Verify 401 maps to `AnyLLMError::Authentication`.
- `batch_422_returns_provider_error` — Verify 422 maps to `AnyLLMError::Provider`.
- `batch_502_returns_provider_error` — Verify 502 maps to `AnyLLMError::Provider`.

### Integration Tests (in `tests/integration_batch.rs`, new file)

Gated by `#[ignore]` (require live gateway):
- `live_create_and_retrieve_batch` — Full create → retrieve → cancel flow.
- `live_retrieve_batch_results_not_complete` — Verify `BatchNotComplete` error on fresh batch.

## Acceptance Criteria

1. All five batch methods compile and produce correct HTTP calls.
2. `Batch` and `BatchResult` types correctly deserialize from gateway JSON responses.
3. Error mapping works for 409 (batch not complete), 404 (upgrade hint), and standard HTTP errors.
4. All unit tests pass with wiremock.
5. The `provider` field from the create response is accessible on the `Batch` struct.
6. No changes to existing Provider trait or completion functionality.

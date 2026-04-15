# Design: Batch API Support Across All SDKs

## User/Developer Flows

### Flow 1: Python SDK — Direct provider batch (OpenAI, Mistral, Anthropic)

This is the foundational flow. The user has a JSONL file of requests and wants to submit it as a batch job directly against a provider.

```
1. User prepares a JSONL input file with batch requests
2. User calls create_batch(provider, input_file_path, endpoint, ...)
3. SDK uploads the file, creates the batch, returns a Batch object
4. User polls with retrieve_batch(provider, batch_id) until status is "completed"
5. User calls retrieve_batch_results(provider, batch_id) to get BatchResult
6. User iterates over BatchResult.results, matching custom_id to original requests
```

**No change to steps 1-4** — these already work for OpenAI and Mistral. This feature adds Anthropic to step 3, adds step 5-6 for all providers, and graduates the API from experimental (removing the `FutureWarning`).

### Flow 2: Any SDK — Batch via gateway

This is the primary new flow for non-Python SDKs and for Python users who want centralized auth/observability. The gateway accepts a JSON body (not a file upload), so the SDK experience is simpler.

```
1. User constructs a list of request objects in code (no file needed)
2. User calls createBatch({ model: "openai:gpt-4o-mini", requests: [...] })
3. Gateway constructs the JSONL internally, delegates to Python SDK, returns Batch
4. User polls with retrieveBatch(batchId, provider) until status is "completed"
5. User calls retrieveBatchResults(batchId, provider) to get BatchResult
6. User iterates over results, matching customId to original requests
```

Key ergonomic difference from Flow 1: **no file management**. The SDK user works entirely with in-memory data structures. The gateway handles file construction and cleanup.

### Flow 3: Cancel and list

```
Cancel:  cancelBatch(batchId, provider) → Batch with updated status
List:    listBatches(provider, { after?, limit? }) → Batch[]
```

Both are low-frequency operations. The `provider` parameter is always required for gateway calls (DD2).

### Flow 4: Error — batch not yet complete

```
1. User calls retrieveBatchResults(batchId, provider)
2. Batch status is "in_progress"
3. SDK receives a clear error: "Batch 'batch_abc' is not yet complete (status: in_progress).
   Call retrieve_batch() to check the current status."
4. User adjusts their polling logic
```

### Flow 5: Error — gateway does not support batch (version mismatch)

```
1. User upgrades their SDK but not the gateway
2. User calls createBatch(...)
3. Gateway returns 404 (no /v1/batches endpoint)
4. SDK surfaces: "This gateway does not support batch operations.
   Upgrade your gateway to version X.Y.0 or later."
```

---

## API Design

### Gateway API

All batch endpoints live under `/v1/batches`. Authentication is identical to `/v1/chat/completions` — `verify_api_key_or_master_key` via `X-AnyLLM-Key`, `Authorization`, or `x-api-key` headers.

#### `POST /v1/batches` — Create a batch

**Request body:**

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
    },
    {
      "custom_id": "req-2",
      "body": {
        "messages": [{"role": "user", "content": "World"}],
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

**Response:** `200 OK` with the `Batch` object as JSON. The response includes a `provider` field at the top level (added by the gateway, not part of the OpenAI `Batch` type) so SDKs can cache it.

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

**Design note:** The `provider` field is _not_ part of the standard `Batch` schema. The gateway injects it as a sibling field. SDKs that deserialize into a strict `Batch` type should either: (a) use a wrapper response type (`CreateBatchResponse { batch: Batch, provider: String }`), or (b) store `provider` from a separate JSON field before deserializing the rest as `Batch`. Option (a) is recommended for type safety.

#### `GET /v1/batches/{batch_id}?provider=` — Retrieve batch status

**Query params:** `provider` (required, string — the provider name, e.g., `"openai"`)

**Response:** `200 OK` with `Batch` object.

#### `POST /v1/batches/{batch_id}/cancel?provider=` — Cancel a batch

**Query params:** `provider` (required)

**Response:** `200 OK` with `Batch` object (updated status).

#### `GET /v1/batches?provider=` — List batches

**Query params:**
- `provider` (required)
- `after` (optional, string — cursor for pagination)
- `limit` (optional, integer — max items to return)

**Response:** `200 OK` with `{"data": [Batch, ...]}`.

#### `GET /v1/batches/{batch_id}/results?provider=` — Retrieve batch results

**Query params:** `provider` (required)

**Response:** `200 OK` with `BatchResult` object (see type definition below).

**Error:** `409 Conflict` if batch status is not `completed`, with body:

```json
{
  "detail": "Batch 'batch_abc123' is not yet complete (status: in_progress). Call GET /v1/batches/batch_abc123?provider=openai to check the current status."
}
```

#### Error responses

| Code | Condition | Example `detail` |
|------|-----------|-----------------|
| 400 | Missing/invalid field | `"Invalid request: model is required"` |
| 400 | Empty requests array | Handled by Pydantic validation (422 in practice) |
| 401 | Bad/missing auth | `"Invalid API key"` (existing behavior) |
| 403 | Insufficient permissions | `"API key is inactive"` (existing behavior) |
| 404 | Batch not found | `"Batch 'batch_xyz' not found for provider 'openai'"` |
| 409 | Incompatible state | `"Batch 'batch_abc' is not yet complete (status: in_progress)..."` |
| 413 | Too many requests | `"Requests array exceeds maximum size of 10,000 items"` |
| 422 | Unsupported provider | `"Provider 'ollama' does not support batch operations"` |
| 429 | Rate limited | Upstream provider rate limit (proxied) |
| 502 | Upstream error | `"Upstream provider error: <detail>"` |

#### Gateway route handler pattern

The handler follows the established pattern from `chat.py`:

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
    # 1. Auth
    api_key, is_master_key = await verify_api_key_or_master_key(raw_request, db, config)

    # 2. Parse provider:model
    provider, model = AnyLLM.split_model_provider(request.model)

    # 3. Validate provider supports batch
    provider_class = AnyLLM.get_provider_class(provider)
    if not getattr(provider_class, "SUPPORTS_BATCH", False):
        raise HTTPException(422, detail=f"Provider '{provider.value}' does not support batch operations")

    # 4. Build JSONL temp file from requests array
    # 5. Call acreate_batch(provider, temp_file, "/v1/chat/completions", ...)
    # 6. Clean up temp file
    # 7. Log usage
    # 8. Return Batch + provider field
```

**Router registration:** Add `app.include_router(batches.router)` in `register_routers()`, after `embeddings.router`. The new file is `src/gateway/api/routes/batches.py`. The router uses `prefix="/v1/batches"` and `tags=["batches"]`.

#### Usage logging

Batch operations log to `UsageLog` with:
- `endpoint` = `"/v1/batches"` for create, `"/v1/batches/results"` for result retrieval
- `model` = the model string from the request
- `provider` = extracted provider name
- Token counts and cost: logged at result retrieval time (when usage data is available from the `BatchResult`), not at creation time

#### Prometheus metrics

No new counter needed — the existing `gateway_requests` counter (which fires via `MetricsMiddleware` on every HTTP request) already captures batch endpoint calls with appropriate `method`, `endpoint`, and `status` labels.

#### OpenAPI spec

The `openapi.json` must be regenerated after adding the new routes. The generation script (`scripts/generate_openapi.py`) will pick up the new routes automatically. New schemas to add: `CreateBatchRequest`, `BatchRequestItem`, `BatchResult`, `BatchResultItem`, `BatchResultError`.

---

### Python SDK

#### New types in `src/any_llm/types/batch.py`

```python
from __future__ import annotations

from dataclasses import dataclass

from openai.types import Batch as OpenAIBatch
from openai.types.batch_request_counts import BatchRequestCounts as OpenAIBatchRequestCounts
from openai.types.chat import ChatCompletion

Batch = OpenAIBatch
BatchRequestCounts = OpenAIBatchRequestCounts


@dataclass
class BatchResultError:
    """An error that occurred for a single request within a batch."""

    code: str
    message: str


@dataclass
class BatchResultItem:
    """The result of a single request within a batch."""

    custom_id: str
    result: ChatCompletion | None = None
    error: BatchResultError | None = None


@dataclass
class BatchResult:
    """The results of a completed batch job."""

    results: list[BatchResultItem]
```

**Design decision — `@dataclass` vs Pydantic `BaseModel`:** The existing `Batch` type is an OpenAI Pydantic model. The new result types are SDK-owned. Using `@dataclass` is simpler (no Pydantic dependency for these types), matches the pattern used elsewhere in the SDK for lightweight data containers, and avoids confusion about whether these are request/response models. However, if JSON serialization through the gateway is needed, the gateway route can serialize them manually or use Pydantic models on the gateway side. The Python SDK types themselves don't need to be Pydantic.

**Alternative considered:** Making `BatchResult` a Pydantic `BaseModel` for automatic JSON round-tripping. This would help the gateway but adds coupling. The gateway should define its own Pydantic response models (like it does for `UsageEntry`, `KeyInfo`, etc.) and convert from SDK types.

#### New methods on `AnyLLM` base class (`any_llm.py`)

Following the existing three-tier pattern (sync → async → private):

```python
# Public sync (no @experimental — graduated)
def retrieve_batch_results(
    self,
    batch_id: str,
    **kwargs: Any,
) -> BatchResult:
    return run_async_in_sync(self.aretrieve_batch_results(batch_id, **kwargs))

# Public async
@handle_exceptions()
async def aretrieve_batch_results(
    self,
    batch_id: str,
    **kwargs: Any,
) -> BatchResult:
    return await self._aretrieve_batch_results(batch_id, **kwargs)

# Private overridable
async def _aretrieve_batch_results(self, batch_id: str, **kwargs: Any) -> BatchResult:
    if not self.SUPPORTS_BATCH:
        msg = "Provider doesn't support batch completions."
        raise NotImplementedError(msg)
    msg = "Subclasses must implement _aretrieve_batch_results method"
    raise NotImplementedError(msg)
```

#### New top-level API functions in `api.py`

```python
def retrieve_batch_results(
    provider: str | LLMProvider,
    batch_id: str,
    *,
    api_key: str | None = None,
    api_base: str | None = None,
    client_args: dict[str, Any] | None = None,
    **kwargs: Any,
) -> BatchResult:
    ...

async def aretrieve_batch_results(
    provider: str | LLMProvider,
    batch_id: str,
    *,
    api_key: str | None = None,
    api_base: str | None = None,
    client_args: dict[str, Any] | None = None,
    **kwargs: Any,
) -> BatchResult:
    ...
```

**Note:** No `@experimental` decorator. All batch methods (existing and new) have the decorator removed as part of graduation.

#### Gateway provider overrides (`providers/gateway/gateway.py`)

The Gateway provider must override all five batch methods to use gateway-specific HTTP calls instead of the inherited OpenAI file-upload flow.

```python
@override
async def _acreate_batch(
    self,
    input_file_path: str,
    endpoint: str,
    completion_window: str = "24h",
    metadata: dict[str, str] | None = None,
    **kwargs: Any,
) -> Batch:
    # Read JSONL file and parse into request objects
    requests = _parse_jsonl_to_requests(input_file_path)
    model = kwargs.pop("model", None)
    if not model:
        # Extract model from first request in the JSONL
        model = _extract_model_from_requests(requests)

    body = {
        "model": model,
        "requests": requests,
        "completion_window": completion_window,
        "metadata": metadata,
    }
    response = await self._post_json("/v1/batches", body)
    return Batch(**response)
```

For `_aretrieve_batch`, `_acancel_batch`, `_alist_batches`, and `_aretrieve_batch_results`, the override adds `?provider=<provider>` as a query parameter. The `provider` value must be passed via `**kwargs` by the caller (or cached from the `create_batch` response).

**Design note on provider passing:** The Gateway provider needs the upstream provider name (e.g., `"openai"`) for DD2 query params. Two options:

1. **Via kwargs:** `retrieve_batch(provider="gateway", batch_id="...", provider_name="openai")` — pollutes the public API with gateway-specific params.
2. **Via the model string:** When the user creates a batch with `model="openai:gpt-4o-mini"`, the gateway echoes back `provider: "openai"` in the response. The user passes this as a kwarg on subsequent calls.

**Recommendation:** Use `**kwargs` with `provider_name` as the key. This is gateway-specific and won't affect other providers (they'll ignore it). Document that when using the gateway provider, `provider_name` must be passed on retrieve/cancel/list/results calls.

```python
# Gateway provider usage (Python)
batch = create_batch("gateway", "input.jsonl", "/v1/chat/completions",
                     model="openai:gpt-4o-mini")
# batch.metadata or a returned field tells the user the provider is "openai"

status = retrieve_batch("gateway", batch.id, provider_name="openai")
results = retrieve_batch_results("gateway", batch.id, provider_name="openai")
```

#### Anthropic provider implementation

The Anthropic provider sets `SUPPORTS_BATCH = True` and implements all five private batch methods. The status mapping:

| Anthropic `MessageBatch` status | OpenAI `Batch` status |
|----|-----|
| `in_progress` | `in_progress` |
| `ended` (all succeeded) | `completed` |
| `ended` (with failures) | `completed` (with `request_counts.failed > 0`) |
| `canceling` | `cancelling` |
| `canceled` | `cancelled` |
| `expired` | `expired` |
| Unknown | `in_progress` (with `logger.warning`) |

The conversion function follows the Mistral precedent (`_convert_batch_job_to_openai`):

```python
def _convert_anthropic_batch_to_openai(batch: MessageBatch) -> Batch:
    """Convert an Anthropic MessageBatch to OpenAI Batch format."""
    ...
```

#### Graduating from experimental

Remove `@experimental(BATCH_API_EXPERIMENTAL_MESSAGE)` from all 10 batch methods in `any_llm.py` and all 8 batch functions in `api.py`. Keep the decorator stacking order for `@handle_exceptions()` unchanged.

**Changelog note:**

> **Removed:** The `FutureWarning` previously emitted on every batch API call (`create_batch`, `retrieve_batch`, `cancel_batch`, `list_batches`, and the new `retrieve_batch_results`) has been removed. The Batch API is now stable.

---

### Rust SDK

Batch methods are added directly to the `Gateway` struct (not to the `Provider` trait, since batch is gateway-specific in the Rust SDK).

#### New types in `src/types/batch.rs`

```rust
use serde::{Deserialize, Serialize};
use super::completion::ChatCompletion;

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

/// A batch job.
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
    pub metadata: Option<std::collections::HashMap<String, String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub in_progress_at: Option<i64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub completed_at: Option<i64>,
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
    pub result: Option<ChatCompletion>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<BatchResultError>,
}

/// The results of a completed batch job.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BatchResult {
    pub results: Vec<BatchResultItem>,
}
```

Module registration in `types/mod.rs`:

```rust
mod batch;
pub use batch::*;
```

#### New methods on `Gateway`

```rust
impl Gateway {
    /// Create a batch job.
    pub async fn create_batch(&self, params: CreateBatchParams) -> Result<Batch> { ... }

    /// Retrieve the status of a batch job.
    pub async fn retrieve_batch(&self, batch_id: &str, provider: &str) -> Result<Batch> { ... }

    /// Cancel a batch job.
    pub async fn cancel_batch(&self, batch_id: &str, provider: &str) -> Result<Batch> { ... }

    /// List batch jobs for a provider.
    pub async fn list_batches(&self, provider: &str, options: ListBatchesOptions) -> Result<Vec<Batch>> { ... }

    /// Retrieve the results of a completed batch job.
    pub async fn retrieve_batch_results(&self, batch_id: &str, provider: &str) -> Result<BatchResult> { ... }
}
```

**`CreateBatchParams`** follows the builder pattern used by `CompletionParams`:

```rust
/// Parameters for creating a batch job.
#[derive(Debug, Clone, Serialize)]
pub struct CreateBatchParams {
    pub model: String,
    pub requests: Vec<BatchRequestItem>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub completion_window: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata: Option<std::collections::HashMap<String, String>>,
}

/// A single request within a batch.
#[derive(Debug, Clone, Serialize)]
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
```

Builder methods:

```rust
impl CreateBatchParams {
    pub fn new(model: impl Into<String>, requests: Vec<BatchRequestItem>) -> Self {
        Self {
            model: model.into(),
            requests,
            completion_window: None,
            metadata: None,
        }
    }

    pub fn completion_window(mut self, window: impl Into<String>) -> Self {
        self.completion_window = Some(window.into());
        self
    }

    pub fn metadata(mut self, metadata: std::collections::HashMap<String, String>) -> Self {
        self.metadata = Some(metadata);
        self
    }
}
```

**Usage example:**

```rust
use any_llm::providers::Gateway;
use any_llm::{Batch, BatchResult, BatchRequestItem, CreateBatchParams};

let gw = Gateway::from_config(config)?;

let params = CreateBatchParams::new("openai:gpt-4o-mini", vec![
    BatchRequestItem {
        custom_id: "req-1".into(),
        body: serde_json::json!({
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 100,
        }),
    },
]);

let batch = gw.create_batch(params).await?;
println!("Batch created: {}", batch.id);

// Poll until complete
let batch = gw.retrieve_batch(&batch.id, "openai").await?;

// Get results
let results = gw.retrieve_batch_results(&batch.id, "openai").await?;
for item in &results.results {
    match (&item.result, &item.error) {
        (Some(completion), _) => println!("{}: {}", item.custom_id, completion.content().unwrap_or_default()),
        (_, Some(err)) => eprintln!("{}: error {}: {}", item.custom_id, err.code, err.message),
        _ => {}
    }
}
```

#### Error handling

Batch-specific errors reuse the existing `AnyLLMError` enum. One new variant is added:

```rust
/// Batch not complete - results cannot be retrieved yet.
#[error("Batch '{batch_id}' is not yet complete (status: {status}). Check status with retrieve_batch().")]
BatchNotComplete {
    batch_id: ErrorStr,
    status: ErrorStr,
    provider: ErrorStr,
},
```

The gateway's `convert_error` function (already in `providers/gateway/mod.rs`) handles HTTP status mapping. The new `409` status maps to the new `BatchNotComplete` variant:

```rust
409 => AnyLLMError::BatchNotComplete {
    batch_id: extract_batch_id_from_detail(&detail_with_retry).unwrap_or_default().into(),
    status: extract_status_from_detail(&detail_with_retry).unwrap_or("unknown").into(),
    provider: "gateway".into(),
},
```

---

### Go SDK

#### New `BatchProvider` interface in `providers/types.go`

Following the optional-interface pattern of `EmbeddingProvider`:

```go
// BatchProvider is an optional interface for providers that support
// batch operations. Use a type assertion to check if a provider
// supports batch:
//
//	if bp, ok := provider.(BatchProvider); ok {
//	    batch, err := bp.CreateBatch(ctx, params)
//	}
type BatchProvider interface {
	Provider
	CreateBatch(ctx context.Context, params CreateBatchParams) (*Batch, error)
	RetrieveBatch(ctx context.Context, batchID string, provider string) (*Batch, error)
	CancelBatch(ctx context.Context, batchID string, provider string) (*Batch, error)
	ListBatches(ctx context.Context, provider string, opts ListBatchesOptions) ([]Batch, error)
	RetrieveBatchResults(ctx context.Context, batchID string, provider string) (*BatchResult, error)
}
```

#### New types in `providers/types.go`

Following existing conventions (A-Z field order, `json` tags with `omitempty`, pointer types for optional fields):

```go
// Batch represents a batch job.
type Batch struct {
	CompletedAt      *int64             `json:"completed_at,omitempty"`
	CompletionWindow string             `json:"completion_window"`
	CreatedAt        int64              `json:"created_at"`
	Endpoint         string             `json:"endpoint"`
	ErrorFileID      string             `json:"error_file_id,omitempty"`
	ID               string             `json:"id"`
	InProgressAt     *int64             `json:"in_progress_at,omitempty"`
	InputFileID      string             `json:"input_file_id,omitempty"`
	Metadata         map[string]string  `json:"metadata,omitempty"`
	Object           string             `json:"object"`
	OutputFileID     string             `json:"output_file_id,omitempty"`
	RequestCounts    *BatchRequestCounts `json:"request_counts,omitempty"`
	Status           BatchStatus        `json:"status"`
}

// BatchStatus represents the status of a batch job.
type BatchStatus string

const (
	BatchStatusValidating BatchStatus = "validating"
	BatchStatusFailed     BatchStatus = "failed"
	BatchStatusInProgress BatchStatus = "in_progress"
	BatchStatusFinalizing BatchStatus = "finalizing"
	BatchStatusCompleted  BatchStatus = "completed"
	BatchStatusExpired    BatchStatus = "expired"
	BatchStatusCancelling BatchStatus = "cancelling"
	BatchStatusCancelled  BatchStatus = "cancelled"
)

// BatchRequestCounts tracks request counts for a batch job.
type BatchRequestCounts struct {
	Completed int `json:"completed"`
	Failed    int `json:"failed"`
	Total     int `json:"total"`
}

// BatchRequestItem is a single request within a batch.
type BatchRequestItem struct {
	Body     map[string]any `json:"body"`
	CustomID string         `json:"custom_id"`
}

// CreateBatchParams are parameters for creating a batch job.
type CreateBatchParams struct {
	CompletionWindow string            `json:"completion_window,omitempty"`
	Metadata         map[string]string `json:"metadata,omitempty"`
	Model            string            `json:"model"`
	Requests         []BatchRequestItem `json:"requests"`
}

// ListBatchesOptions are options for listing batch jobs.
type ListBatchesOptions struct {
	After string `json:"after,omitempty"`
	Limit *int   `json:"limit,omitempty"`
}

// BatchResult contains the results of a completed batch job.
type BatchResult struct {
	Results []BatchResultItem `json:"results"`
}

// BatchResultItem is the result of a single request within a batch.
type BatchResultItem struct {
	CustomID string           `json:"custom_id"`
	Error    *BatchResultError `json:"error,omitempty"`
	Result   *ChatCompletion  `json:"result,omitempty"`
}

// BatchResultError is an error for a single request within a batch.
type BatchResultError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}
```

Re-exported in `anyllm.go`:

```go
type Batch = providers.Batch
type BatchStatus = providers.BatchStatus
type BatchResult = providers.BatchResult
// ... etc
```

#### New Gateway provider: `providers/gateway/gateway.go`

The provider struct and constructor follow the CompatibleProvider pattern, but this is a standalone implementation (not embedding CompatibleProvider) since the Gateway has unique auth (X-AnyLLM-Key) and routing (provider:model format):

```go
package gateway

type Provider struct {
	apiBase    string
	httpClient *http.Client
}

func New(opts ...config.Option) (*Provider, error) { ... }

// Implements providers.Provider
func (p *Provider) Name() string { return "gateway" }
func (p *Provider) Completion(ctx context.Context, params providers.CompletionParams) (*providers.ChatCompletion, error) { ... }
func (p *Provider) CompletionStream(ctx context.Context, params providers.CompletionParams) (<-chan providers.ChatCompletionChunk, <-chan error) { ... }

// Implements providers.BatchProvider
func (p *Provider) CreateBatch(ctx context.Context, params providers.CreateBatchParams) (*providers.Batch, error) { ... }
func (p *Provider) RetrieveBatch(ctx context.Context, batchID string, provider string) (*providers.Batch, error) { ... }
func (p *Provider) CancelBatch(ctx context.Context, batchID string, provider string) (*providers.Batch, error) { ... }
func (p *Provider) ListBatches(ctx context.Context, provider string, opts providers.ListBatchesOptions) ([]providers.Batch, error) { ... }
func (p *Provider) RetrieveBatchResults(ctx context.Context, batchID string, provider string) (*providers.BatchResult, error) { ... }

// Compile-time interface checks
var (
	_ providers.BatchProvider      = (*Provider)(nil)
	_ providers.CapabilityProvider = (*Provider)(nil)
	_ providers.Provider           = (*Provider)(nil)
)
```

#### Error handling

Add a new sentinel error and structured error type:

```go
// errors/errors.go
var ErrBatchNotComplete = stderrors.New("batch not yet complete")

type BatchNotCompleteError struct {
	BaseError
	BatchID string
	Status  string
}

func NewBatchNotCompleteError(provider string, batchID string, status string) *BatchNotCompleteError {
	return &BatchNotCompleteError{
		BaseError: BaseError{
			Code:     "batch_not_complete",
			Provider: provider,
			Err:      fmt.Errorf("batch '%s' is not yet complete (status: %s)", batchID, status),
			sentinel: ErrBatchNotComplete,
		},
		BatchID: batchID,
		Status:  status,
	}
}
```

---

### TypeScript SDK

Batch methods are added directly to `GatewayClient`. Unlike completions (which delegate to `this.openai`), batch methods use direct HTTP calls because the gateway's batch API uses a custom JSON format (DD1).

#### New types in `src/types.ts`

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

#### New methods on `GatewayClient`

```typescript
export class GatewayClient {
  // ... existing methods ...

  async createBatch(params: CreateBatchParams): Promise<Batch> {
    return this.batchRequest("POST", "/v1/batches", { body: params });
  }

  async retrieveBatch(batchId: string, provider: string): Promise<Batch> {
    return this.batchRequest("GET", `/v1/batches/${batchId}?provider=${encodeURIComponent(provider)}`);
  }

  async cancelBatch(batchId: string, provider: string): Promise<Batch> {
    return this.batchRequest("POST", `/v1/batches/${batchId}/cancel?provider=${encodeURIComponent(provider)}`);
  }

  async listBatches(provider: string, options?: ListBatchesOptions): Promise<Batch[]> {
    const params = new URLSearchParams({ provider });
    if (options?.after) params.set("after", options.after);
    if (options?.limit !== undefined) params.set("limit", String(options.limit));
    const response = await this.batchRequest<{ data: Batch[] }>("GET", `/v1/batches?${params}`);
    return response.data;
  }

  async retrieveBatchResults(batchId: string, provider: string): Promise<BatchResult> {
    return this.batchRequest("GET", `/v1/batches/${batchId}/results?provider=${encodeURIComponent(provider)}`);
  }

  // Private helper for batch HTTP calls
  private async batchRequest<T = unknown>(method: string, path: string, options?: { body?: unknown }): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const headers: Record<string, string> = { "Content-Type": "application/json", ...this.authHeaders };

    const response = await fetch(url, {
      method,
      headers,
      body: options?.body ? JSON.stringify(options.body) : undefined,
    });

    if (!response.ok) {
      await this.handleBatchError(response);
    }

    return response.json() as Promise<T>;
  }
}
```

**Design note:** `this.baseUrl` and `this.authHeaders` are new private properties extracted from the constructor. Currently the constructor builds an `OpenAI` client, which encapsulates the base URL and headers. For batch methods, we need direct access. The cleanest approach is to store these as private fields during construction:

```typescript
private readonly baseUrl: string;      // e.g. "http://localhost:8000/v1"
private readonly authHeaders: Record<string, string>;
```

This is a small internal refactor — the public API of the constructor doesn't change.

#### New error class

```typescript
export class BatchNotCompleteError extends AnyLLMError {
  static override defaultMessage = "Batch is not yet complete";
  readonly batchId?: string;
  readonly batchStatus?: string;

  constructor(options: AnyLLMErrorOptions & { batchId?: string; batchStatus?: string } = {}) {
    super(options);
    this.batchId = options.batchId;
    this.batchStatus = options.batchStatus;
  }
}
```

Error mapping in `handleBatchError`:

```typescript
private async handleBatchError(response: Response): Promise<never> {
  const body = await response.json().catch(() => ({}));
  const detail = body?.detail ?? response.statusText;

  switch (response.status) {
    case 401:
    case 403:
      throw new AuthenticationError({ message: detail, statusCode: response.status });
    case 404:
      throw new AnyLLMError({ message: detail, statusCode: 404 });
    case 409:
      throw new BatchNotCompleteError({ message: detail, statusCode: 409 });
    case 422:
      throw new AnyLLMError({ message: detail, statusCode: 422 });
    case 429:
      throw new RateLimitError({
        message: detail,
        statusCode: 429,
        retryAfter: response.headers.get("retry-after") ?? undefined,
      });
    case 502:
      throw new UpstreamProviderError({ message: detail, statusCode: 502 });
    case 504:
      throw new GatewayTimeoutError({ message: detail, statusCode: 504 });
    default:
      throw new AnyLLMError({ message: detail, statusCode: response.status });
  }
}
```

#### Updated exports in `src/index.ts`

```typescript
// New class exports
export { BatchNotCompleteError } from "./errors.js";

// New type exports
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

---

## Error Handling UX

Every error a developer encounters should answer three questions: **What happened? Why? What do I do next?**

### Error catalog

| Scenario | Python SDK | Rust SDK | Go SDK | TypeScript SDK |
|----------|-----------|---------|--------|---------------|
| Provider doesn't support batch | `NotImplementedError: Provider doesn't support batch completions.` | `AnyLLMError::Provider { message: "Provider does not support batch" }` | `errors.NewProviderError("gateway", err)` | `AnyLLMError { message: "Provider does not support batch operations" }` |
| Batch not found | `ProviderError: [gateway] Batch 'batch_xyz' not found for provider 'openai'` | `AnyLLMError::Provider { message: "Batch 'batch_xyz' not found..." }` | `*errors.ProviderError` | `AnyLLMError { statusCode: 404 }` |
| Results requested before completion | `BatchNotCompleteError: Batch 'batch_abc' is not yet complete (status: in_progress). Call retrieve_batch() to check the current status.` | `AnyLLMError::BatchNotComplete { batch_id, status }` | `*errors.BatchNotCompleteError { BatchID, Status }` | `BatchNotCompleteError { batchId, batchStatus }` |
| Gateway too old (no batch endpoints) | `ProviderError: [gateway] This gateway does not support batch operations. Upgrade your gateway to v0.X.0 or later.` | Same pattern, detected via 404 on `/v1/batches` | Same | Same |
| Request array too large | `ProviderError: [gateway] Requests array exceeds maximum size of 10,000 items` | Same | Same | Same |
| Upstream rate limit | `RateLimitError` (existing) | `AnyLLMError::RateLimit` (existing) | `*errors.RateLimitError` (existing) | `RateLimitError` (existing) |

### Python-specific: `BatchNotCompleteError`

A new exception class in the Python SDK's exception hierarchy:

```python
class BatchNotCompleteError(AnyLLMError):
    """Raised when retrieve_batch_results is called on a non-completed batch."""

    def __init__(
        self,
        batch_id: str,
        status: str,
        provider_name: str | None = None,
    ):
        self.batch_id = batch_id
        self.batch_status = status
        message = (
            f"Batch '{batch_id}' is not yet complete (status: {status}). "
            f"Call retrieve_batch() to check the current status."
        )
        super().__init__(message=message, provider_name=provider_name)
```

This is raised by each provider's `_aretrieve_batch_results` when the batch status is not `completed`. The gateway endpoint returns `409 Conflict` in this case, which the Gateway provider maps to this exception.

### Gateway-version detection

When the Gateway provider receives a `404` on any `/v1/batches/*` endpoint, it should detect this and raise a more helpful error than the default "Model not found":

```python
# In Gateway provider's batch methods
try:
    response = await self._post_json("/v1/batches", body)
except Exception as e:
    if _is_404(e):
        msg = (
            "This gateway does not support batch operations. "
            "Upgrade your gateway to v0.X.0 or later."
        )
        raise ProviderError(message=msg, provider_name="gateway") from e
    raise
```

---

## Configuration

### New configuration options

**None.** Batch operations use the same authentication, base URL, and provider configuration as completions. No new environment variables, config file fields, or CLI flags are needed.

### Existing configuration reused

| Config | Purpose for batch |
|--------|-------------------|
| `GATEWAY_API_BASE` / `api_base` | Base URL for gateway batch endpoints |
| `GATEWAY_API_KEY` / `api_key` | Authentication for batch requests |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc. | Direct provider auth (Python SDK only) |
| Provider config in gateway YAML | Provider credentials used by gateway when proxying batch calls |

### Gateway-side configuration

**Request size limit:** The 10,000 item max for the `requests` array is enforced by Pydantic's `Field(max_length=10_000)`. This is a sensible default aligned with Anthropic's limit (the most restrictive provider). It is not user-configurable in this iteration — changing it requires a code change. If needed later, it can be made configurable via the gateway YAML config.

**Timeout:** The gateway should set a generous timeout for batch creation. This is configured in the ASGI server (uvicorn) settings or via a middleware timeout, not a new config option. Recommendation: ensure the default uvicorn `--timeout-keep-alive` is sufficient (default 5s is fine for keep-alive, but the request processing timeout depends on the ASGI framework — FastAPI doesn't have a built-in per-route timeout, so this should be handled by the upstream reverse proxy or a timeout middleware if needed).

---

## Naming Conventions

### Cross-SDK naming map

| Concept | Python (snake_case) | Rust (snake_case) | Go (PascalCase) | TypeScript (camelCase) | Gateway API |
|---------|--------------------|--------------------|-----------------|----------------------|-------------|
| Create batch | `create_batch()` | `create_batch()` | `CreateBatch()` | `createBatch()` | `POST /v1/batches` |
| Retrieve status | `retrieve_batch()` | `retrieve_batch()` | `RetrieveBatch()` | `retrieveBatch()` | `GET /v1/batches/{id}` |
| Cancel | `cancel_batch()` | `cancel_batch()` | `CancelBatch()` | `cancelBatch()` | `POST /v1/batches/{id}/cancel` |
| List | `list_batches()` | `list_batches()` | `ListBatches()` | `listBatches()` | `GET /v1/batches` |
| Get results | `retrieve_batch_results()` | `retrieve_batch_results()` | `RetrieveBatchResults()` | `retrieveBatchResults()` | `GET /v1/batches/{id}/results` |

### Type naming map

| Type | Python | Rust | Go | TypeScript |
|------|--------|------|-----|-----------|
| Batch job | `Batch` | `Batch` | `Batch` | `Batch` |
| Batch status | `str` (literal union) | `BatchStatus` (enum) | `BatchStatus` (string const) | `string` (from `Batch`) |
| Request counts | `BatchRequestCounts` | `BatchRequestCounts` | `BatchRequestCounts` | (inline in `Batch`) |
| Result container | `BatchResult` | `BatchResult` | `BatchResult` | `BatchResult` |
| Single result | `BatchResultItem` | `BatchResultItem` | `BatchResultItem` | `BatchResultItem` |
| Result error | `BatchResultError` | `BatchResultError` | `BatchResultError` | `BatchResultError` |
| Create params | (positional args) | `CreateBatchParams` | `CreateBatchParams` | `CreateBatchParams` |
| Single request | (dict in JSONL) | `BatchRequestItem` | `BatchRequestItem` | `BatchRequestItem` |
| List options | `after`/`limit` kwargs | `ListBatchesOptions` | `ListBatchesOptions` | `ListBatchesOptions` |
| Batch-not-complete error | `BatchNotCompleteError` | `AnyLLMError::BatchNotComplete` | `BatchNotCompleteError` | `BatchNotCompleteError` |

---

## Documentation Notes

### API reference (in scope — docstrings and OpenAPI)

Every public method/function/type must have:

1. **A one-line summary** of what it does
2. **Parameter documentation** (types, required vs optional, valid values)
3. **Return type documentation**
4. **Error conditions** — what errors can be raised/returned and when
5. **A minimal usage example** (in docstring for Python/Rust, in godoc for Go, in JSDoc for TS)

### Key points to cover in docstrings

**`create_batch`:**
- When using the gateway, the `model` parameter must use `provider:model` format
- The `requests` array has a maximum size of 10,000 items
- Returns immediately — the batch is processed asynchronously
- The returned `Batch` object's status will typically be `"validating"` or `"in_progress"`

**`retrieve_batch_results`:**
- Must only be called after the batch status is `"completed"`
- Raises `BatchNotCompleteError` if called prematurely
- Each `BatchResultItem` has either `result` (success) or `error` (failure), never both
- Match results to original requests via `custom_id`

**`cancel_batch`:**
- Cancellation is not immediate — status transitions to `"cancelling"` then `"cancelled"`
- Batches that are already completed cannot be cancelled

**Provider parameter (gateway SDKs):**
- All retrieve/cancel/list/results methods require a `provider` parameter
- This is the provider name (e.g., `"openai"`, `"anthropic"`, `"mistral"`), not the full `provider:model` string
- The provider is returned in the `create_batch` response for convenience

### Examples to include

1. **End-to-end batch workflow** — create, poll, retrieve results (one per SDK)
2. **Error handling** — catching `BatchNotCompleteError`, handling partial failures in results
3. **Processing results** — iterating over `BatchResult.results`, matching `custom_id`

### Migration note for existing Python SDK users

> **Upgrading from experimental batch API:** The batch API is now stable. If you were suppressing the `FutureWarning` with `warnings.filterwarnings("ignore", category=FutureWarning)`, you can remove that filter. The `create_batch`, `retrieve_batch`, `cancel_batch`, and `list_batches` signatures are unchanged. A new `retrieve_batch_results` method is now available for downloading results.

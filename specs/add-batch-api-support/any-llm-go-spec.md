# Implementation Spec: any-llm-go

## Context

The any-llm-go SDK provides a Go interface for communicating with LLM providers. It currently has no Gateway provider (only a Platform provider that delegates to underlying providers after platform authentication). This work adds: (1) a new `BatchProvider` interface following the optional-interface pattern of `EmbeddingProvider`, (2) a new `gateway` provider package that implements both `Provider` (for completions) and `BatchProvider` (for batch operations), and (3) all supporting batch types and error types.

This is the largest scope among the non-Python SDKs because it requires building an entire Gateway provider from scratch, including completion support. The batch methods call the gateway's `/v1/batches/*` HTTP endpoints.

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

| HTTP Status | Meaning | Go Error Type |
|-------------|---------|---------------|
| 401/403 | Auth failure | `*errors.AuthenticationError` |
| 404 | Batch not found / gateway too old | `*errors.ProviderError` with upgrade hint |
| 409 | Batch not complete | `*errors.BatchNotCompleteError` (new) |
| 422 | Unsupported provider | `*errors.ProviderError` |
| 429 | Rate limited | `*errors.RateLimitError` |
| 502 | Upstream error | `*errors.ProviderError` |

### Authentication

The Gateway provider uses the `X-AnyLLM-Key: Bearer <key>` header, consistent with the Rust and TypeScript SDKs. The key is resolved from `config.WithAPIKey()` or the `GATEWAY_API_KEY` environment variable.

## Changes Required

### 1. New batch types in `providers/types.go`

Add after the existing types, following Go conventions (alphabetical fields, `json` tags with `omitempty`, pointer types for optional fields):

```go
// Batch represents a batch job.
type Batch struct {
    CompletedAt      *int64              `json:"completed_at,omitempty"`
    CompletionWindow string              `json:"completion_window"`
    CreatedAt        int64               `json:"created_at"`
    Endpoint         string              `json:"endpoint"`
    ErrorFileID      string              `json:"error_file_id,omitempty"`
    ID               string              `json:"id"`
    InProgressAt     *int64              `json:"in_progress_at,omitempty"`
    InputFileID      string              `json:"input_file_id,omitempty"`
    Metadata         map[string]string   `json:"metadata,omitempty"`
    Object           string              `json:"object"`
    OutputFileID     string              `json:"output_file_id,omitempty"`
    Provider         string              `json:"provider,omitempty"`
    RequestCounts    *BatchRequestCounts `json:"request_counts,omitempty"`
    Status           BatchStatus         `json:"status"`
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
    After string
    Limit *int
}

// BatchResult contains the results of a completed batch job.
type BatchResult struct {
    Results []BatchResultItem `json:"results"`
}

// BatchResultItem is the result of a single request within a batch.
type BatchResultItem struct {
    CustomID string            `json:"custom_id"`
    Error    *BatchResultError `json:"error,omitempty"`
    Result   *ChatCompletion   `json:"result,omitempty"`
}

// BatchResultError is an error for a single request within a batch.
type BatchResultError struct {
    Code    string `json:"code"`
    Message string `json:"message"`
}
```

### 2. New `BatchProvider` interface in `providers/types.go`

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

### 3. New error types in `errors/errors.go`

Add a new sentinel error and typed error struct:

```go
// Sentinel error
var ErrBatchNotComplete = stderrors.New("batch not yet complete")

// Error code constant
const CodeBatchNotComplete = "batch_not_complete"

// BatchNotCompleteError is returned when retrieve_batch_results is called
// on a batch that is not yet complete.
type BatchNotCompleteError struct {
    BaseError
    BatchID string
    Status  string
}

// NewBatchNotCompleteError creates a new BatchNotCompleteError.
func NewBatchNotCompleteError(provider string, batchID string, status string) *BatchNotCompleteError {
    return &BatchNotCompleteError{
        BaseError: BaseError{
            Code:     CodeBatchNotComplete,
            Provider: provider,
            Err:      fmt.Errorf("batch '%s' is not yet complete (status: %s)", batchID, status),
            sentinel: ErrBatchNotComplete,
        },
        BatchID: batchID,
        Status:  status,
    }
}
```

### 4. Re-exports in `anyllm.go`

Add type aliases and sentinel error:

```go
// Batch types
type Batch = providers.Batch
type BatchStatus = providers.BatchStatus
type BatchRequestCounts = providers.BatchRequestCounts
type BatchRequestItem = providers.BatchRequestItem
type CreateBatchParams = providers.CreateBatchParams
type ListBatchesOptions = providers.ListBatchesOptions
type BatchResult = providers.BatchResult
type BatchResultItem = providers.BatchResultItem
type BatchResultError = providers.BatchResultError
type BatchProvider = providers.BatchProvider

// Batch status constants
const (
    BatchStatusValidating = providers.BatchStatusValidating
    BatchStatusFailed     = providers.BatchStatusFailed
    BatchStatusInProgress = providers.BatchStatusInProgress
    BatchStatusFinalizing = providers.BatchStatusFinalizing
    BatchStatusCompleted  = providers.BatchStatusCompleted
    BatchStatusExpired    = providers.BatchStatusExpired
    BatchStatusCancelling = providers.BatchStatusCancelling
    BatchStatusCancelled  = providers.BatchStatusCancelled
)

// Error types
type BatchNotCompleteError = errors.BatchNotCompleteError
var ErrBatchNotComplete = errors.ErrBatchNotComplete
```

### 5. New Gateway provider package: `providers/gateway/gateway.go`

This is a new provider that communicates directly with the any-llm gateway over HTTP. It uses `net/http` (via `config.HTTPClient()`) and implements both `Provider` and `BatchProvider`.

```go
package gateway

import (
    "context"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "net/url"
    "strings"

    "github.com/mozilla-ai/any-llm-go/config"
    "github.com/mozilla-ai/any-llm-go/errors"
    "github.com/mozilla-ai/any-llm-go/providers"
)

const (
    name             = "gateway"
    envAPIKey        = "GATEWAY_API_KEY"
    envAPIBase       = "GATEWAY_API_BASE"
    headerName       = "X-AnyLLM-Key"
)

// Provider communicates with the any-llm gateway.
type Provider struct {
    apiBase    string
    apiKey     string
    httpClient *http.Client
}

// Compile-time interface checks.
var (
    _ providers.BatchProvider      = (*Provider)(nil)
    _ providers.CapabilityProvider = (*Provider)(nil)
    _ providers.Provider           = (*Provider)(nil)
)

// New creates a new Gateway provider.
func New(opts ...config.Option) (*Provider, error) {
    cfg, err := config.New(opts...)
    if err != nil {
        return nil, fmt.Errorf("gateway: %w", err)
    }

    apiBase, err := cfg.ResolveBaseURL(envAPIBase, "")
    if err != nil || apiBase == "" {
        return nil, errors.NewProviderError(name,
            fmt.Errorf("api_base is required (set via WithBaseURL or %s env var)", envAPIBase))
    }
    apiBase = strings.TrimRight(apiBase, "/")

    apiKey := cfg.ResolveAPIKey(envAPIKey)

    return &Provider{
        apiBase:    apiBase,
        apiKey:     apiKey,
        httpClient: cfg.HTTPClient(),
    }, nil
}

func (p *Provider) Name() string { return name }

func (p *Provider) Capabilities() providers.Capabilities {
    return providers.Capabilities{
        Completion: true,
        Streaming:  true,
        Tools:      true,
        Images:     true,
        Reasoning:  true,
        PDF:        true,
        Embedding:  true,
    }
}
```

**Completion methods** (implementing `Provider` interface):

```go
func (p *Provider) Completion(ctx context.Context, params providers.CompletionParams) (*providers.ChatCompletion, error) {
    body, err := json.Marshal(convertParamsToRequest(params))
    if err != nil {
        return nil, errors.NewInvalidRequestError(name, err)
    }
    resp, err := p.doRequest(ctx, http.MethodPost, "/v1/chat/completions", body)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()
    if resp.StatusCode != http.StatusOK {
        return nil, p.handleHTTPError(resp, "/v1/chat/completions")
    }
    var completion providers.ChatCompletion
    if err := json.NewDecoder(resp.Body).Decode(&completion); err != nil {
        return nil, errors.NewProviderError(name, fmt.Errorf("failed to decode response: %w", err))
    }
    return &completion, nil
}

func (p *Provider) CompletionStream(ctx context.Context, params providers.CompletionParams) (<-chan providers.ChatCompletionChunk, <-chan error) {
    // SSE streaming implementation following the z.ai provider pattern
    // POST to /v1/chat/completions with stream=true
    // Parse SSE events, convert to ChatCompletionChunk
    // ...
}
```

**Batch methods** (implementing `BatchProvider` interface):

```go
func (p *Provider) CreateBatch(ctx context.Context, params providers.CreateBatchParams) (*providers.Batch, error) {
    body, err := json.Marshal(params)
    if err != nil {
        return nil, errors.NewInvalidRequestError(name, err)
    }
    resp, err := p.doRequest(ctx, http.MethodPost, "/v1/batches", body)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()
    if resp.StatusCode != http.StatusOK {
        return nil, p.handleBatchError(resp, "/v1/batches")
    }
    var batch providers.Batch
    if err := json.NewDecoder(resp.Body).Decode(&batch); err != nil {
        return nil, errors.NewProviderError(name, fmt.Errorf("failed to decode batch response: %w", err))
    }
    return &batch, nil
}

func (p *Provider) RetrieveBatch(ctx context.Context, batchID string, provider string) (*providers.Batch, error) {
    path := fmt.Sprintf("/v1/batches/%s?provider=%s", url.PathEscape(batchID), url.QueryEscape(provider))
    resp, err := p.doRequest(ctx, http.MethodGet, path, nil)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()
    if resp.StatusCode != http.StatusOK {
        return nil, p.handleBatchError(resp, path)
    }
    var batch providers.Batch
    if err := json.NewDecoder(resp.Body).Decode(&batch); err != nil {
        return nil, errors.NewProviderError(name, fmt.Errorf("failed to decode batch response: %w", err))
    }
    return &batch, nil
}

func (p *Provider) CancelBatch(ctx context.Context, batchID string, provider string) (*providers.Batch, error) {
    path := fmt.Sprintf("/v1/batches/%s/cancel?provider=%s", url.PathEscape(batchID), url.QueryEscape(provider))
    resp, err := p.doRequest(ctx, http.MethodPost, path, nil)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()
    if resp.StatusCode != http.StatusOK {
        return nil, p.handleBatchError(resp, path)
    }
    var batch providers.Batch
    if err := json.NewDecoder(resp.Body).Decode(&batch); err != nil {
        return nil, errors.NewProviderError(name, fmt.Errorf("failed to decode batch response: %w", err))
    }
    return &batch, nil
}

func (p *Provider) ListBatches(ctx context.Context, provider string, opts providers.ListBatchesOptions) ([]providers.Batch, error) {
    params := url.Values{"provider": {provider}}
    if opts.After != "" {
        params.Set("after", opts.After)
    }
    if opts.Limit != nil {
        params.Set("limit", fmt.Sprintf("%d", *opts.Limit))
    }
    path := "/v1/batches?" + params.Encode()
    resp, err := p.doRequest(ctx, http.MethodGet, path, nil)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()
    if resp.StatusCode != http.StatusOK {
        return nil, p.handleBatchError(resp, path)
    }
    var listResp struct {
        Data []providers.Batch `json:"data"`
    }
    if err := json.NewDecoder(resp.Body).Decode(&listResp); err != nil {
        return nil, errors.NewProviderError(name, fmt.Errorf("failed to decode list response: %w", err))
    }
    return listResp.Data, nil
}

func (p *Provider) RetrieveBatchResults(ctx context.Context, batchID string, provider string) (*providers.BatchResult, error) {
    path := fmt.Sprintf("/v1/batches/%s/results?provider=%s", url.PathEscape(batchID), url.QueryEscape(provider))
    resp, err := p.doRequest(ctx, http.MethodGet, path, nil)
    if err != nil {
        return nil, err
    }
    defer resp.Body.Close()
    if resp.StatusCode != http.StatusOK {
        return nil, p.handleBatchError(resp, path)
    }
    var result providers.BatchResult
    if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
        return nil, errors.NewProviderError(name, fmt.Errorf("failed to decode batch results: %w", err))
    }
    return &result, nil
}
```

**Private helpers:**

```go
func (p *Provider) doRequest(ctx context.Context, method, path string, body []byte) (*http.Response, error) {
    fullURL := p.apiBase + path
    var bodyReader io.Reader
    if body != nil {
        bodyReader = bytes.NewReader(body)
    }
    req, err := http.NewRequestWithContext(ctx, method, fullURL, bodyReader)
    if err != nil {
        return nil, errors.NewProviderError(name, err)
    }
    req.Header.Set("Content-Type", "application/json")
    if p.apiKey != "" {
        req.Header.Set(headerName, "Bearer "+p.apiKey)
    }
    return p.httpClient.Do(req)
}

func (p *Provider) handleBatchError(resp *http.Response, path string) error {
    bodyBytes, _ := io.ReadAll(resp.Body)
    var detail struct {
        Detail string `json:"detail"`
    }
    _ = json.Unmarshal(bodyBytes, &detail)
    msg := detail.Detail
    if msg == "" {
        msg = string(bodyBytes)
    }

    switch resp.StatusCode {
    case http.StatusUnauthorized, http.StatusForbidden:
        return errors.NewAuthenticationError(name, fmt.Errorf("%s", msg))
    case http.StatusNotFound:
        if strings.Contains(path, "/v1/batches") {
            return errors.NewProviderError(name,
                fmt.Errorf("this gateway does not support batch operations; upgrade your gateway"))
        }
        return errors.NewModelNotFoundError(name, fmt.Errorf("%s", msg))
    case http.StatusConflict:
        // Extract batch ID and status from the error message if possible
        batchID, batchStatus := parseBatchNotCompleteDetail(msg)
        return errors.NewBatchNotCompleteError(name, batchID, batchStatus)
    case http.StatusUnprocessableEntity:
        return errors.NewProviderError(name, fmt.Errorf("%s", msg))
    case http.StatusTooManyRequests:
        return errors.NewRateLimitError(name, fmt.Errorf("%s", msg))
    case http.StatusBadGateway:
        return errors.NewProviderError(name, fmt.Errorf("upstream provider error: %s", msg))
    default:
        return errors.NewProviderError(name, fmt.Errorf("HTTP %d: %s", resp.StatusCode, msg))
    }
}

func (p *Provider) handleHTTPError(resp *http.Response, path string) error {
    // Reuse similar logic but without batch-specific 409 handling
    // or delegate to handleBatchError which handles all cases
    return p.handleBatchError(resp, path)
}

// parseBatchNotCompleteDetail extracts batch ID and status from the error detail.
func parseBatchNotCompleteDetail(detail string) (batchID, status string) {
    // Parse: "Batch 'batch_abc' is not yet complete (status: in_progress)..."
    // Simple string parsing or regex
    // Return best-effort values, empty strings if parsing fails
    return "", "unknown"
}

// convertParamsToRequest converts CompletionParams to OpenAI wire format.
func convertParamsToRequest(params providers.CompletionParams) map[string]any {
    req := map[string]any{
        "model":    params.Model,
        "messages": params.Messages,
    }
    if params.Temperature != nil {
        req["temperature"] = *params.Temperature
    }
    if params.MaxTokens != nil {
        req["max_completion_tokens"] = *params.MaxTokens
    }
    if params.TopP != nil {
        req["top_p"] = *params.TopP
    }
    if params.Stream != nil && *params.Stream {
        req["stream"] = true
        req["stream_options"] = map[string]any{"include_usage": true}
    }
    if params.Tools != nil {
        req["tools"] = params.Tools
    }
    if params.ToolChoice != nil {
        req["tool_choice"] = params.ToolChoice
    }
    if params.ResponseFormat != nil {
        req["response_format"] = params.ResponseFormat
    }
    if params.ReasoningEffort != "" {
        req["reasoning_effort"] = params.ReasoningEffort
    }
    // Add other fields as needed
    return req
}
```

### 6. Test file: `providers/gateway/gateway_test.go`

Follow the existing provider test patterns (`t.Parallel()`, table-driven, `testutil` fixtures, `require`).

## Implementation Steps

1. Add batch types to `providers/types.go` (`Batch`, `BatchStatus`, etc.).
2. Add `BatchProvider` interface to `providers/types.go`.
3. Add `BatchNotCompleteError` and `ErrBatchNotComplete` to `errors/errors.go`.
4. Add re-exports to `anyllm.go`.
5. Create `providers/gateway/gateway.go` with the `Provider` struct, constructor, `Name()`, `Capabilities()`.
6. Implement `Completion()` and `CompletionStream()` for the gateway.
7. Implement all five batch methods.
8. Implement `doRequest()`, `handleBatchError()`, `convertParamsToRequest()` helpers.
9. Write unit tests with `httptest` fake servers.
10. Write integration tests (gated by API key / live gateway).

## Testing Requirements

### Unit Tests (`providers/gateway/gateway_test.go`)

Follow existing patterns: `t.Parallel()`, `require` assertions, `testutil.FakeCompletionServer` where applicable.

**Construction tests:**
- `TestNewRequiresAPIBase` — Error when no base URL.
- `TestNewWithAPIKey` — Key stored, sent in header.
- `TestNewWithoutAPIKey` — No error, no auth header.
- `TestNewFromEnvVars` — Resolves from `GATEWAY_API_KEY` and `GATEWAY_API_BASE`.

**Interface checks** (compile-time):
```go
var (
    _ providers.BatchProvider      = (*Provider)(nil)
    _ providers.CapabilityProvider = (*Provider)(nil)
    _ providers.Provider           = (*Provider)(nil)
)
```

**Completion tests (httptest):**
- `TestCompletionSuccess` — Verify request body, response parsing.
- `TestCompletionSendsAuthHeader` — Verify `X-AnyLLM-Key: Bearer <key>`.
- `TestCompletionHTTPError` — Verify error mapping.

**Batch tests (httptest):**
- `TestCreateBatchSuccess` — POST to `/v1/batches` with correct body, response parsed as `Batch`.
- `TestCreateBatchSendsAuthHeader` — `X-AnyLLM-Key` header present.
- `TestRetrieveBatchSendsProviderParam` — GET with `?provider=openai`.
- `TestCancelBatchSuccess` — POST to correct URL.
- `TestListBatchesPagination` — Verify `after` and `limit` query params.
- `TestRetrieveBatchResultsSuccess` — Response parsed as `BatchResult`.
- `TestBatchError409` — 409 → `BatchNotCompleteError`, check `errors.Is(err, errors.ErrBatchNotComplete)`.
- `TestBatchError404` — 404 → `ProviderError` with "upgrade gateway" message.
- `TestBatchError401` — 401 → `AuthenticationError`.
- `TestBatchError422` — 422 → `ProviderError`.
- `TestBatchError502` — 502 → `ProviderError`.

### Integration Tests

Gated by `testutil.SkipIfNoAPIKey("gateway")` or equivalent:
- `TestIntegrationCreateBatch` — Full flow against live gateway.
- `TestIntegrationBatchNotComplete` — Verify error on incomplete batch.

## Acceptance Criteria

1. `providers.BatchProvider` interface exists and the Gateway provider satisfies it (compile-time check).
2. `gateway.New(config.WithBaseURL(...), config.WithAPIKey(...))` constructs a working provider.
3. Gateway provider's `Completion()` works against a live or mocked gateway.
4. All five batch methods make correct HTTP calls with proper auth headers and query params.
5. `errors.Is(err, errors.ErrBatchNotComplete)` works on 409 errors.
6. `errors.As(err, &batchErr)` provides `BatchID` and `Status` fields.
7. All unit tests pass with httptest.
8. Batch types are re-exported from the root `anyllm` package.
9. No changes to existing provider implementations.

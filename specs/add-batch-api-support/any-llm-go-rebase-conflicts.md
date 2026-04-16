# Rebase Conflict — any-llm-go

The rebase onto `origin/main` produced merge conflicts.

## Conflicted files

```
providers/gateway/gateway_test.go
```

## Full diff (with conflict markers)

```diff
[1mdiff --cc providers/gateway/gateway_test.go[m
[1mindex f7c7ed6,ee0cdd0..0000000[m
[1m--- a/providers/gateway/gateway_test.go[m
[1m+++ b/providers/gateway/gateway_test.go[m
[36m@@@ -1414,130 -813,248 +1415,359 @@@[m [mfunc TestParseBatchNotCompleteDetail(t [m
  	}[m
  }[m
  [m
[31m -func TestConvertParamsToRequest(t *testing.T) {[m
[32m +// --- Integration tests ---[m
[32m +[m
[32m +func TestIntegrationCompletion(t *testing.T) {[m
  	t.Parallel()[m
  [m
[32m++<<<<<<< HEAD[m
[32m +	gatewayURL, token := gatewayCredentials()[m
[32m +	if gatewayURL == "" || token == "" {[m
[32m +		t.Skip("GATEWAY_API_BASE and GATEWAY_PLATFORM_TOKEN not set")[m
[32m +	}[m
[32m++=======[m
[32m+ 	t.Run("basic params", func(t *testing.T) {[m
[32m+ 		t.Parallel()[m
[32m+ [m
[32m+ 		temp := 0.7[m
[32m+ 		topP := 0.9[m
[32m+ 		maxTokens := 100[m
[32m+ [m
[32m+ 		params := providers.CompletionParams{[m
[32m+ 			Model: "test-model",[m
[32m+ 			Messages: []providers.Message{[m
[32m+ 				{Role: "user", Content: "Hello"},[m
[32m+ 			},[m
[32m+ 			Temperature: &temp,[m
[32m+ 			TopP:        &topP,[m
[32m+ 			MaxTokens:   &maxTokens,[m
[32m+ 			Stop:        []string{"END"},[m
[32m+ 			User:        "test-user",[m
[32m+ 		}[m
[32m+ [m
[32m+ 		req := convertParamsToRequest(params)[m
[32m+ [m
[32m+ 		require.Equal(t, "test-model", req["model"])[m
[32m+ 		require.Equal(t, 0.7, req["temperature"])[m
[32m+ 		require.Equal(t, 0.9, req["top_p"])[m
[32m+ 		require.Equal(t, 100, req["max_completion_tokens"])[m
[32m+ 		require.Equal(t, []string{"END"}, req["stop"])[m
[32m+ 		require.Equal(t, "test-user", req["user"])[m
[32m+ 	})[m
[32m+ [m
[32m+ 	t.Run("stream params", func(t *testing.T) {[m
[32m+ 		t.Parallel()[m
[32m+ [m
[32m+ 		params := providers.CompletionParams{[m
[32m+ 			Model: "test-model",[m
[32m+ 			Messages: []providers.Message{[m
[32m+ 				{Role: "user", Content: "Hello"},[m
[32m+ 			},[m
[32m+ 			Stream: true,[m
[32m+ 		}[m
[32m+ [m
[32m+ 		req := convertParamsToRequest(params)[m
[32m+ [m
[32m+ 		require.Equal(t, true, req["stream"])[m
[32m+ 		require.NotNil(t, req["stream_options"])[m
[32m+ 	})[m
[32m+ [m
[32m+ 	t.Run("reasoning effort", func(t *testing.T) {[m
[32m+ 		t.Parallel()[m
[32m+ [m
[32m+ 		params := providers.CompletionParams{[m
[32m+ 			Model: "test-model",[m
[32m+ 			Messages: []providers.Message{[m
[32m+ 				{Role: "user", Content: "Think carefully"},[m
[32m+ 			},[m
[32m+ 			ReasoningEffort: providers.ReasoningEffortHigh,[m
[32m+ 		}[m
[32m+ [m
[32m+ 		req := convertParamsToRequest(params)[m
[32m+ [m
[32m+ 		require.Equal(t, providers.ReasoningEffortHigh, req["reasoning_effort"])[m
[32m+ 	})[m
[32m+ [m
[32m+ 	t.Run("omits nil optional fields", func(t *testing.T) {[m
[32m+ 		t.Parallel()[m
[32m+ [m
[32m+ 		params := providers.CompletionParams{[m
[32m+ 			Model: "test-model",[m
[32m+ 			Messages: []providers.Message{[m
[32m+ 				{Role: "user", Content: "Hello"},[m
[32m+ 			},[m
[32m+ 		}[m
[32m+ [m
[32m+ 		req := convertParamsToRequest(params)[m
[32m+ [m
[32m+ 		require.NotContains(t, req, "temperature")[m
[32m+ 		require.NotContains(t, req, "top_p")[m
[32m+ 		require.NotContains(t, req, "max_completion_tokens")[m
[32m+ 		require.NotContains(t, req, "stop")[m
[32m+ 		require.NotContains(t, req, "stream")[m
[32m+ 		require.NotContains(t, req, "tools")[m
[32m+ 		require.NotContains(t, req, "tool_choice")[m
[32m+ 		require.NotContains(t, req, "response_format")[m
[32m+ 		require.NotContains(t, req, "reasoning_effort")[m
[32m+ 		require.NotContains(t, req, "seed")[m
[32m+ 		require.NotContains(t, req, "user")[m
[32m+ 		require.NotContains(t, req, "parallel_tool_calls")[m
[32m+ 	})[m
[32m+ }[m
[32m+ [m
[32m+ func TestCompletionHTTPError409IsNotBatchError(t *testing.T) {[m
[32m+ 	t.Parallel()[m
[32m+ [m
[32m+ 	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {[m
[32m+ 		w.Header().Set("Content-Type", "application/json")[m
[32m+ 		w.WriteHeader(http.StatusConflict)[m
[32m+ 		_, _ = w.Write([]byte(`{"detail": "conflict on completion endpoint"}`))[m
[32m+ 	}))[m
[32m+ 	t.Cleanup(srv.Close)[m
[32m+ [m
[32m+ 	provider, err := New([m
[32m+ 		config.WithBaseURL(srv.URL),[m
[32m+ 		config.WithAPIKey("test-key"),[m
[32m+ 	)[m
[32m+ 	require.NoError(t, err)[m
[32m+ [m
[32m+ 	_, err = provider.Completion(context.Background(), providers.CompletionParams{[m
[32m+ 		Model:    "test-model",[m
[32m+ 		Messages: []providers.Message{{Role: "user", Content: "hi"}},[m
[32m+ 	})[m
[32m+ 	require.Error(t, err)[m
[32m+ [m
[32m+ 	// 409 on a completion endpoint should NOT produce a BatchNotCompleteError.[m
[32m+ 	require.False(t, stderrors.Is(err, errors.ErrBatchNotComplete),[m
[32m+ 		"completion 409 should not map to ErrBatchNotComplete, got %v", err)[m
[32m+ 	// It should be a generic ProviderError.[m
[32m+ 	require.True(t, stderrors.Is(err, errors.ErrProvider),[m
[32m+ 		"completion 409 should map to ErrProvider, got %v", err)[m
[32m+ }[m
[32m+ [m
[32m+ func TestCompletionHTTPError404IsModelNotFound(t *testing.T) {[m
[32m+ 	t.Parallel()[m
[32m+ [m
[32m+ 	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {[m
[32m+ 		w.Header().Set("Content-Type", "application/json")[m
[32m+ 		w.WriteHeader(http.StatusNotFound)[m
[32m+ 		_, _ = w.Write([]byte(`{"detail": "model not found"}`))[m
[32m+ 	}))[m
[32m+ 	t.Cleanup(srv.Close)[m
[32m+ [m
[32m+ 	provider, err := New([m
[32m+ 		config.WithBaseURL(srv.URL),[m
[32m+ 		config.WithAPIKey("test-key"),[m
[32m+ 	)[m
[32m+ 	require.NoError(t, err)[m
[32m+ [m
[32m+ 	_, err = provider.Completion(context.Background(), providers.CompletionParams{[m
[32m+ 		Model:    "nonexistent:model",[m
[32m+ 		Messages: []providers.Message{{Role: "user", Content: "hi"}},[m
[32m+ 	})[m
[32m+ 	require.Error(t, err)[m
[32m+ [m
[32m+ 	// 404 on a completion endpoint should produce ModelNotFoundError, not "upgrade your gateway".[m
[32m+ 	require.True(t, stderrors.Is(err, errors.ErrModelNotFound),[m
[32m+ 		"completion 404 should map to ErrModelNotFound, got %v", err)[m
[32m+ 	require.NotContains(t, err.Error(), "upgrade your gateway")[m
[32m+ }[m
[32m+ [m
[32m+ func TestListBatchesWithoutPagination(t *testing.T) {[m
[32m+ 	t.Parallel()[m
[32m+ [m
[32m+ 	var capturedPath string[m
[32m+ [m
[32m+ 	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {[m
[32m+ 		capturedPath = r.URL.RequestURI()[m
[32m+ 		w.Header().Set("Content-Type", "application/json")[m
[32m+ 		_, _ = w.Write([]byte(`{"data": []}`))[m
[32m+ 	}))[m
[32m+ 	t.Cleanup(srv.Close)[m
[32m++>>>>>>> 2d6f696 (test(gateway): add integration test stubs and handleHTTPError tests)[m
  [m
  	provider, err := New([m
[31m -		config.WithBaseURL(srv.URL),[m
[31m -		config.WithAPIKey("test-key"),[m
[32m +		config.WithBaseURL(gatewayURL),[m
[32m +		config.WithAPIKey(token),[m
[32m +		WithPlatformMode(),[m
  	)[m
  	require.NoError(t, err)[m
  [m
[31m -	batches, err := provider.ListBatches(context.Background(), "openai", providers.ListBatchesOptions{})[m
[32m +	ctx := context.Background()[m
[32m +	resp, err := provider.Completion(ctx, providers.CompletionParams{[m
[32m +		Model: "openai:gpt-4o-mini",[m
[32m +		Messages: []providers.Message{[m
[32m +			{Role: providers.RoleUser, Content: "Say 'hello' and nothing else."},[m
[32m +		},[m
[32m +	})[m
  	require.NoError(t, err)[m
[31m -	require.Empty(t, batches)[m
  [m
[31m -	// Verify only provider param is sent (no after or limit).[m
[31m -	require.Contains(t, capturedPath, "provider=openai")[m
[31m -	require.NotContains(t, capturedPath, "after=")[m
[31m -	require.NotContains(t, capturedPath, "limit=")[m
[32m +	require.NotEmpty(t, resp.ID)[m
[32m +	require.Equal(t, objectChatCompletion, resp.Object)[m
[32m +	require.Len(t, resp.Choices, 1)[m
[32m +	require.NotEmpty(t, resp.Choices[0].Message.ContentString())[m
[32m +	require.Contains(t, strings.ToLower(resp.Choices[0].Message.ContentString()), "hello")[m
[32m +[m
[32m +	t.Logf("Response: %s", resp.Choices[0].Message.ContentString())[m
[32m +	if resp.Usage != nil {[m
[32m +		t.Logf("Tokens used: %d", resp.Usage.TotalTokens)[m
[32m +	}[m
[32m +}[m
[32m +[m
[32m +func TestIntegrationCompletionStream(t *testing.T) {[m
[32m +	t.Parallel()[m
[32m +[m
[32m +	gatewayURL, token := gatewayCredentials()[m
[32m +	if gatewayURL == "" || token == "" {[m
[32m +		t.Skip("GATEWAY_API_BASE and GATEWAY_PLATFORM_TOKEN not set")[m
[32m +	}[m
[32m +[m
[32m +	provider, err := New([m
[32m +		config.WithBaseURL(gatewayURL),[m
[32m +		config.WithAPIKey(token),[m
[32m +		WithPlatformMode(),[m
[32m +	)[m
[32m +	require.NoError(t, err)[m
[32m +[m
[32m +	ctx := context.Background()[m
[32m +	chunks, errs := provider.CompletionStream(ctx, providers.CompletionParams{[m
[32m +		Model: "openai:gpt-4o-mini",[m
[32m +		Messages: []providers.Message{[m
[32m +			{Role: providers.RoleUser, Content: "Count from 1 to 3, one number per line."},[m
[32m +		},[m
[32m +		Stream: true,[m
[32m +	})[m
[32m +[m
[32m +	var content strings.Builder[m
[32m +	chunkCount := 0[m
[32m +[m
[32m +	for chunk := range chunks {[m
[32m +		chunkCount++[m
[32m +		if len(chunk.Choices) > 0 && chunk.Choices[0].Delta.Content != "" {[m
[32m +			content.WriteString(chunk.Choices[0].Delta.Content)[m
[32m +		}[m
[32m +	}[m
[32m +[m
[32m +	err = <-errs[m
[32m +	require.NoError(t, err)[m
[32m +[m
[32m +	require.Greater(t, chunkCount, 0, "should have received chunks")[m
[32m +	require.NotEmpty(t, content.String(), "should have received content")[m
[32m +[m
[32m +	t.Logf("Received %d chunks", chunkCount)[m
[32m +	t.Logf("Content: %s", content.String())[m
[32m +}[m
[32m +[m
[32m +// Test helpers.[m
[32m +[m
[32m +// mockRoundTripper records whether it was called and delegates to a base transport.[m
[32m +type mockRoundTripper struct {[m
[32m +	base   http.RoundTripper[m
[32m +	called bool[m
[32m +	mu     sync.Mutex[m
[32m +}[m
[32m +[m
[32m +func (m *mockRoundTripper) RoundTrip(req *http.Request) (*http.Response, error) {[m
[32m +	m.mu.Lock()[m
[32m +	m.called = true[m
[32m +	m.mu.Unlock()[m
[32m +	return m.base.RoundTrip(req)[m
[32m +}[m
[32m +[m
[32m +// mockCompletionParams returns standard completion params for tests.[m
[32m +func mockCompletionParams() providers.CompletionParams {[m
[32m +	return providers.CompletionParams{[m
[32m +		Model:    "openai:gpt-4o-mini",[m
[32m +		Messages: []providers.Message{{Role: providers.RoleUser, Content: "hello"}},[m
[32m +	}[m
[32m +}[m
[32m +[m
[32m +// mockCompletionResponse returns a minimal valid JSON completion response.[m
[32m +func mockCompletionResponse(content string) string {[m
[32m +	return fmt.Sprintf(`{[m
[32m +		"id": "chatcmpl-test",[m
[32m +		"object": "chat.completion",[m
[32m +		"created": 1700000000,[m
[32m +		"model": "test-model",[m
[32m +		"choices": [{[m
[32m +			"index": 0,[m
[32m +			"message": {"role": "assistant", "content": %q},[m
[32m +			"finish_reason": "stop"[m
[32m +		}],[m
[32m +		"usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}[m
[32m +	}`, content)[m
[32m +}[m
[32m +[m
[32m +// gatewayCredentials returns the gateway URL and platform token from[m
[32m +// environment variables. Returns empty strings if not set.[m
[32m +func gatewayCredentials() (gatewayURL string, token string) {[m
[32m +	return os.Getenv(envAPIBase), os.Getenv(envPlatformToken)[m
  }[m
[32m+ [m
[32m+ // --- Integration tests (gated by GATEWAY_API_KEY) ---[m
[32m+ [m
[32m+ func TestIntegrationCreateAndRetrieveBatch(t *testing.T) {[m
[32m+ 	if testutil.SkipIfNoAPIKey(providerName) {[m
[32m+ 		t.Skip("GATEWAY_API_KEY not set")[m
[32m+ 	}[m
[32m+ [m
[32m+ 	provider, err := New()[m
[32m+ 	require.NoError(t, err)[m
[32m+ [m
[32m+ 	ctx := context.Background()[m
[32m+ [m
[32m+ 	batch, err := provider.CreateBatch(ctx, providers.CreateBatchParams{[m
[32m+ 		Model: "openai:gpt-4o-mini",[m
[32m+ 		Requests: []providers.BatchRequestItem{[m
[32m+ 			{[m
[32m+ 				CustomID: "integration-req-1",[m
[32m+ 				Body: map[string]any{[m
[32m+ 					"messages":   []any{map[string]any{"role": "user", "content": "Say hello"}},[m
[32m+ 					"max_tokens": 10,[m
[32m+ 				},[m
[32m+ 			},[m
[32m+ 		},[m
[32m+ 		CompletionWindow: "24h",[m
[32m+ 	})[m
[32m+ 	require.NoError(t, err)[m
[32m+ 	require.NotEmpty(t, batch.ID)[m
[32m+ 	require.Equal(t, "batch", batch.Object)[m
[32m+ 	require.NotEmpty(t, batch.Provider)[m
[32m+ [m
[32m+ 	// Retrieve the batch we just created.[m
[32m+ 	retrieved, err := provider.RetrieveBatch(ctx, batch.ID, batch.Provider)[m
[32m+ 	require.NoError(t, err)[m
[32m+ 	require.Equal(t, batch.ID, retrieved.ID)[m
[32m+ }[m
[32m+ [m
[32m+ func TestIntegrationBatchNotComplete(t *testing.T) {[m
[32m+ 	if testutil.SkipIfNoAPIKey(providerName) {[m
[32m+ 		t.Skip("GATEWAY_API_KEY not set")[m
[32m+ 	}[m
[32m+ [m
[32m+ 	provider, err := New()[m
[32m+ 	require.NoError(t, err)[m
[32m+ [m
[32m+ 	ctx := context.Background()[m
[32m+ [m
[32m+ 	batch, err := provider.CreateBatch(ctx, providers.CreateBatchParams{[m
[32m+ 		Model: "openai:gpt-4o-mini",[m
[32m+ 		Requests: []providers.BatchRequestItem{[m
[32m+ 			{[m
[32m+ 				CustomID: "integration-req-1",[m
[32m+ 				Body: map[string]any{[m
[32m+ 					"messages":   []any{map[string]any{"role": "user", "content": "Say hello"}},[m
[32m+ 					"max_tokens": 10,[m
[32m+ 				},[m
[32m+ 			},[m
[32m+ 		},[m
[32m+ 		CompletionWindow: "24h",[m
[32m+ 	})[m
[32m+ 	require.NoError(t, err)[m
[32m+ [m
[32m+ 	// Immediately requesting results should fail since the batch is not yet complete.[m
[32m+ 	_, err = provider.RetrieveBatchResults(ctx, batch.ID, batch.Provider)[m
[32m+ 	require.Error(t, err)[m
[32m+ 	require.True(t, stderrors.Is(err, errors.ErrBatchNotComplete),[m
[32m+ 		"expected ErrBatchNotComplete, got %v", err)[m
[32m+ }[m

```

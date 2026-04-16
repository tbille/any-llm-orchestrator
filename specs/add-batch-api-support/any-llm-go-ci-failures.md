# CI Failures

## Lint
- State: FAILURE
- Details: https://github.com/mozilla-ai/any-llm-go/actions/runs/24511166203/job/71642411859

## Run 24511166203 — Failed Log

```
Lint	golangci-lint	﻿2026-04-16T12:50:16.0984465Z ##[group]Run golangci/golangci-lint-action@v9
Lint	golangci-lint	2026-04-16T12:50:16.0985672Z with:
Lint	golangci-lint	2026-04-16T12:50:16.0986372Z   version: v2.4.0
Lint	golangci-lint	2026-04-16T12:50:16.0987167Z   install-mode: binary
Lint	golangci-lint	2026-04-16T12:50:16.0988020Z   install-only: false
Lint	golangci-lint	2026-04-16T12:50:16.0989238Z   github-token: ***
Lint	golangci-lint	2026-04-16T12:50:16.0990044Z   verify: true
Lint	golangci-lint	2026-04-16T12:50:16.0991060Z   only-new-issues: false
Lint	golangci-lint	2026-04-16T12:50:16.0991949Z   skip-cache: false
Lint	golangci-lint	2026-04-16T12:50:16.0992775Z   skip-save-cache: false
Lint	golangci-lint	2026-04-16T12:50:16.0993702Z   cache-invalidation-interval: 7
Lint	golangci-lint	2026-04-16T12:50:16.0994730Z   problem-matchers: false
Lint	golangci-lint	2026-04-16T12:50:16.0995595Z env:
Lint	golangci-lint	2026-04-16T12:50:16.0996294Z   GOTOOLCHAIN: local
Lint	golangci-lint	2026-04-16T12:50:16.0997083Z ##[endgroup]
Lint	golangci-lint	2026-04-16T12:50:16.2483301Z ##[group]Restore cache
Lint	golangci-lint	2026-04-16T12:50:16.2486878Z Checking for go.mod: go.mod
Lint	golangci-lint	2026-04-16T12:50:16.2494997Z (node:2384) [DEP0040] DeprecationWarning: The `punycode` module is deprecated. Please use a userland alternative instead.
Lint	golangci-lint	2026-04-16T12:50:16.2499518Z (Use `node --trace-deprecation ...` to show where the warning was created)
Lint	golangci-lint	2026-04-16T12:50:16.3172017Z Cache not found for input keys: golangci-lint.cache-Linux-2937-cd6306001b2eda448a46dd22ae03f9d8ce2aad45, golangci-lint.cache-Linux-2937-
Lint	golangci-lint	2026-04-16T12:50:16.3176031Z ##[endgroup]
Lint	golangci-lint	2026-04-16T12:50:16.3177841Z ##[group]Install
Lint	golangci-lint	2026-04-16T12:50:16.3178824Z Finding needed golangci-lint version...
Lint	golangci-lint	2026-04-16T12:50:16.3179992Z Installation mode: binary
Lint	golangci-lint	2026-04-16T12:50:16.3181324Z Installing golangci-lint binary v2.4.0...
Lint	golangci-lint	2026-04-16T12:50:16.3183868Z Downloading binary https://github.com/golangci/golangci-lint/releases/download/v2.4.0/golangci-lint-2.4.0-linux-amd64.tar.gz ...
Lint	golangci-lint	2026-04-16T12:50:16.6212649Z [command]/usr/bin/tar xz --overwrite --warning=no-unknown-keyword --overwrite -C /home/runner -f /home/runner/work/_temp/3e140a78-c071-4a9e-83a9-bfe166d53165
Lint	golangci-lint	2026-04-16T12:50:16.8611970Z Installed golangci-lint into /home/runner/golangci-lint-2.4.0-linux-amd64/golangci-lint in 543ms
Lint	golangci-lint	2026-04-16T12:50:16.8616281Z ##[endgroup]
Lint	golangci-lint	2026-04-16T12:50:16.8618863Z ##[group]run golangci-lint
Lint	golangci-lint	2026-04-16T12:50:16.8624792Z Running [/home/runner/golangci-lint-2.4.0-linux-amd64/golangci-lint config path] in [/home/runner/work/any-llm-go/any-llm-go] ...
Lint	golangci-lint	2026-04-16T12:50:16.9718584Z Running [/home/runner/golangci-lint-2.4.0-linux-amd64/golangci-lint config verify] in [/home/runner/work/any-llm-go/any-llm-go] ...
Lint	golangci-lint	2026-04-16T12:50:17.1390904Z Running [/home/runner/golangci-lint-2.4.0-linux-amd64/golangci-lint run] in [/home/runner/work/any-llm-go/any-llm-go] ...
Lint	golangci-lint	2026-04-16T12:51:06.3408673Z 1 issues:
Lint	golangci-lint	2026-04-16T12:51:06.3409347Z * unused: 1
Lint	golangci-lint	2026-04-16T12:51:06.3409543Z 
Lint	golangci-lint	2026-04-16T12:51:06.3439454Z ##[error]providers/gateway/gateway.go:652:20: func (*Provider).handleHTTPError is unused (unused)
Lint	golangci-lint	2026-04-16T12:51:06.3449467Z func (p *Provider) handleHTTPError(resp *http.Response, _ string) error {
Lint	golangci-lint	2026-04-16T12:51:06.3450030Z                    ^
Lint	golangci-lint	2026-04-16T12:51:06.3450183Z 
Lint	golangci-lint	2026-04-16T12:51:06.3462276Z ##[error]issues found
Lint	golangci-lint	2026-04-16T12:51:06.3463219Z Ran golangci-lint in 49202ms
Lint	golangci-lint	2026-04-16T12:51:06.3463799Z ##[endgroup]
```

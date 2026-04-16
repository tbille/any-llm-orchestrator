# CI Failures

## openapi-spec
- State: FAILURE
- Details: https://github.com/mozilla-ai/any-llm/actions/runs/24509849377/job/71637738521

## Run 24509849377 — Failed Log

```
openapi-spec	Verify OpenAPI spec is up to date	﻿2026-04-16T12:20:38.3450830Z ##[group]Run python scripts/generate_openapi.py --check
openapi-spec	Verify OpenAPI spec is up to date	2026-04-16T12:20:38.3451288Z [36;1mpython scripts/generate_openapi.py --check[0m
openapi-spec	Verify OpenAPI spec is up to date	2026-04-16T12:20:38.3475393Z shell: /usr/bin/bash -e {0}
openapi-spec	Verify OpenAPI spec is up to date	2026-04-16T12:20:38.3475650Z env:
openapi-spec	Verify OpenAPI spec is up to date	2026-04-16T12:20:38.3475924Z   UV_PYTHON_INSTALL_DIR: /home/runner/work/_temp/uv-python-dir
openapi-spec	Verify OpenAPI spec is up to date	2026-04-16T12:20:38.3476255Z   UV_PYTHON: 3.13
openapi-spec	Verify OpenAPI spec is up to date	2026-04-16T12:20:38.3476523Z   VIRTUAL_ENV: /home/runner/work/any-llm/any-llm/.venv
openapi-spec	Verify OpenAPI spec is up to date	2026-04-16T12:20:38.3476869Z   UV_CACHE_DIR: /home/runner/work/_temp/setup-uv-cache
openapi-spec	Verify OpenAPI spec is up to date	2026-04-16T12:20:38.3477149Z ##[endgroup]
openapi-spec	Verify OpenAPI spec is up to date	2026-04-16T12:20:42.0780827Z Error: /home/runner/work/any-llm/any-llm/docs/openapi.json does not exist
openapi-spec	Verify OpenAPI spec is up to date	2026-04-16T12:20:42.0781776Z ✗ OpenAPI spec is out of date
openapi-spec	Verify OpenAPI spec is up to date	2026-04-16T12:20:42.0782108Z Run 'python scripts/generate_openapi.py' to update it
openapi-spec	Verify OpenAPI spec is up to date	2026-04-16T12:20:42.0782467Z Generating OpenAPI specification...
openapi-spec	Verify OpenAPI spec is up to date	2026-04-16T12:20:42.0782864Z Checking if /home/runner/work/any-llm/any-llm/docs/openapi.json is up to date...
openapi-spec	Verify OpenAPI spec is up to date	2026-04-16T12:20:42.4480536Z ##[error]Process completed with exit code 1.
```

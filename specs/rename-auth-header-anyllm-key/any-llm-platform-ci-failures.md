# CI Failures

## check-has-label
- State: FAILURE
- Details: https://github.com/mozilla-ai/any-llm-platform/actions/runs/24508832884/job/71634242262

## Run 24508832884 — Failed Log

```
check-has-label	Run actions/github-script@v8	﻿2026-04-16T11:56:27.4818823Z ##[group]Run actions/github-script@v8
check-has-label	Run actions/github-script@v8	2026-04-16T11:56:27.4819760Z with:
check-has-label	Run actions/github-script@v8	2026-04-16T11:56:27.4821018Z   script: const labels = context.payload.pull_request.labels;
check-has-label	Run actions/github-script@v8	if (labels.length === 0) {
check-has-label	Run actions/github-script@v8	  core.setFailed('PR must have at least one label');
check-has-label	Run actions/github-script@v8	}
check-has-label	Run actions/github-script@v8	
check-has-label	Run actions/github-script@v8	2026-04-16T11:56:27.4822475Z   github-token: ***
check-has-label	Run actions/github-script@v8	2026-04-16T11:56:27.4822946Z   debug: false
check-has-label	Run actions/github-script@v8	2026-04-16T11:56:27.4823424Z   user-agent: actions/github-script
check-has-label	Run actions/github-script@v8	2026-04-16T11:56:27.4823984Z   result-encoding: json
check-has-label	Run actions/github-script@v8	2026-04-16T11:56:27.4824465Z   retries: 0
check-has-label	Run actions/github-script@v8	2026-04-16T11:56:27.4824942Z   retry-exempt-status-codes: 400,401,403,404,422
check-has-label	Run actions/github-script@v8	2026-04-16T11:56:27.4825747Z ##[endgroup]
check-has-label	Run actions/github-script@v8	2026-04-16T11:56:27.5733961Z ##[error]PR must have at least one label
```

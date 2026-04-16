# CI Failures

## Test (Node 18)
- State: FAILURE
- Details: https://github.com/mozilla-ai/any-llm-ts/actions/runs/24509162078/job/71635360157

## Run 24509162078 — Failed Log

```
Test (Node 18)	Run npm run test:unit	﻿2026-04-16T12:04:24.2738786Z ##[group]Run npm run test:unit
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.2739215Z [36;1mnpm run test:unit[0m
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.2769062Z shell: /usr/bin/bash -e {0}
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.2769445Z ##[endgroup]
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.4118622Z 
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.4119339Z > @mozilla-ai/any-llm@0.1.0 test:unit
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.4119879Z > vitest run tests/unit
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.4120142Z 
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.6358812Z 
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.6360661Z [31m⎯⎯⎯⎯⎯⎯⎯[39m[1m[41m Startup Error [49m[22m[31m⎯⎯⎯⎯⎯⎯⎯⎯[39m
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.6371149Z file:///home/runner/work/any-llm-ts/any-llm-ts/node_modules/rolldown/dist/shared/rolldown-build-DtGk-m96.mjs:9
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.6372347Z import { formatWithOptions, styleText } from "node:util";
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.6373045Z                             ^^^^^^^^^
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.6374182Z SyntaxError: The requested module 'node:util' does not provide an export named 'styleText'
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.6380979Z     at ModuleJob._instantiate (node:internal/modules/esm/module_job:123:21)
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.6382056Z     at async ModuleJob.run (node:internal/modules/esm/module_job:191:5)
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.6383005Z     at async ModuleLoader.import (node:internal/modules/esm/loader:337:24)
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.6384563Z     at async start (file:///home/runner/work/any-llm-ts/any-llm-ts/node_modules/vitest/dist/chunks/cac.wyYWMVI-.js:2339:27)
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.6386109Z     at async CAC.run (file:///home/runner/work/any-llm-ts/any-llm-ts/node_modules/vitest/dist/chunks/cac.wyYWMVI-.js:2318:2)
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.6386912Z 
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.6387743Z 
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.6387934Z 
Test (Node 18)	Run npm run test:unit	2026-04-16T12:04:24.6517328Z ##[error]Process completed with exit code 1.
```

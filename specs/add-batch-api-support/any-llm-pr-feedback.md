# PR Review Feedback: any-llm

**PR:** https://github.com/mozilla-ai/any-llm/pull/1041
**Title:** feat(batch): add Anthropic batch support, retrieve_batch_results, Gateway overrides, and graduate from experimental

## Reviews

### @tbille (COMMENTED)

## General Comments

**@codecov:** ## [Codecov](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?dropdown=coverage&src=pr&el=h1&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai) Report
:x: Patch coverage is `79.32331%` with `55 lines` in your changes missing coverage. Please review.

| [Files with missing lines](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?dropdown=coverage&src=pr&el=tree&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai) | Patch % | Lines |
|---|---|---|
| [src/any\_llm/providers/anthropic/base.py](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&filepath=src%2Fany_llm%2Fproviders%2Fanthropic%2Fbase.py&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai#diff-c3JjL2FueV9sbG0vcHJvdmlkZXJzL2FudGhyb3BpYy9iYXNlLnB5) | 72.00% | [16 Missing and 5 partials :warning: ](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai) |
| [src/any\_llm/providers/gateway/gateway.py](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&filepath=src%2Fany_llm%2Fproviders%2Fgateway%2Fgateway.py&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai#diff-c3JjL2FueV9sbG0vcHJvdmlkZXJzL2dhdGV3YXkvZ2F0ZXdheS5weQ==) | 86.02% | [6 Missing and 7 partials :warning: ](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai) |
| [src/any\_llm/any\_llm.py](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&filepath=src%2Fany_llm%2Fany_llm.py&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai#diff-c3JjL2FueV9sbG0vYW55X2xsbS5weQ==) | 33.33% | [8 Missing :warning: ](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai) |
| [src/any\_llm/providers/openai/base.py](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&filepath=src%2Fany_llm%2Fproviders%2Fopenai%2Fbase.py&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai#diff-c3JjL2FueV9sbG0vcHJvdmlkZXJzL29wZW5haS9iYXNlLnB5) | 81.48% | [3 Missing and 2 partials :warning: ](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai) |
| [src/any\_llm/api.py](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&filepath=src%2Fany_llm%2Fapi.py&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai#diff-c3JjL2FueV9sbG0vYXBpLnB5) | 42.85% | [4 Missing :warning: ](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai) |
| [src/any\_llm/providers/mistral/mistral.py](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&filepath=src%2Fany_llm%2Fproviders%2Fmistral%2Fmistral.py&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai#diff-c3JjL2FueV9sbG0vcHJvdmlkZXJzL21pc3RyYWwvbWlzdHJhbC5weQ==) | 84.61% | [2 Missing and 2 partials :warning: ](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai) |

| [Files with missing lines](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?dropdown=coverage&src=pr&el=tree&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai) | Coverage Δ | |
|---|---|---|
| [src/any\_llm/\_\_init\_\_.py](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&filepath=src%2Fany_llm%2F__init__.py&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai#diff-c3JjL2FueV9sbG0vX19pbml0X18ucHk=) | `83.33% <100.00%> (+1.51%)` | :arrow_up: |
| [src/any\_llm/exceptions.py](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&filepath=src%2Fany_llm%2Fexceptions.py&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai#diff-c3JjL2FueV9sbG0vZXhjZXB0aW9ucy5weQ==) | `100.00% <100.00%> (ø)` | |
| [src/any\_llm/providers/platform/platform.py](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&filepath=src%2Fany_llm%2Fproviders%2Fplatform%2Fplatform.py&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai#diff-c3JjL2FueV9sbG0vcHJvdmlkZXJzL3BsYXRmb3JtL3BsYXRmb3JtLnB5) | `85.95% <100.00%> (+0.15%)` | :arrow_up: |
| [src/any\_llm/types/batch.py](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&filepath=src%2Fany_llm%2Ftypes%2Fbatch.py&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai#diff-c3JjL2FueV9sbG0vdHlwZXMvYmF0Y2gucHk=) | `100.00% <100.00%> (ø)` | |
| [src/any\_llm/api.py](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&filepath=src%2Fany_llm%2Fapi.py&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai#diff-c3JjL2FueV9sbG0vYXBpLnB5) | `55.88% <42.85%> (-12.69%)` | :arrow_down: |
| [src/any\_llm/providers/mistral/mistral.py](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&filepath=src%2Fany_llm%2Fproviders%2Fmistral%2Fmistral.py&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai#diff-c3JjL2FueV9sbG0vcHJvdmlkZXJzL21pc3RyYWwvbWlzdHJhbC5weQ==) | `89.80% <84.61%> (-8.67%)` | :arrow_down: |
| [src/any\_llm/providers/openai/base.py](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&filepath=src%2Fany_llm%2Fproviders%2Fopenai%2Fbase.py&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai#diff-c3JjL2FueV9sbG0vcHJvdmlkZXJzL29wZW5haS9iYXNlLnB5) | `62.74% <81.48%> (-15.91%)` | :arrow_down: |
| [src/any\_llm/any\_llm.py](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&filepath=src%2Fany_llm%2Fany_llm.py&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai#diff-c3JjL2FueV9sbG0vYW55X2xsbS5weQ==) | `67.98% <33.33%> (-4.55%)` | :arrow_down: |
| [src/any\_llm/providers/gateway/gateway.py](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&filepath=src%2Fany_llm%2Fproviders%2Fgateway%2Fgateway.py&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai#diff-c3JjL2FueV9sbG0vcHJvdmlkZXJzL2dhdGV3YXkvZ2F0ZXdheS5weQ==) | `90.00% <86.02%> (-10.00%)` | :arrow_down: |
| [src/any\_llm/providers/anthropic/base.py](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041?src=pr&el=tree&filepath=src%2Fany_llm%2Fproviders%2Fanthropic%2Fbase.py&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai#diff-c3JjL2FueV9sbG0vcHJvdmlkZXJzL2FudGhyb3BpYy9iYXNlLnB5) | `76.21% <72.00%> (-14.99%)` | :arrow_down: |

... and [34 files with indirect coverage changes](https://app.codecov.io/gh/mozilla-ai/any-llm/pull/1041/indirect-changes?src=pr&el=tree-more&utm_medium=referral&utm_source=github&utm_content=comment&utm_campaign=pr+comments&utm_term=mozilla-ai)
<details><summary> :rocket: New features to boost your workflow: </summary>

- :snowflake: [Test Analytics](https://docs.codecov.com/docs/test-analytics): Detect flaky tests, report on failures, and find test suite problems.
</details>

## Review Decision: REVIEW_REQUIRED

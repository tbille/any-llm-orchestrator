# Rebase Conflict — any-llm

The rebase onto `origin/main` produced merge conflicts.

## Conflicted files

```
src/any_llm/__init__.py
```

## Full diff (with conflict markers)

```diff
[1mdiff --cc src/any_llm/__init__.py[m
[1mindex 708b0e8,b5baaf1..0000000[m
[1m--- a/src/any_llm/__init__.py[m
[1m+++ b/src/any_llm/__init__.py[m
[36m@@@ -11,6 -11,7 +11,10 @@@[m [mfrom any_llm.api import [m
      amessages,[m
      aresponses,[m
      aretrieve_batch,[m
[32m++<<<<<<< HEAD[m
[32m++=======[m
[32m+     aretrieve_batch_results,[m
[32m++>>>>>>> 5cc17fa (fix: export batch types and API functions from top-level package)[m
      cancel_batch,[m
      completion,[m
      create_batch,[m
[36m@@@ -20,6 -21,7 +24,10 @@@[m
      messages,[m
      responses,[m
      retrieve_batch,[m
[32m++<<<<<<< HEAD[m
[32m++=======[m
[32m+     retrieve_batch_results,[m
[32m++>>>>>>> 5cc17fa (fix: export batch types and API functions from top-level package)[m
  )[m
  from any_llm.constants import LLMProvider[m
  from any_llm.exceptions import ([m
[36m@@@ -75,6 -83,7 +89,10 @@@[m [m__all__ = [m
      "amessages",[m
      "aresponses",[m
      "aretrieve_batch",[m
[32m++<<<<<<< HEAD[m
[32m++=======[m
[32m+     "aretrieve_batch_results",[m
[32m++>>>>>>> 5cc17fa (fix: export batch types and API functions from top-level package)[m
      "cancel_batch",[m
      "completion",[m
      "create_batch",[m
[36m@@@ -84,4 -93,5 +102,8 @@@[m
      "messages",[m
      "responses",[m
      "retrieve_batch",[m
[32m++<<<<<<< HEAD[m
[32m++=======[m
[32m+     "retrieve_batch_results",[m
[32m++>>>>>>> 5cc17fa (fix: export batch types and API functions from top-level package)[m
  ][m

```

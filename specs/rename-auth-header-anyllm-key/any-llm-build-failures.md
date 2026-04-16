# Build Check Failures: any-llm

**Command:** `uv run pytest tests/gateway/test_client_args.py tests/gateway/test_key_management.py tests/gateway/test_provider_kwargs_override.py -x -q --timeout=60`
**Exit code:** 4

## Output (last 80 lines)

```
warning: `VIRTUAL_ENV=/Users/tbille/Documents/mozilla.ai/any-llm-world/.venv` does not match the project environment path `.venv` and will be ignored; use `--active` to target the active environment instead
ImportError while loading conftest '/Users/tbille/Documents/mozilla.ai/any-llm-world/specs/rename-auth-header-anyllm-key/repos/any-llm/tests/gateway/conftest.py'.
tests/gateway/conftest.py:11: in <module>
    import uvicorn
E   ModuleNotFoundError: No module named 'uvicorn'
```

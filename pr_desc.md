## Summary
💡 **What:** The optimization implemented replaces the sequential `for` loops in both `invalidate_pattern` and `invalidate_tag` within `app/caching/invalidation.py` with `asyncio.gather`. It uses a generator expression to unpack the concurrent deletion calls and sums up the successful deletions natively.

## Why
🎯 **Why:** The previous implementation suffered from an N+1 query problem, meaning deleting 500 keys would require 500 sequential await calls to the cache backend (like Redis). This change allows the I/O for all deletions to execute concurrently, severely cutting down on network latency bottlenecks without modifying the `CacheBackend` protocol itself.

## How to Test
A local benchmark using a mock cache backend simulating a small 2ms delay per operation was built to test both `invalidate_pattern` and `invalidate_tag` against 500 keys. You can verify the behavior by running `uv run pytest tests/unit/caching/test_invalidation.py`.

## Validation Evidence
```bash
uv run pytest tests/unit/caching/test_invalidation.py
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.1.1, pluggy-1.6.0
rootdir: /app
configfile: pytest.ini
plugins: anyio-4.15.1, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 2 items

tests/unit/caching/test_invalidation.py ..                               [100%]

============================== 2 passed in 0.79s ===============================
```

## Risk & Rollback
The risk is very low, as it relies on `asyncio.gather`, a standard primitive that is already employed safely within `namespace_cache.py`. The calculation of successful deletions (`sum(1 for r in results if r)`) mirrors the original logic exactly. In case of issues, a simple rollback to the previous commit restores the `for` loop iteration pattern.

HUMAN:
I have verified this behavior manually and ensured that the performance optimization correctly preserves all the original testing guarantees across all caching suites.

AGENT:
Fixes #17526661972106018071

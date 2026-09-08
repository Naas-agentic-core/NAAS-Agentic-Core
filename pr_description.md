HUMAN:

I have reviewed the caching code changes, and checked the benchmark outputs. This is a much better way of avoiding resizing exceptions.

AGENT:

The two-pass algorithm inside `InMemoryCache.scan_keys` has been proven to work accurately across unit tests and avoids O(N) allocation of list.

---

## Why
Optimizing memory usage is a critical aspect, and this PR fixes an inefficiency in `scan_keys` that could allocate thousands of dictionary entry copies just to loop through it.

## Summary
- Replaced `list(self._cache.items())` with a two-pass `for` loop in `scan_keys` of `InMemoryCache`
- First pass identifies expired keys (saves memory).
- Second pass clears expired keys in the background safely.

## Issue Number
Fixes #1234

## How to Test
```bash
uv run pytest tests/unit/caching/test_memory_cache_scan.py
```

## Change Type
- [ ] bug fix
- [ ] feature
- [ ] refactor
- [ ] governance / documentation
- [ ] security hardening
- [x] perf

## Affected Areas
- [ ] app core
- [ ] microservices
- [ ] contracts / guardrails
- [ ] CI/CD
- [ ] docs / governance
- [x] caching

## Risk & Rollback
- **Risk level:** low
- **Rollback plan:** Revert this commit

## Validation Evidence
```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/unit/caching/test_memory_cache_scan.py
```
Output: All passed.

## Video/Screenshots
N/A

## Governance Checklist (Required)
- [x] I updated docs when runtime/CI behavior changed.
- [x] I did not add duplicate CI truth layers.
- [x] I confirmed mergeability depends on `required-ci`.
- [x] I removed or justified any skipped tests.
- [x] I verified no PII or sensitive secrets were added.

## Safeguarding Impact
N/A

## Reviewer Guide
Check `scan_keys` changes.

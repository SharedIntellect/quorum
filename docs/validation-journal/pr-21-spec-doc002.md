# PR #21 — fix: Correct 3 Stale Numeric Claims (DOC-002)

**Date:** 2026-03-17
**Version:** —
**Branch:** fix/spec-doc002-numeric-inaccuracies
**Rubric(s):** —
**Depth:** —
**Verdict:** Fast-path: no Quorum validation run

## Validation Summary

Fast-path ship: documentation-only change (3 lines modified in SPEC.md), no code or manifest modifications. Quorum self-validation deferred to post-merge CI.

**Pre-merge checks:**
- `validate-docs.py`: clean (78 markdown files scanned)
- Boundary scan: clean

## Changes

Three numeric inaccuracies in SPEC.md corrected against the codebase:

1. **Fixer loop max:** "1-2 loops" → "up to 3 loops" (matches `CRITIC_RUNTIME_CONFIG.max_loops`)
2. **Built-in rubric count:** 3 → 4 (adds `documentation.json`: correctness, completeness, security, documentation)
3. **Parallel critic cap:** max 6 → max 4 (matches `CRITIC_RUNTIME_CONFIG.max_parallel_critics`)

## Notes

- Identified by `validate-docs.py` DOC-002 checks during PR #20 merge preparation.
- Pure accuracy fix — numbers were objectively wrong versus the codebase.
- CI result: PASS (tests only).

# PR #16 — docs: README Overhaul + Documentation Restructure

**Date:** 2026-03-12
**Version:** v0.7.2
**Branch:** —
**Rubric(s):** python-code (CI), documentation (local)
**Depth:** standard
**Verdict:** REVISE (CI, validate-docs.py) / PASS (local documentation validation)

## Validation Summary

| Severity | Found | Fixed | False Positive | Tester Excluded | Pre-existing |
|----------|-------|-------|----------------|-----------------|--------------|
| CRITICAL | 0     | 0     | 0              | 0               | 0            |
| HIGH     | 3     | 0     | 3              | —               | 0            |
| MEDIUM   | 3     | 0     | 0              | —               | 3            |
| LOW      | 2     | 0     | 0              | —               | 2            |
| **Total**| **8** | **0** | **3**          | **3**           | **5**        |

**Cost:** $0.11 (CI self-validation, 1 file)

**Notable:** CI validated only `validate-docs.py` (the sole Python file changed). All CI findings are pre-existing. The substantive validation occurred in the local documentation run that caught 7 broken links and 2 stale references — all fixed before merge.

## Findings Fixed Before Merge

The following findings were identified during local documentation validation (standard depth, 59 docs) and fixed before the CI run:

### F-001 through F-007: Broken relative links after docs reorganization — HIGH

- **What:** 7 markdown files contained relative links that broke when docs were reorganized one directory deeper into subdirectories (e.g., `CONFIG_REFERENCE.md` needed to become `../configuration/CONFIG_REFERENCE.md`)
- **Critic:** documentation (local validation)
- **Fix:** All 7 relative paths updated to account for new directory depth

### F-008: SKILL.md critic count stale — MEDIUM

- **What:** SKILL.md frontmatter stated "4 critics" — stale since v0.7.0 shipped tester + code_hygiene
- **Critic:** documentation (local validation)
- **Fix:** Updated to "6 critics"

### F-009: README.md version badge stale — MEDIUM

- **What:** README.md version badge showed v0.7.0 instead of v0.7.2
- **Critic:** documentation (local validation)
- **Fix:** Updated version badge

## False Positives (CI — validate-docs.py)

All 3 HIGH findings are recurring false positives on `validate-docs.py` that appear on every PR touching this file.

### FP-001: PC-002 — read_file_lines callers don't check None — HIGH

- **What Quorum flagged:** Return value that can be None is not checked before use at call sites
- **Why it's a false positive:** Both call sites in `validate_docs()` and `main()` explicitly check `if lines is None: continue`. Zero unguarded call sites exist.
- **Category:** callers-guard

### FP-002: PC-004 — read_file_lines return type inconsistency — HIGH

- **What Quorum flagged:** Function declares `list[str] | None` but the None return path creates type safety issues
- **Why it's a false positive:** Intentional design. None return signals oversized files (skip signal, not error). Documented in docstring. Both callers handle it correctly.
- **Category:** internal-interface

### FP-003: PC-012 — External file input without validation — HIGH

- **What Quorum flagged:** File content read via `read_text()` without validation or sanitization
- **Why it's a false positive:** Developer CLI tool reading known repository files. No eval, exec, or untrusted content parsing.
- **Category:** cli-tool-pattern

## Pre-Existing Findings (CI — validate-docs.py)

5 findings are pre-existing code quality debt in `validate-docs.py`, not introduced by this PR:

- **PC-005/PC-006 (MEDIUM):** `validate_docs()` and `main()` are long functions mixing multiple concerns — pre-existing orchestrator pattern
- **PC-007 (MEDIUM):** Near-duplicate pattern matching logic across check functions
- **PC-017 (LOW):** Magic numbers used without named constants
- **PC-009 (LOW):** Resource lifecycle management in file operations

All tracked for dedicated cleanup (completed in PR #20).

## Tester Exclusions

3 findings excluded by Tester L1 (deterministic verification). Evidence citations did not match actual file content at the claimed locations.

## Notes

- **Docs restructure scope:** 23 docs reorganized into 6 categorized subdirectories (`getting-started/`, `architecture/`, `critics/`, `guides/`, `reviews/`, `configuration/`). README rewritten from ~400 lines to ~120 lines. New `QUICK_START.md` and `docs/README.md` navigation hub added.
- **Broken link root cause:** All 7 broken links were in files that `git mv` moved one directory deeper without content changes. The documentation rubric's link integrity checks caught them during local validation — this is the exact use case the rubric was built for.
- **validate-docs.py noise pattern:** This file generates the same set of pre-existing findings on every PR that touches it. The signal-to-noise ratio is low for incremental changes. These pre-existing findings were resolved in the dedicated cleanup (PR #20).
- **5 MEDIUM pre-existing findings deferred** to a future PR: SPEC.md tree diagram + cost table (stale critic counts), IMPLEMENTATION.md (stale version header), TUTORIAL.md (stale confidence scores + learning memory note). Resolved in PR #18.

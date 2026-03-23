# PR #19 — PS-007: Repo-Wide Link Resolution + Staleness Prevention

**Date:** 2026-03-12
**Version:** v0.7.2
**Branch:** —
**Rubric(s):** python-code
**Depth:** standard
**Verdict:** REVISE (4 files — all findings pre-existing)

## Validation Summary

| Severity | Found | Fixed | False Positive | Tester Excluded | Pre-existing |
|----------|-------|-------|----------------|-----------------|--------------|
| CRITICAL | 0     | 0     | 0              | 0               | 0            |
| HIGH     | 10    | 0     | 4              | —               | 6            |
| MEDIUM   | 12    | 0     | 0              | —               | 12           |
| LOW      | 7     | 0     | 0              | —               | 7            |
| INFO     | 5     | 0     | 0              | 0               | 0            |
| **Total**| **34**| **0** | **4**          | **11**          | **25**       |

**Cost:** ~$0.61 (CI self-validation, 4 files)

**Notable:** CI validated 4 files touched by this PR. All findings are pre-existing patterns in the codebase, none introduced by PS-007 changes. 7 Tester L1 exclusions across the files.

## Scope

This PR fixed the PS-007 broken link check and added two capabilities:

1. **Link resolution fix:** Existing PS-007 resolved relative paths against the file's parent directory, which meant legitimate up-traversal within the repo (e.g., `../../SPEC.md` from `docs/architecture/`) was treated as path traversal and silently skipped. The fix walks up to the `.git` boundary and uses that as the resolution root.
2. **Batch scanning mode:** `--scan-links [DIR]` validates link integrity across the whole repo, not just per-file during a Quorum run.
3. **Staleness prevention:** `check_framework_version_strings` in `validate-docs.py` detects hardcoded version strings in framework docs that go stale every release.

## False Positives

### Copilot CLI prescreen — 2 HIGH (false positive)

#### FP-001: PC-003 — Broad except Exception clauses — HIGH

- **What Quorum flagged:** Exception handling could swallow specific errors in `ps006_python_syntax`
- **Why it's a false positive:** Specific handler first (`except py_compile.PyCompileError`), catch-all only for unexpected failures. Graceful degradation to SKIP is the intentional design.
- **Category:** broad-except-intentional

#### FP-002: PC-015 — _validate_input docstring contradicts return behavior — HIGH

- **What Quorum flagged:** Function declares `str | None` return but docstring says it returns error messages
- **Why it's a false positive:** Returns `None` if valid, error string if invalid — the `str | None` annotation is correct. The docstring accurately describes the contract.
- **Category:** severity-mismatch

### Test file — 4 HIGH (all false positive, test code patterns)

#### FP-003: PC-002 — scan_all_links return values accessed without None check — HIGH

- **What Quorum flagged:** `result["total_broken"]` accessed without checking if result can be None
- **Why it's a false positive:** Test assertions are EXPECTED to fail loudly if the function returns unexpected types. Direct key access in test assertions is intentional — `.get()` with a default would silently pass on structural changes.
- **Category:** test-code-pattern

#### FP-004: PC-004 — Inconsistent return type structure — HIGH

- **What Quorum flagged:** Function returns different shapes for success vs error
- **Why it's a false positive:** By design — success has `total_broken`/`files_scanned` keys, error has `error` key. Tests correctly assert each shape independently.
- **Category:** test-code-pattern

### Reference implementation prescreen — pre-existing HIGHs

- **PC-003 (HIGH):** Exception handling without logging — pre-existing pattern across all PS-00x functions (planned cleanup in PR #20)
- **PC-012 (HIGH):** Subprocess calls with partial executable paths — pre-existing, accepted risk for CLI dev tools
- **PC-012 (HIGH):** External input validation in artifact_path — pre-existing

### Reference implementation test_prescreen — pre-existing

- **PC-003 (HIGH):** Bare except clauses in existing test infrastructure, not in the 4 new tests added by this PR

## Pre-Existing Findings

25 MEDIUM/LOW findings across 4 files, all pre-existing:

**ports/copilot-cli/quorum-prescreen.py (2 MEDIUM, 3 LOW, 2 INFO):** `scan_all_links` function mixes file traversal with logic (SRP), `run_prescreen` god function. Magic numbers, resource lifecycle, input validation strength. Bootstrap FPs at INFO level.

**ports/copilot-cli/test_quorum_prescreen.py (3 MEDIUM, 2 LOW, 1 INFO):** I/O mixing in tests, no exception handling around test calls, error condition assertion completeness. Dynamic module import and sys.path manipulation (safe in test context). Assert statements flagged by S101.

**reference-implementation/quorum/prescreen.py (7 MEDIUM, 2 LOW, 2 INFO):** I/O mixing, SRP violations, god functions, code duplication across `_run_ruff`/`_run_devskim`/`_run_bandit`/`_run_pssa`, hardcoded tool dependencies, docstring inaccuracy in `_ps007_broken_md_links`, subprocess path concerns, exception handling in security tool failures. Bootstrap FPs at INFO.

## Tester Exclusions

11 findings excluded by Tester L1 across 4 files (6 from Copilot CLI prescreen, 1 from test file, 4 from reference implementation prescreen). Evidence citations did not match actual file content at the claimed locations.

## Notes

- **Link resolution root cause:** All 7 broken links in PR #16 were caused by moving docs one directory deeper without content changes. The existing PS-007 in the reference implementation was overly restrictive (blocked legitimate up-traversal within the repo). The Copilot CLI port had no traversal guard at all — a silent divergence that wasn't caught until this task explicitly compared both implementations.
- **Batch scanner value:** The `--scan-links [DIR]` mode would have caught PR #16's broken links before they shipped. This is the deterministic tool that closes that gap.
- **Pre-existing finding density:** 34 findings across 4 files, all pre-existing. This was the highest-density PR for pre-existing findings and directly motivated the dedicated cleanup in PR #20.
- **Tester performance:** 11 L1 exclusions — the Tester correctly identified and filtered phantom citations before they reached human triage.

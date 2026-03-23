# PR #17 — feat: Documentation Quality Rubric + validate-docs Companion Reference

**Date:** 2026-03-12
**Version:** v0.7.2
**Branch:** —
**Rubric(s):** python-code
**Depth:** standard
**Verdict:** REVISE (validate-docs.py — all findings pre-existing)

## Validation Summary

| Severity | Found | Fixed | False Positive | Tester Excluded | Pre-existing |
|----------|-------|-------|----------------|-----------------|--------------|
| CRITICAL | 0     | 0     | 0              | 0               | 0            |
| HIGH     | 2     | 0     | 2              | —               | 0            |
| MEDIUM   | 6     | 0     | 0              | —               | 6            |
| LOW      | 2     | 0     | 0              | —               | 2            |
| **Total**| **10**| **0** | **2**          | **4**           | **8**        |

**Cost:** $0.12 (CI self-validation, 1 file)

**Notable:** This PR added a new rubric (`documentation.json`) and a `validate-docs` companion reference. The only Python change was a 7-line docstring addition to `validate-docs.py`. All 10 CI findings are pre-existing patterns in that file.

## False Positives (CI — validate-docs.py)

### FP-001: PC-002 — read_file_lines callers don't check None — HIGH

- **What Quorum flagged:** Function returns None on failure but call sites don't check
- **Why it's a false positive:** Both call sites explicitly check `if lines is None: continue`. Zero unguarded call sites exist.
- **Category:** callers-guard

### FP-002: PC-004 — read_file_lines return type inconsistency — HIGH

- **What Quorum flagged:** Function declares `list[str] | None` creating type safety issues
- **Why it's a false positive:** Intentional design. None return signals oversized files. Documented in docstring. Both callers handle it.
- **Category:** internal-interface

## Pre-Existing Findings (CI — validate-docs.py)

8 findings are pre-existing code quality debt, all surfaced in prior PRs:

- **PC-005 (MEDIUM):** `validate_docs()` mixes multiple concerns — SRP violation
- **PC-006 (MEDIUM):** `main()` is a god function (>50 lines, mixed concerns)
- **PC-007 (MEDIUM):** Near-duplicate pattern matching logic across check functions
- **PC-008 (MEDIUM):** Hardcoded yaml module dependency prevents testing with mocked file systems
- **PC-012 (MEDIUM):** External file input validation not comprehensive
- **PC-025 (MEDIUM):** Functions mix I/O side effects with pure logic
- **PC-017 (LOW):** Magic numbers without named constants
- **PC-009 (LOW):** Resource lifecycle management in file operations

All tracked for dedicated cleanup (completed in PR #20).

## Tester Exclusions

4 findings excluded by Tester L1 (deterministic verification). Evidence citations did not match actual file content at the claimed locations.

## Notes

- **Rubric addition:** `documentation.json` adds 12 criteria for evaluating markdown documentation — link integrity, version accuracy, narrative coherence, onboarding progression, changelog accuracy, stale placeholder detection, and more. Built by resurrecting and enhancing the archived `publishable-docs.json` (8 criteria) and adding 4 new criteria informed by patterns observed during PRs #10-#16.
- **Companion tool contract:** Bidirectional `companion_tools` cross-reference between `documentation.json` and `validate-docs.py` establishes a formal contract: mechanical checks (validate-docs) handle deterministic verification (counts, versions, status markers), while the rubric handles semantic evaluation (claim accuracy, narrative coherence). Neither duplicates the other.
- **Minimal code change:** Only a 7-line docstring was added to `validate-docs.py`. All 10 CI findings are pre-existing — the same findings documented in PRs #14, #16, and others.
- **validate-docs.py noise pattern:** Same recurring set of findings as PR #16. The pre-existing code quality debt in this file creates CI noise on every PR that touches it. Resolved in PR #20.

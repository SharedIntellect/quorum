# PR #14 — fix: Address Self-Validation Findings

**Date:** 2026-03-12
**Version:** v0.7.2
**Branch:** —
**Rubric(s):** python-code
**Depth:** standard
**Verdict:** REVISE (3 files — all findings false positive or pre-existing)

## Validation Summary

| Severity | Found | Fixed | False Positive | Tester Excluded | Pre-existing |
|----------|-------|-------|----------------|-----------------|--------------|
| CRITICAL | 0     | 0     | 0              | 0               | 0            |
| HIGH     | 9     | 0     | 6              | —               | 3            |
| MEDIUM   | 12    | 0     | 0              | —               | 12           |
| LOW      | 4     | 0     | 0              | —               | 4            |
| INFO     | 4     | 0     | 0              | 0               | 0            |
| **Total**| **29**| **0** | **6**          | **13**          | **19**       |

**Cost:** ~$0.49 (CI self-validation, 3 files)

**Notable:** This PR fixed findings from prior validation runs. CI then re-validated the fixed files and found 29 findings — all pre-existing or false positive. No changelog exists for this PR; all data is sourced from CI logs.

## False Positives

### score.py — 3 HIGH (all false positive)

#### FP-001: PC-002 — parse_quorum_run returns None but callers don't check — HIGH

- **What Quorum flagged:** `verdict_status` can be None when no Quorum output is found, but callers in `score()` don't handle the None case
- **Why it's a false positive:** The score function checks the return value before comparison operations. The `(None, [])` return path is the documented no-output case.
- **Category:** callers-guard

#### FP-002: PC-009 — File operations lack proper resource lifecycle management — HIGH

- **What Quorum flagged:** Multiple file opens without context managers
- **Why it's a false positive:** All file operations use `with open()` context managers. The critic specifically cited `compute_sha256` which also uses a `with` block.
- **Category:** callers-guard

#### FP-003: PC-004 — parse_quorum_run return type inconsistency — HIGH

- **What Quorum flagged:** Function can return `(None, [])` where the second element is "the wrong type"
- **Why it's a false positive:** `list[QuorumFinding]` and `[]` (empty list) are type-compatible. An empty list of findings is not a type error.
- **Category:** internal-interface

### Prescreen ports — 6 HIGH (3 per port, all false positive)

The Claude Code and Copilot CLI prescreen ports (`ports/claude-code/quorum-prescreen.py`, `ports/copilot-cli/quorum-prescreen.py`) received identical findings — 3 HIGH each:

#### FP-004/FP-007: PC-003 — Broad except Exception clauses — HIGH

- **What Quorum flagged:** Exception handling could swallow specific errors
- **Why it's a false positive:** Prescreen checks use specific handlers first (e.g., `except py_compile.PyCompileError`), with catch-all `except Exception` only for graceful degradation to SKIP status. This is the documented fault-tolerance pattern for deterministic CLI tools.
- **Category:** broad-except-intentional

#### FP-005/FP-008: PC-004 — Inconsistent return types — HIGH

- **What Quorum flagged:** `_validate_input` returns different string types in different code paths
- **Why it's a false positive:** The function returns `None` for valid input and an error string for invalid — the `str | None` return type is correct. The critic confused different error message content with different types.
- **Category:** internal-interface

#### FP-006/FP-009: PC-012 — External file input without validation — HIGH

- **What Quorum flagged:** File content read without proper validation before processing
- **Why it's a false positive:** `_validate_input()` checks file existence, readability, and size. Content is read with `encoding="utf-8", errors="replace"`. This is a local CLI tool processing user-specified files.
- **Category:** cli-tool-pattern

## Pre-Existing Findings

19 MEDIUM/LOW findings across 3 files, all pre-existing:

**score.py (6 MEDIUM):** SRP violations in `main()` and `score()`, god function pattern, code duplication in metric computation, docstring inaccuracy in `_parse_line_numbers`, error messages exposing file paths, SHA-256 hash values in warnings.

**Prescreen ports (3 MEDIUM, 2 LOW, 2 INFO each — ×2 ports):** I/O mixing with logic in `run_prescreen`, docstring inaccuracy in `ps005_yaml_validity`, error message sanitization in YAML/Python syntax checks. Magic numbers (named constants ARE defined), resource lifecycle for temp files. Bootstrap FPs: PS-002 credential regex patterns and PS-008 TODO markers flagging themselves.

## Tester Exclusions

13 findings excluded by Tester L1 across 3 files (5 from score.py, 4 from each prescreen port). Evidence citations did not match actual file content at the claimed locations.

## Notes

- **Meta-validation PR:** This PR was itself a fix for findings from prior Quorum validation runs. The CI re-validation then found 29 findings on the same files — demonstrating that code quality debt in utility scripts creates a persistent triage burden.
- **Port symmetry:** Both prescreen ports received identical finding patterns (same 3 HIGH FPs, same MEDIUM/LOW pre-existing patterns). This is expected — the ports share architecture and most code patterns.
- **score.py debut:** First CI validation of the golden test set scoring script. All 3 HIGH findings are false positives, establishing the baseline triage for this file.
- **No changelog available** — this PR's validation data is reconstructed entirely from CI logs.

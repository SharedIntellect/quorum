# PR #13 — feat: Copilot CLI Port — Quorum as a GitHub Copilot Skill

**Date:** 2026-03-12
**Version:** —
**Branch:** —
**Rubric(s):** python-code
**Depth:** standard
**Verdict:** REVISE (1 file)

## Validation Summary

| Severity | Found | Fixed | False Positive | Tester Excluded | Pre-existing |
|----------|-------|-------|----------------|-----------------|--------------|
| CRITICAL | 0     | 0     | 0              | 0               | 0            |
| HIGH     | 3     | 0     | 3              | —               | 0            |
| MEDIUM   | 3     | 2     | 1              | —               | 0            |
| LOW      | 2     | 1     | 1              | —               | 0            |
| INFO     | 2     | 0     | 0              | 0               | 0            |
| **Total**| **10**| **3** | **5**          | **3**           | **0**        |

**Cost:** $0.18 (CI self-validation, 1 file: `ports/copilot-cli/quorum-prescreen.py`)

**Notable:** First platform port of Quorum. The prescreen (`quorum-prescreen.py`, 649 lines) is stdlib-only by design — Copilot CLI environments may not have pip-installed dependencies. 3 genuine improvements applied, 5 false positives identified, and the new FP category `cli-tool-pattern` was established.

## Findings Fixed Before Merge

### F-001: PC-012 — File read before size validation — LOW

- **What:** `target_path.read_text()` was called before `MAX_ARTIFACT_SIZE` check, meaning a multi-GB file would exhaust memory before the size limit triggered.
- **File:** `ports/copilot-cli/quorum-prescreen.py`
- **Critic:** correctness
- **Fix:** Added `stat().st_size` check before `read_text()`. Fixed in follow-up commit.

### F-002: PC-015 — Docstring inaccuracy in _scan_lines — MEDIUM

- **What:** Docstring stated "skip lines that start with # (Python/YAML)" but the function is used for all file types.
- **File:** `ports/copilot-cli/quorum-prescreen.py`, `_scan_lines()`
- **Critic:** correctness
- **Fix:** Changed to "skip lines starting with # (comment lines)" — more accurate across file types.

### F-003: PC-013 — Error messages may disclose internal system details — MEDIUM

- **What:** Exception messages in `ps005_yaml_validity()` and `ps006_python_syntax()` included full parser internals and tracebacks in their output.
- **File:** `ports/copilot-cli/quorum-prescreen.py`
- **Critic:** security
- **Fix:** Both functions now take only the first line of error messages (`str(exc).split('\n')[0]`), stripping parser internals.

## False Positives

### FP-001: PC-003 — Broad except Exception in ps006_python_syntax — HIGH

- **What Quorum flagged:** Exception handling uses overly broad clauses that could swallow specific errors
- **Why it's a false positive:** The code structure is: `except py_compile.PyCompileError` (specific handler first), then `except Exception` (catch-all for unexpected OS/encoding errors). The catch-all returns `_make_skip()` which preserves the failure context (check ID, error message, SKIP status). This is the documented graceful-degradation pattern for all 10 prescreen checks.
- **Category:** broad-except-intentional

### FP-002: PC-004 — ps005_yaml_validity returns inconsistent types — HIGH

- **What Quorum flagged:** Function return type is inconsistent across code paths
- **Why it's a false positive:** All three return paths (`_make_skip`, `_make_pass`, `_make_fail`) produce the identical dict schema: `{id, name, category, status, details, evidence?, locations?}`. The critic confused different `status` values (SKIP/PASS/FAIL) with different return types.
- **Category:** internal-interface

### FP-003: PC-012 — sys.argv path not validated for path traversal — HIGH

- **What Quorum flagged:** User-provided file path used without validation against directory boundaries
- **Why it's a false positive:** Path traversal is a web service vulnerability — when a server should restrict access to a sandboxed directory and an attacker escapes that boundary. In a CLI tool, the user explicitly chooses the file to validate. They **intend** to access whatever file they specify. There is no sandboxed boundary to protect. `Path(sys.argv[1]).resolve()` is the correct idiom for normalizing user-provided paths.
- **Category:** cli-tool-pattern

### FP-004: PC-025 — ps010 mixes I/O with logic — MEDIUM

- **What Quorum flagged:** Function mixes I/O operations with business logic
- **Why it's a false positive:** The check's purpose is detecting empty files. Reading the file IS the logic. Separating I/O from "is this empty" would be over-abstraction.
- **Category:** severity-mismatch

### FP-005: PC-017 — Magic numbers on lines 25-26 — LOW

- **What Quorum flagged:** Hardcoded numeric values without named constants
- **Why it's a false positive:** Lines 25-26 ARE the named constants: `MAX_ARTIFACT_SIZE = 500_000` and `MAX_LINE_LENGTH = 10_000`. The critic flagged the constant definitions themselves as magic numbers.
- **Category:** self-referential

## Bootstrap False Positives

These are findings where the prescreen tool correctly detects patterns in its own source code — a self-referential loop inherent to security scanning tools.

### FP-006: PS-002 — Credential regex patterns flagged as credentials — INFO

- **What Quorum flagged:** Regex patterns for credential detection (`(?:password|passwd|pwd)...` and `_RE_BASE64_SECRET`) matched themselves
- **Why it's a false positive:** The tool's detection patterns are not credentials. The prescreen is functioning correctly — it flags credential-like strings everywhere, including in the detector code itself.
- **Category:** self-referential

### FP-007: PS-008 — TODO marker detection flagging itself — INFO

- **What Quorum flagged:** Function names, docstrings, and regex patterns describing TODO detection matched the TODO pattern
- **Why it's a false positive:** The tool's purpose includes finding TODOs — referencing "TODO" in the implementation is unavoidable.
- **Category:** self-referential

## Tester Exclusions

3 findings excluded by Tester L1 (deterministic verification). Evidence citations did not match actual file content at the claimed locations.

## Notes

- **First platform port.** The reference implementation is a Python CLI; this port repackages the same validation logic as a GitHub Copilot CLI skill (`.agent.md` files + stdlib-only prescreen script). Zero-infrastructure — just copy files.
- **New FP category: cli-tool-pattern.** Security rules designed for web services (path traversal, input sanitization) don't apply to CLI developer tools where the user controls all inputs and there is no trust boundary to protect. This category now applies to all prescreen FPs of this type.
- **Bootstrap FP pattern.** The prescreen's self-referential false positives (credential regex and TODO markers flagging themselves) are inherent to security scanning tools. They demonstrate correct behavior — the tool has no context awareness and flags patterns everywhere.
- **Prescreen architecture:** stdlib-only by design (PyYAML is optional with graceful degradation). Implements PS-001 through PS-010, same check IDs as the reference implementation.

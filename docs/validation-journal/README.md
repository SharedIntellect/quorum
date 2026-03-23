# Validation Journal

Quorum validates its own codebase. This directory publishes the results — every finding, every fix, every false positive, with reasoning.

**Why this exists:** A substantiation framework should substantiate itself. Every PR that runs Quorum validation produces calibration data. Rather than claiming accuracy in the abstract, we publish the triage: what was flagged, what was real, what was noise, and why we made each call.

**How entries are produced:** Each PR runs Quorum self-validation in CI. Findings are triaged into four categories: fixed (genuine issue, resolved before merge), false positive (flagged but not a real issue, with reasoning), pre-existing (real but out of scope for this PR, routed to backlog), and tester-excluded (L1 deterministic contradiction — evidence doesn't exist or doesn't match).

---

## Aggregate Metrics

*Updated with each new entry. Counts marked ~ are approximate (PR #10 MEDIUM/LOW counts estimated from partial CI logs).*

| Metric | Value |
|--------|-------|
| PRs validated | 11 |
| Total findings (post-L1) | ~237 |
| Genuine findings (fixed) | 4 |
| False positives | ~136 |
| Pre-existing (backlog) | 81 |
| INFO (neutral observations) | 16 |
| Tester L1 exclusions | 62 |
| **False positive rate** | **~97% of actionable** |
| **Fix rate** | **~3% of actionable** |

*"Actionable" = Fixed + False Positive (excludes pre-existing, INFO, and tester-excluded). The high FP rate reflects early calibration — PRs #10-#12 predate the Tester and rubric refinements. Local documentation validation (PRs #16, #18) caught an additional 13 genuine issues not reflected in CI totals.*

## Detection by Critic

*Approximate attribution based on criterion codes (PC-xxx). Individual entries have precise per-finding detail.*

| Critic | Criteria | Genuine | False Positive | Pre-existing |
|--------|----------|---------|----------------|--------------|
| Correctness | PC-002, 003, 004, 009, 010, 020, 021 | 3 | ~50 | ~25 |
| Security | PC-012, 013, 014 | 1 | ~35 | ~10 |
| Code Hygiene | PC-005, 006, 007, 017, 025 | 0 | ~40 | ~40 |
| Completeness | PC-008, 015, 024 | 0 | ~5 | ~6 |

*Tester L1 operates as a filter, not a critic — it excludes phantom citations before they reach triage. 62 total exclusions across 8 PRs.*

## False Positive Categories

*Categories are explicitly tagged on each false positive in individual entries. Counts below are aggregated across all 11 PRs.*

| Category | Count | Description |
|----------|-------|-------------|
| severity-mismatch | ~40 | Real pattern identified but severity or impact overstated for context |
| callers-guard | ~30 | Function flagged as unsafe but all call sites already validate or guard |
| test-code-pattern | ~18 | Production code rules applied to test files (assert usage, AAA structure, test isolation) |
| broad-except-intentional | ~14 | Catch-all exceptions for documented graceful degradation patterns |
| internal-interface | ~12 | Pydantic/typed model attributes treated as unvalidated external input |
| cli-tool-pattern | ~10 | Web service security rules (path traversal, input sanitization) applied to local CLI tools |
| self-referential | ~4 | Security scanner's own detection patterns flagged by the scanner itself |
| aspirational-comment | ~3 | "Future version could..." comments misread as current contradictions |

## Per-PR Entries

| PR | Date | Version | Verdict | Found | Fixed | FP | Pre-existing | L1 Excluded | Entry |
|----|------|---------|---------|-------|-------|----|--------------|-------------|-------|
| [#10](pr-10-v0.6.1-confidence-to-coverage.md) | 2026-03-12 | v0.6.1 | REVISE | ~64 | 0 | ~64 | 0 | 0 | Confidence → Coverage |
| [#11](pr-11-golden-test-set.md) | 2026-03-12 | — | FAILURE* | 13 | 0 | 13 | 0 | 5 | Golden Test Set |
| [#12](pr-12-v0.7.0-wire-tester.md) | 2026-03-12 | v0.7.0 | REVISE | 34 | 1 | 31 | 0 | 9 | Wire TesterCritic |
| [#13](pr-13-copilot-cli-port.md) | 2026-03-12 | — | REVISE | 10 | 3 | 5 | 0 | 3 | Copilot CLI Port |
| [#14](pr-14-fix-self-validation-findings.md) | 2026-03-12 | v0.7.2 | REVISE | 29 | 0 | 6 | 19 | 13 | Fix Self-Validation |
| [#16](pr-16-docs-restructure.md) | 2026-03-12 | v0.7.2 | REVISE | 8 | 0 | 3 | 5 | 3 | Docs Restructure |
| [#17](pr-17-documentation-rubric.md) | 2026-03-12 | v0.7.2 | REVISE | 10 | 0 | 2 | 8 | 4 | Documentation Rubric |
| [#18](pr-18-stale-content-cleanup.md) | 2026-03-12 | v0.7.2 | PASS | 0 | 0 | 0 | 0 | 0 | Stale Content Cleanup |
| [#19](pr-19-ps007-link-resolution.md) | 2026-03-12 | v0.7.2 | REVISE | 34 | 0 | 4 | 25 | 11 | PS-007 Link Resolution |
| [#20](pr-20-v0.7.3-preexisting-findings.md) | 2026-03-16 | v0.7.3 | REJECT | 35 | 0 | 8 | 24 | 14 | Pre-existing Findings |
| [#21](pr-21-spec-doc002.md) | 2026-03-17 | — | — | 0 | 0 | 0 | 0 | 0 | SPEC DOC-002 Fixes |

*\*PR #11 FAILURE is expected and correct — the golden test set contains intentionally planted defects designed to test Quorum's detection accuracy.*

---

## Methodology

- **Validation tool:** Quorum self-validation (CI workflow + local runs)
- **Depth:** Standard unless noted otherwise in the entry
- **Rubrics:** `python-code` for source files, `documentation` for markdown
- **Triage authority:** Human judgment on all false positive and pre-existing classifications
- **Transparency commitment:** Every finding appears in the journal. Nothing is silently dropped.

## Reading an Entry

Each entry follows a consistent structure:

1. **Validation Summary** — severity breakdown table showing disposition of every finding
2. **Findings Fixed** — genuine issues resolved before merge, with description and fix
3. **False Positives** — flagged but not real issues, with category and reasoning
4. **Tester Exclusions** — findings where L1 deterministic verification proved the evidence citation was invalid (file missing, line out of range, quoted text doesn't match)
5. **Pre-Existing** — real findings that predate this PR, routed to backlog
6. **Notes** — process observations, critic behavior patterns, calibration insights

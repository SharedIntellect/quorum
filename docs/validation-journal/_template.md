# PR #NN — Title

**Date:** YYYY-MM-DD
**Version:** vX.Y.Z (if applicable)
**Branch:** branch-name
**Rubric(s):** python-code | documentation | agent-config | research-synthesis
**Depth:** quick | standard | thorough
**Verdict:** PASS | PASS_WITH_NOTES | REVISE | REJECT

## Validation Summary

| Severity | Found | Fixed | False Positive | Tester Excluded | Pre-existing |
|----------|-------|-------|----------------|-----------------|--------------|
| CRITICAL | 0     | 0     | 0              | 0               | 0            |
| HIGH     | 0     | 0     | 0              | 0               | 0            |
| MEDIUM   | 0     | 0     | 0              | 0               | 0            |
| LOW      | 0     | 0     | 0              | 0               | 0            |
| **Total**| **0** | **0** | **0**          | **0**            | **0**        |

## Findings Fixed Before Merge

<!-- Genuine issues resolved in this PR. Include enough detail to understand what was wrong and how it was fixed. -->

### F-001: [criterion] — [SEVERITY]

- **What:** Description of the finding
- **File:** `filename.py`, line ~N
- **Critic:** correctness | completeness | security | code_hygiene
- **Fix:** What was changed and why

## False Positives

<!-- Findings that were flagged but are not real issues. Each must include reasoning — the "why" is the calibration value. -->

### FP-001: [criterion] — [SEVERITY]

- **What Quorum flagged:** Description of the finding
- **File:** `filename.py`, line ~N
- **Critic:** correctness | completeness | security | code_hygiene
- **Why it's a false positive:** Triage reasoning
- **Category:** See category table below

<!--
False positive categories (add new categories as they emerge):
- broad-except-intentional: `except Exception` where the catch is deliberate design
- test-code-pattern: Test files flagged for patterns correct in test context
- self-referential: Docs/changelogs flagged for mentioning patterns they describe
- callers-guard: Function appears unsafe but all callers already validate
- internal-interface: Typed internal API where external validation is unnecessary
- aspirational-comment: Future-tense comment flagged as contradiction with current behavior
- severity-mismatch: Real pattern but critic over-classified the severity
-->

## Tester Exclusions

<!-- Findings excluded by Tester L1 (deterministic verification). These are phantom citations — the evidence doesn't exist or doesn't match what the critic claimed. -->

### TE-001: [criterion] — [original SEVERITY]

- **What the critic claimed:** Description
- **File:** `filename.py`, line ~N
- **Critic:** correctness | completeness | security | code_hygiene
- **L1 result:** File not found | Line out of range | Quoted text doesn't match (similarity: N%)

## Pre-Existing Findings

<!-- Real findings that predate this PR. Not introduced by this change, routed to backlog. -->

- **[criterion]** in `filename.py` — brief description *(backlog: description of where it's tracked)*

## Notes

<!-- Process observations, critic behavior patterns, calibration insights, anything worth recording for future reference. -->

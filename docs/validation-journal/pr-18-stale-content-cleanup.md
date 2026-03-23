# PR #18 — fix: Stale Content Cleanup + External Reviews Removal

**Date:** 2026-03-12
**Version:** v0.7.2
**Branch:** fix/stale-content-cleanup
**Rubric(s):** documentation (local)
**Depth:** standard
**Verdict:** PASS (CI) / PASS (local documentation validation)

## Validation Summary

No Python source files were modified in this PR, so the CI Quorum self-validation step was not triggered against any `.py` files. Pre-merge documentation validation was performed locally.

**CI result:** PASS (tests: 879 passed, 6 skipped)

## Scope

17 files changed (13 modified, 4 deleted):

- Resolved 13 stale content findings accumulated across PRs #10-#17
- Removed 4 stale external review files (AI-generated reviews against v0.5.3 — outdated after v0.7.2 shipped Tester, golden test set, and documentation rubric)
- Replaced external reviews section with community invitation template
- Updated `validate-docs.py` exclusion path for reorganized `docs/reviews/` directory

## Pre-Merge Validation (Local)

Documentation rubric validation at standard depth across 59 docs:

- 4 in-scope findings found and fixed before merge
- 1 deferred finding (IMPLEMENTATION.md shipped critic list incomplete) resolved post-merge
- `validate-docs.py`: PASS
- Boundary scan: clean

## Notes

- **Stale content debt pattern:** 13 findings accumulated across 4 shipping cycles (PRs #10-#17). Each CI run correctly triaged them as "pre-existing, not in PR scope" — but the aggregate debt grew until a dedicated cleanup was warranted.
- **External review removal rationale:** Reviews were run against v0.5.3 by frontier models evaluating from cached training data, not current repo state. A substantiation framework hosting ungrounded assessments is a credibility contradiction. The validation journal replaces them as the empirical credibility vehicle.
- **First docs-only PR** in the journal — demonstrates that not every PR needs a Quorum CI run to have validation value.

# score.py — Scoring Framework Specification

## Purpose

Compare Quorum validation output against golden test set annotations.
Compute precision, recall, F1, severity accuracy, false positive rate, and verdict accuracy.

## Usage

```bash
# Score a single run
python3 score.py --run-dir results/baseline-20260312/ --annotations-dir annotations/

# Score with custom thresholds
python3 score.py --run-dir results/baseline-20260312/ --annotations-dir annotations/ \
    --min-recall 0.80 --min-precision 0.70

# Output formats
python3 score.py --run-dir results/baseline-20260312/ --annotations-dir annotations/ \
    --format json     # machine-readable
    --format markdown # human-readable report
    --format both     # default: both to stdout + files
```

## Exit Codes

- 0: All thresholds met
- 1: One or more thresholds not met (prints which)
- 2: Error (missing files, schema mismatch, etc.)

## Matching Algorithm

For each artifact in the test set:

1. Load the annotation sidecar (`<artifact-name>.annotations.yaml`)
2. Verify `artifact_sha256` matches the actual file (abort with warning if mismatch)
3. Load Quorum's findings from the run directory
4. For each ground truth finding (GT-###), attempt to match a Quorum finding:
   a. **Critic match:** Quorum finding's `critic` field matches GT `critic` (required)
   b. **Category match:** Quorum finding's category matches GT `category` (required)
   c. **Location match** (if GT has location): Quorum finding location within ±5 lines (preferred) OR description fuzzy match ≥0.6 (fallback)
   d. **Location match** (if GT has no location): description fuzzy match ≥0.6
5. Each Quorum finding can match at most one GT finding (greedy, highest-similarity-first)
6. Each GT finding can be matched at most once

### Classification

- **True Positive (TP):** Quorum finding matches a GT finding
- **False Positive (FP):** Quorum finding matches no GT finding AND is not in a `false_positive_traps` entry (if it matches a trap, it's a **Trapped FP** — counted separately for analysis)
- **False Negative (FN):** GT finding has no matching Quorum finding

## Metrics

### Aggregate

| Metric | Formula |
|--------|---------|
| Detection Precision | TP / (TP + FP) |
| Detection Recall | TP / (TP + FN) |
| F1 | 2 × (P × R) / (P + R) |
| Severity Accuracy | TP_exact_severity / TP |
| Severity Distance (mean) | mean(|GT_tier - Quorum_tier|) for all TPs |
| False Positive Rate (clean) | FP on PASS artifacts / total Quorum findings on PASS artifacts |
| Verdict Accuracy | artifacts_correct_verdict / total_artifacts |
| Trapped FP Count | Quorum findings that hit annotated false_positive_traps |

Severity tier encoding: CRITICAL=4, HIGH=3, MEDIUM=2, LOW=1, INFO=0.

### Sliced (same metrics computed per dimension)

- Per critic: correctness, completeness, security, code_hygiene, cross_consistency
- Per severity: CRITICAL, HIGH, MEDIUM, LOW
- Per complexity: low, medium, high
- Per file type: python-code, yaml-config, markdown-doc, shell-script, cross-artifact
- Per source: synthetic, natural, modified-natural

## Output Format

### JSON (`--format json`)

```json
{
  "schema_version": "1.0",
  "run_dir": "results/baseline-20260312/",
  "timestamp": "2026-03-12T...",
  "aggregate": {
    "precision": 0.82,
    "recall": 0.78,
    "f1": 0.80,
    "severity_accuracy": 0.71,
    "severity_distance_mean": 0.35,
    "fp_rate_clean": 0.10,
    "verdict_accuracy": 0.80,
    "trapped_fp_count": 3,
    "tp": 45,
    "fp": 10,
    "fn": 13,
    "total_gt_findings": 58,
    "total_quorum_findings": 55
  },
  "by_critic": { ... },
  "by_severity": { ... },
  "by_complexity": { ... },
  "by_file_type": { ... },
  "by_source": { ... },
  "per_artifact": [
    {
      "artifact": "artifacts/python/vulnerable-api.py",
      "expected_verdict": "REVISE",
      "actual_verdict": "REVISE",
      "verdict_correct": true,
      "tp": 3,
      "fp": 1,
      "fn": 0,
      "trapped_fp": 0,
      "findings_detail": [
        {
          "gt_id": "GT-001",
          "matched": true,
          "quorum_finding_id": "F-abc123",
          "severity_match": true,
          "gt_severity": "CRITICAL",
          "quorum_severity": "CRITICAL"
        }
      ]
    }
  ],
  "thresholds": {
    "min_recall": 0.80,
    "min_precision": 0.70,
    "met": true
  }
}
```

### Markdown (`--format markdown`)

Human-readable report with:
- Summary table (aggregate metrics)
- Per-critic breakdown table
- Per-artifact results (pass/fail, missed findings, false positives)
- Worst performers (artifacts with lowest recall)
- False positive analysis (most common FP patterns)
- Threshold pass/fail status

## Dependencies

- Standard library only (no external deps beyond what Quorum already requires)
- Uses `difflib.SequenceMatcher` for fuzzy matching (consistent with Quorum's tester)
- Reads Quorum run output via JSON (verdict.json, critics/*.json)

## Testing

Include `tests/test_score.py`:
- Test matching algorithm with known TP/FP/FN cases
- Test severity distance calculation
- Test fuzzy location matching (±5 lines)
- Test handling of clean (PASS) artifacts
- Test trapped false positive detection
- Test SHA-256 integrity check
- Test edge cases: empty annotations, no Quorum findings, all false positives

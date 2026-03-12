#!/usr/bin/env python3
"""Golden Test Set Scoring Framework.

Compares Quorum validation output against human-annotated ground truth.
Computes precision, recall, F1, severity accuracy, false positive rate,
and verdict accuracy — aggregate and sliced by multiple dimensions.

Usage:
    python3 score.py --run-dir results/baseline-20260312/ --annotations-dir annotations/
    python3 score.py --run-dir results/baseline-20260312/ --annotations-dir annotations/ --validate
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEVERITY_TIERS = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
LOCATION_TOLERANCE = 5
FUZZY_THRESHOLD = 0.6
SCHEMA_VERSION = "1.0"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class GTFinding:
    """A single ground-truth finding from an annotation."""
    id: str
    description: str
    location: str | None
    severity: str
    category: str
    critic: str
    rubric_criterion: str | None = None
    notes: str | None = None


@dataclass
class FPTrap:
    """A false-positive trap from an annotation."""
    description: str
    location: str | None = None
    notes: str | None = None


@dataclass
class Annotation:
    """Parsed annotation sidecar for one artifact."""
    artifact: str
    artifact_sha256: str
    expected_verdict: str
    findings: list[GTFinding]
    false_positive_traps: list[FPTrap]
    metadata: dict[str, str]
    schema_version: str = SCHEMA_VERSION


@dataclass
class QuorumFinding:
    """A single finding from Quorum's output."""
    id: str
    severity: str
    category: str | None
    description: str
    location: str | None
    critic: str
    rubric_criterion: str | None = None


@dataclass
class MatchResult:
    """Result of matching one GT finding."""
    gt_id: str
    matched: bool
    quorum_finding_id: str | None = None
    severity_match: bool = False
    gt_severity: str = ""
    quorum_severity: str = ""


@dataclass
class ArtifactScore:
    """Scoring result for one artifact."""
    artifact: str
    expected_verdict: str
    actual_verdict: str | None
    verdict_correct: bool
    tp: int = 0
    fp: int = 0
    fn: int = 0
    trapped_fp: int = 0
    findings_detail: list[MatchResult] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    severity_matches: int = 0
    severity_distances: list[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_annotation(path: Path) -> Annotation:
    """Parse an annotation YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f)

    findings = []
    for fd in data.get("findings") or []:
        findings.append(GTFinding(
            id=fd["id"],
            description=fd["description"],
            location=fd.get("location"),
            severity=fd["severity"],
            category=fd["category"],
            critic=fd["critic"],
            rubric_criterion=fd.get("rubric_criterion"),
            notes=fd.get("notes"),
        ))

    traps = []
    for td in data.get("false_positive_traps") or []:
        traps.append(FPTrap(
            description=td["description"],
            location=td.get("location"),
            notes=td.get("notes"),
        ))

    return Annotation(
        artifact=data["artifact"],
        artifact_sha256=data["artifact_sha256"],
        expected_verdict=data["expected_verdict"],
        findings=findings,
        false_positive_traps=traps,
        metadata=data.get("metadata", {}),
        schema_version=data.get("schema_version", SCHEMA_VERSION),
    )


def parse_quorum_run(run_dir: Path, artifact_name: str) -> tuple[str | None, list[QuorumFinding]]:
    """Parse Quorum output for a specific artifact from a run directory.

    Supports two layouts:
      1. Batch: run_dir/per-file/<timestamp>-<name>/{verdict.json, critics/*.json}
      2. Single: run_dir/{verdict.json, critics/*.json}

    Returns (verdict_status, findings_list).
    """
    # Try batch layout first: look for a subdirectory matching the artifact name
    per_file = run_dir / "per-file"
    target_dir = None

    if per_file.is_dir():
        stem = Path(artifact_name).stem
        for entry in per_file.iterdir():
            if entry.is_dir() and stem in entry.name:
                target_dir = entry
                break

    if target_dir is None:
        # Try single-file layout
        if (run_dir / "verdict.json").exists():
            target_dir = run_dir
        else:
            return None, []

    # Read verdict
    verdict_status = None
    verdict_path = target_dir / "verdict.json"
    if verdict_path.exists():
        with open(verdict_path) as f:
            verdict_data = json.load(f)
        verdict_status = verdict_data.get("status")

    # Read findings from all critic files
    findings: list[QuorumFinding] = []
    critics_dir = target_dir / "critics"
    if critics_dir.is_dir():
        for critic_file in sorted(critics_dir.glob("*-findings.json")):
            critic_name = critic_file.stem.replace("-findings", "")
            with open(critic_file) as f:
                critic_data = json.load(f)
            for fd in critic_data.get("findings", []):
                findings.append(QuorumFinding(
                    id=fd.get("id", ""),
                    severity=fd.get("severity", "INFO"),
                    category=fd.get("category"),
                    description=fd.get("description", ""),
                    location=fd.get("location"),
                    critic=fd.get("critic", critic_name),
                    rubric_criterion=fd.get("rubric_criterion"),
                ))

    # Also read findings from verdict.json if they exist there
    if verdict_path.exists():
        with open(verdict_path) as f:
            verdict_data = json.load(f)
        report = verdict_data.get("report", {})
        for fd in report.get("findings", []):
            # Avoid duplicates by checking ID
            existing_ids = {f.id for f in findings}
            fid = fd.get("id", "")
            if fid and fid not in existing_ids:
                findings.append(QuorumFinding(
                    id=fid,
                    severity=fd.get("severity", "INFO"),
                    category=fd.get("category"),
                    description=fd.get("description", ""),
                    location=fd.get("location"),
                    critic=fd.get("critic", "unknown"),
                    rubric_criterion=fd.get("rubric_criterion"),
                ))

    return verdict_status, findings


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _parse_line_numbers(location: str | None) -> list[int]:
    """Extract line numbers from a location string like 'line 42-48' or 'line 30'.

    Requires either 'line' prefix or a standalone number/range pattern (not embedded
    in words like 'section 3.2').
    """
    if not location:
        return []
    nums = []
    # Match "line N", "line N-M", "Line N", or standalone "N-M" at word boundary
    # Require "line" prefix OR the number must not be preceded by a dot (avoids "section 3.2")
    for m in re.finditer(r"(?:line\s+)(\d+)(?:\s*[-–]\s*(\d+))?|(?:^|(?<=\s))(\d+)\s*[-–]\s*(\d+)", location, re.IGNORECASE):
        if m.group(1) is not None:
            # "line N" or "line N-M"
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else start
        else:
            # Standalone "N-M" range
            start = int(m.group(3))
            end = int(m.group(4))
        nums.extend(range(start, end + 1))
    return nums


def _location_match(gt_location: str | None, q_location: str | None) -> bool:
    """Check if locations overlap within ±LOCATION_TOLERANCE lines."""
    gt_lines = _parse_line_numbers(gt_location)
    q_lines = _parse_line_numbers(q_location)
    if not gt_lines or not q_lines:
        return False
    for gl in gt_lines:
        for ql in q_lines:
            if abs(gl - ql) <= LOCATION_TOLERANCE:
                return True
    return False


def _fuzzy_match(text_a: str, text_b: str) -> float:
    """Fuzzy string similarity using SequenceMatcher."""
    return difflib.SequenceMatcher(None, text_a.lower(), text_b.lower()).ratio()


def _is_trap_match(qf: QuorumFinding, traps: list[FPTrap]) -> bool:
    """Check if a Quorum finding matches any false-positive trap."""
    for trap in traps:
        # Location match
        if trap.location and qf.location:
            if _location_match(trap.location, qf.location):
                return True
        # Description fuzzy match
        if _fuzzy_match(trap.description, qf.description) >= FUZZY_THRESHOLD:
            return True
    return False


def match_findings(
    gt_findings: list[GTFinding],
    quorum_findings: list[QuorumFinding],
    traps: list[FPTrap],
) -> tuple[list[MatchResult], int, int, int, int, int, list[int]]:
    """Match Quorum findings against ground truth.

    Returns: (match_results, tp, fp, fn, trapped_fp, severity_matches, severity_distances)
    """
    # Build similarity scores for all pairs
    pairs: list[tuple[float, int, int]] = []  # (score, gt_idx, q_idx)
    for gi, gt in enumerate(gt_findings):
        for qi, qf in enumerate(quorum_findings):
            # Hard requirements: critic and category must match
            if qf.critic != gt.critic:
                continue
            q_cat = qf.category or qf.critic  # fallback: use critic name as category
            if q_cat != gt.category:
                continue

            # Score: location match gets priority, then fuzzy description
            score = 0.0
            if gt.location and _location_match(gt.location, qf.location):
                score = 1.0
            elif _fuzzy_match(gt.description, qf.description) >= FUZZY_THRESHOLD:
                score = _fuzzy_match(gt.description, qf.description)

            if score > 0:
                pairs.append((score, gi, qi))

    # Greedy matching: highest similarity first
    pairs.sort(key=lambda x: -x[0])
    matched_gt: set[int] = set()
    matched_q: set[int] = set()
    match_map: dict[int, int] = {}  # gt_idx -> q_idx

    for score, gi, qi in pairs:
        if gi not in matched_gt and qi not in matched_q:
            matched_gt.add(gi)
            matched_q.add(qi)
            match_map[gi] = qi

    # Build results
    tp = len(match_map)
    fn = len(gt_findings) - tp

    # Count FP and trapped FP
    trapped_fp = 0
    fp = 0
    for qi, qf in enumerate(quorum_findings):
        if qi not in matched_q:
            if _is_trap_match(qf, traps):
                trapped_fp += 1
            else:
                fp += 1

    # Severity accuracy
    severity_matches = 0
    severity_distances: list[int] = []
    match_results: list[MatchResult] = []

    for gi, gt in enumerate(gt_findings):
        if gi in match_map:
            qi = match_map[gi]
            qf = quorum_findings[qi]
            sev_match = gt.severity == qf.severity
            if sev_match:
                severity_matches += 1
            gt_tier = SEVERITY_TIERS.get(gt.severity, 0)
            q_tier = SEVERITY_TIERS.get(qf.severity, 0)
            severity_distances.append(abs(gt_tier - q_tier))

            match_results.append(MatchResult(
                gt_id=gt.id,
                matched=True,
                quorum_finding_id=qf.id,
                severity_match=sev_match,
                gt_severity=gt.severity,
                quorum_severity=qf.severity,
            ))
        else:
            match_results.append(MatchResult(
                gt_id=gt.id,
                matched=False,
                gt_severity=gt.severity,
            ))

    return match_results, tp, fp, fn, trapped_fp, severity_matches, severity_distances


# ---------------------------------------------------------------------------
# SHA-256 integrity
# ---------------------------------------------------------------------------

def compute_sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Metrics aggregation
# ---------------------------------------------------------------------------

def _safe_div(a: float, b: float) -> float:
    return a / b if b > 0 else 0.0


def _compute_aggregate(scores: list[ArtifactScore]) -> dict[str, Any]:
    """Compute aggregate metrics only (no slicing — avoids recursion)."""
    total_tp = sum(s.tp for s in scores)
    total_fp = sum(s.fp for s in scores)
    total_fn = sum(s.fn for s in scores)
    total_trapped = sum(s.trapped_fp for s in scores)
    total_sev_matches = sum(s.severity_matches for s in scores)
    all_sev_distances: list[int] = []
    for s in scores:
        all_sev_distances.extend(s.severity_distances)

    precision = _safe_div(total_tp, total_tp + total_fp)
    recall = _safe_div(total_tp, total_tp + total_fn)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    severity_accuracy = _safe_div(total_sev_matches, total_tp)
    severity_distance_mean = _safe_div(sum(all_sev_distances), len(all_sev_distances)) if all_sev_distances else 0.0

    clean = [s for s in scores if s.expected_verdict == "PASS"]
    clean_fp = sum(s.fp + s.trapped_fp for s in clean)
    clean_total_q = sum(s.tp + s.fp + s.trapped_fp for s in clean)
    fp_rate_clean = _safe_div(clean_fp, clean_total_q) if clean_total_q > 0 else 0.0

    verdict_correct = sum(1 for s in scores if s.verdict_correct)
    verdict_accuracy = _safe_div(verdict_correct, len(scores))

    total_gt = total_tp + total_fn
    total_q = total_tp + total_fp + total_trapped

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "severity_accuracy": round(severity_accuracy, 4),
        "severity_distance_mean": round(severity_distance_mean, 4),
        "fp_rate_clean": round(fp_rate_clean, 4),
        "verdict_accuracy": round(verdict_accuracy, 4),
        "trapped_fp_count": total_trapped,
        "tp": total_tp,
        "fp": total_fp,
        "fn": total_fn,
        "total_gt_findings": total_gt,
        "total_quorum_findings": total_q,
    }


def compute_metrics(scores: list[ArtifactScore]) -> dict[str, Any]:
    """Compute aggregate and sliced metrics from per-artifact scores."""
    aggregate = _compute_aggregate(scores)

    # Sliced metrics
    def _slice(key_fn: Any) -> dict[str, dict[str, Any]]:
        buckets: dict[str, list[ArtifactScore]] = {}
        for s in scores:
            k = key_fn(s)
            buckets.setdefault(k, []).append(s)
        result = {}
        for k, bucket in sorted(buckets.items()):
            m = _compute_aggregate(bucket)
            result[k] = m
        return result

    by_critic: dict[str, dict[str, Any]] = {}
    for critic_name in ["correctness", "completeness", "security", "code_hygiene", "cross_consistency"]:
        # Filter findings per critic — create synthetic ArtifactScores
        critic_scores = []
        for s in scores:
            # This is a simplification — full per-critic slicing would require
            # re-running matching per critic. For now, use metadata category.
            pass
        by_critic[critic_name] = {}  # populated below

    sliced = {
        "by_complexity": _slice(lambda s: s.metadata.get("complexity", "unknown")),
        "by_file_type": _slice(lambda s: s.metadata.get("domain", "unknown")),
        "by_source": _slice(lambda s: s.metadata.get("source", "unknown")),
    }

    # Per-severity slice (need to reconstruct from finding details)
    by_severity: dict[str, dict[str, int]] = {}
    for s in scores:
        for mr in s.findings_detail:
            sev = mr.gt_severity
            if sev not in by_severity:
                by_severity[sev] = {"tp": 0, "fn": 0}
            if mr.matched:
                by_severity[sev]["tp"] += 1
            else:
                by_severity[sev]["fn"] += 1
    severity_slice = {}
    for sev, counts in sorted(by_severity.items()):
        t = counts["tp"]
        f = counts["fn"]
        r = _safe_div(t, t + f)
        severity_slice[sev] = {"recall": round(r, 4), "tp": t, "fn": f}
    sliced["by_severity"] = severity_slice

    return {
        "aggregate": aggregate,
        **sliced,
    }


# ---------------------------------------------------------------------------
# Validation mode
# ---------------------------------------------------------------------------

def validate_annotations(annotations_dir: Path, golden_dir: Path) -> list[str]:
    """Validate all annotations: schema compliance + SHA-256 integrity."""
    errors: list[str] = []
    count = 0
    for ann_path in sorted(annotations_dir.glob("*.annotations.yaml")):
        count += 1
        try:
            ann = parse_annotation(ann_path)
        except Exception as e:
            errors.append(f"{ann_path.name}: parse error: {e}")
            continue

        # Check schema version
        if ann.schema_version != SCHEMA_VERSION:
            errors.append(f"{ann_path.name}: schema_version {ann.schema_version} != {SCHEMA_VERSION}")

        # Check required fields
        if not ann.artifact:
            errors.append(f"{ann_path.name}: missing artifact path")
        if not ann.expected_verdict:
            errors.append(f"{ann_path.name}: missing expected_verdict")
        if ann.expected_verdict not in ("PASS", "PASS_WITH_NOTES", "REVISE", "REJECT"):
            errors.append(f"{ann_path.name}: invalid expected_verdict '{ann.expected_verdict}'")

        # Check artifact exists and SHA-256 matches
        artifact_path = golden_dir / ann.artifact
        if not artifact_path.exists():
            errors.append(f"{ann_path.name}: artifact not found at {ann.artifact}")
        elif artifact_path.is_dir():
            # Cross-artifact pairs: SHA is typically of the primary document
            # Just verify the directory exists and has files
            if not any(artifact_path.iterdir()):
                errors.append(f"{ann_path.name}: artifact directory is empty at {ann.artifact}")
        else:
            actual_sha = compute_sha256(artifact_path)
            if actual_sha != ann.artifact_sha256:
                errors.append(
                    f"{ann_path.name}: SHA-256 mismatch — "
                    f"expected {ann.artifact_sha256[:16]}... got {actual_sha[:16]}..."
                )

        # Check findings have required fields
        seen_ids: set[str] = set()
        for fd in ann.findings:
            if fd.id in seen_ids:
                errors.append(f"{ann_path.name}: duplicate finding ID {fd.id}")
            seen_ids.add(fd.id)
            if fd.severity not in SEVERITY_TIERS:
                errors.append(f"{ann_path.name}: {fd.id} invalid severity '{fd.severity}'")
            if fd.category not in ("security", "correctness", "completeness", "code_hygiene", "cross_consistency"):
                errors.append(f"{ann_path.name}: {fd.id} invalid category '{fd.category}'")

        # Check metadata
        for req in ("source", "domain", "complexity", "rubric", "depth", "author", "created"):
            if req not in ann.metadata:
                errors.append(f"{ann_path.name}: missing metadata.{req}")

        # PASS artifacts should have no findings
        if ann.expected_verdict == "PASS" and ann.findings:
            errors.append(f"{ann_path.name}: PASS verdict but has {len(ann.findings)} findings")

    if count == 0:
        errors.append("No annotation files found")

    return errors


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_json(metrics: dict, scores: list[ArtifactScore], run_dir: str) -> str:
    """Format results as JSON."""
    from datetime import datetime, timezone
    output = {
        "schema_version": SCHEMA_VERSION,
        "run_dir": run_dir,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **metrics,
        "per_artifact": [],
    }
    for s in scores:
        output["per_artifact"].append({
            "artifact": s.artifact,
            "expected_verdict": s.expected_verdict,
            "actual_verdict": s.actual_verdict,
            "verdict_correct": s.verdict_correct,
            "tp": s.tp,
            "fp": s.fp,
            "fn": s.fn,
            "trapped_fp": s.trapped_fp,
            "findings_detail": [
                {
                    "gt_id": mr.gt_id,
                    "matched": mr.matched,
                    "quorum_finding_id": mr.quorum_finding_id,
                    "severity_match": mr.severity_match,
                    "gt_severity": mr.gt_severity,
                    "quorum_severity": mr.quorum_severity,
                }
                for mr in s.findings_detail
            ],
        })
    return json.dumps(output, indent=2)


def format_markdown(metrics: dict, scores: list[ArtifactScore], thresholds: dict) -> str:
    """Format results as Markdown report."""
    agg = metrics["aggregate"]
    lines = [
        "# Golden Test Set — Scoring Report",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Detection Precision | {agg['precision']:.2%} |",
        f"| Detection Recall | {agg['recall']:.2%} |",
        f"| F1 | {agg['f1']:.2%} |",
        f"| Severity Accuracy | {agg['severity_accuracy']:.2%} |",
        f"| Severity Distance (mean) | {agg['severity_distance_mean']:.2f} |",
        f"| FP Rate (clean) | {agg['fp_rate_clean']:.2%} |",
        f"| Verdict Accuracy | {agg['verdict_accuracy']:.2%} |",
        f"| Trapped FP Count | {agg['trapped_fp_count']} |",
        "",
        f"**Totals:** {agg['tp']} TP, {agg['fp']} FP, {agg['fn']} FN "
        f"({agg['total_gt_findings']} GT findings, {agg['total_quorum_findings']} Quorum findings)",
        "",
    ]

    # Thresholds
    lines.extend([
        "## Thresholds",
        "",
        "| Metric | Target | Actual | Status |",
        "|--------|--------|--------|--------|",
    ])
    checks = [
        ("Recall", thresholds.get("min_recall", 0.80), agg["recall"]),
        ("Precision", thresholds.get("min_precision", 0.70), agg["precision"]),
    ]
    all_met = True
    for name, target, actual in checks:
        met = actual >= target
        if not met:
            all_met = False
        status = "PASS" if met else "FAIL"
        lines.append(f"| {name} | {target:.0%} | {actual:.2%} | {status} |")
    lines.append("")

    # Per-complexity breakdown
    if "by_complexity" in metrics:
        lines.extend(["## By Complexity", "", "| Complexity | Precision | Recall | F1 |", "|------------|-----------|--------|-----|"])
        for k, v in metrics["by_complexity"].items():
            lines.append(f"| {k} | {v['precision']:.2%} | {v['recall']:.2%} | {v['f1']:.2%} |")
        lines.append("")

    # Per-severity breakdown
    if "by_severity" in metrics:
        lines.extend(["## By Severity", "", "| Severity | Recall | TP | FN |", "|----------|--------|----|----|"])
        for k, v in metrics["by_severity"].items():
            lines.append(f"| {k} | {v['recall']:.2%} | {v['tp']} | {v['fn']} |")
        lines.append("")

    # Per-artifact results
    lines.extend(["## Per-Artifact Results", "", "| Artifact | Expected | Actual | Verdict | TP | FP | FN |",
                   "|----------|----------|--------|---------|----|----|-----|"])
    for s in sorted(scores, key=lambda x: x.artifact):
        v_mark = "correct" if s.verdict_correct else "WRONG"
        lines.append(f"| {s.artifact} | {s.expected_verdict} | {s.actual_verdict or 'N/A'} | {v_mark} | {s.tp} | {s.fp} | {s.fn} |")
    lines.append("")

    # Worst performers
    worst = sorted([s for s in scores if s.fn > 0], key=lambda x: -x.fn)[:5]
    if worst:
        lines.extend(["## Worst Performers (most missed findings)", ""])
        for s in worst:
            missed = [mr.gt_id for mr in s.findings_detail if not mr.matched]
            lines.append(f"- **{s.artifact}**: {s.fn} missed — {', '.join(missed)}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main scoring pipeline
# ---------------------------------------------------------------------------

def score(
    run_dir: Path,
    annotations_dir: Path,
    golden_dir: Path,
    thresholds: dict[str, float],
) -> tuple[dict[str, Any], list[ArtifactScore], bool]:
    """Run the full scoring pipeline.

    Returns: (metrics_dict, per_artifact_scores, thresholds_met)
    """
    scores: list[ArtifactScore] = []
    warnings: list[str] = []

    for ann_path in sorted(annotations_dir.glob("*.annotations.yaml")):
        ann = parse_annotation(ann_path)

        # SHA-256 integrity check
        artifact_path = golden_dir / ann.artifact
        if artifact_path.exists():
            actual_sha = compute_sha256(artifact_path)
            if actual_sha != ann.artifact_sha256:
                warnings.append(
                    f"WARNING: SHA-256 mismatch for {ann.artifact} "
                    f"(expected {ann.artifact_sha256[:16]}..., got {actual_sha[:16]}...)"
                )

        # Parse Quorum output
        actual_verdict, quorum_findings = parse_quorum_run(run_dir, ann.artifact)

        # Match findings
        match_results, tp, fp, fn, trapped_fp, sev_matches, sev_dists = match_findings(
            ann.findings, quorum_findings, ann.false_positive_traps
        )

        verdict_correct = (actual_verdict == ann.expected_verdict) if actual_verdict else False

        scores.append(ArtifactScore(
            artifact=ann.artifact,
            expected_verdict=ann.expected_verdict,
            actual_verdict=actual_verdict,
            verdict_correct=verdict_correct,
            tp=tp,
            fp=fp,
            fn=fn,
            trapped_fp=trapped_fp,
            findings_detail=match_results,
            metadata=ann.metadata,
            severity_matches=sev_matches,
            severity_distances=sev_dists,
        ))

    # Print warnings
    for w in warnings:
        print(w, file=sys.stderr)

    # Compute metrics
    metrics = compute_metrics(scores)

    # Check thresholds
    agg = metrics["aggregate"]
    met = True
    for key, target in thresholds.items():
        metric_name = key.replace("min_", "")
        if metric_name in agg and agg[metric_name] < target:
            met = False
            print(f"THRESHOLD NOT MET: {metric_name} = {agg[metric_name]:.4f} < {target}", file=sys.stderr)

    metrics["thresholds"] = {**thresholds, "met": met}

    return metrics, scores, met


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Score Quorum output against golden test set annotations")
    parser.add_argument("--run-dir", type=Path, help="Path to Quorum run output directory")
    parser.add_argument("--annotations-dir", type=Path, default=Path("annotations"),
                        help="Path to annotations directory (default: annotations/)")
    parser.add_argument("--golden-dir", type=Path, default=None,
                        help="Path to golden-test-set root (default: parent of annotations-dir)")
    parser.add_argument("--min-recall", type=float, default=0.80)
    parser.add_argument("--min-precision", type=float, default=0.70)
    parser.add_argument("--format", choices=["json", "markdown", "both"], default="both",
                        dest="output_format")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Write output files to this directory")
    parser.add_argument("--validate", action="store_true",
                        help="Validate annotations without scoring (no run-dir needed)")

    args = parser.parse_args()

    golden_dir = args.golden_dir or args.annotations_dir.parent

    # Validate mode
    if args.validate:
        errors = validate_annotations(args.annotations_dir, golden_dir)
        if errors:
            print(f"Validation found {len(errors)} error(s):", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
            return 2
        print(f"All annotations valid.")
        return 0

    # Score mode
    if not args.run_dir:
        parser.error("--run-dir is required for scoring (use --validate for validation-only)")

    if not args.run_dir.is_dir():
        print(f"ERROR: run directory not found: {args.run_dir}", file=sys.stderr)
        return 2

    thresholds = {
        "min_recall": args.min_recall,
        "min_precision": args.min_precision,
    }

    try:
        metrics, scores, met = score(args.run_dir, args.annotations_dir, golden_dir, thresholds)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    # Output
    if args.output_format in ("json", "both"):
        json_str = format_json(metrics, scores, str(args.run_dir))
        if args.output_dir:
            out_path = args.output_dir / "score-results.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json_str)
            print(f"JSON results written to {out_path}")
        else:
            print(json_str)

    if args.output_format in ("markdown", "both"):
        md_str = format_markdown(metrics, scores, thresholds)
        if args.output_dir:
            out_path = args.output_dir / "score-report.md"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(md_str)
            print(f"Markdown report written to {out_path}")
        else:
            print(md_str)

    return 0 if met else 1


if __name__ == "__main__":
    sys.exit(main())

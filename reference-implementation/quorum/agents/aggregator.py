"""
Aggregator Agent — Deduplicates findings, resolves conflicts, produces verdict.

The Aggregator:
1. Collects all CriticResults
2. Deduplicates findings that describe the same issue from different critics
3. Recalibrates confidence from inter-critic agreement
4. Assigns the final Verdict (PASS / PASS_WITH_NOTES / REVISE / REJECT)

The verdict is determined by the highest severity findings:
- REJECT:          Any CRITICAL findings present
- REVISE:          Any HIGH findings present
- PASS_WITH_NOTES: Any MEDIUM or LOW findings present
- PASS:            No findings (or all INFO)
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher

from quorum.config import QuorumConfig
from quorum.models import (
    AggregatedReport,
    CriticResult,
    Finding,
    Severity,
    Verdict,
    VerdictStatus,
)
from quorum.providers.base import BaseProvider

logger = logging.getLogger(__name__)

# Similarity threshold for deduplication (0.0–1.0)
# Findings with description similarity above this are considered duplicates
DEDUP_THRESHOLD = 0.72


class AggregatorAgent:
    """
    Synthesizes findings from multiple critics into a coherent verdict.

    Does NOT call the LLM for verdict assignment (uses deterministic rules).
    A future version could use the LLM for subtle conflict resolution.
    """

    def __init__(self, provider: BaseProvider, config: QuorumConfig):
        self.provider = provider
        self.config = config

    def run(self, critic_results: list[CriticResult]) -> Verdict:
        """
        Main entry point.

        Args:
            critic_results: List of CriticResult from each critic

        Returns:
            Final Verdict with AggregatedReport attached
        """
        all_findings = self._collect_findings(critic_results)
        deduped_findings, conflicts_resolved = self._deduplicate(all_findings)
        confidence = self._calculate_confidence(critic_results, deduped_findings)

        report = AggregatedReport(
            findings=deduped_findings,
            confidence=confidence,
            conflicts_resolved=conflicts_resolved,
            critic_results=critic_results,
        )

        verdict = self._assign_verdict(report)
        logger.info(
            "Aggregator: %d findings → %d deduped → verdict=%s (confidence=%.2f)",
            len(all_findings), len(deduped_findings), verdict.status.value, confidence,
        )

        return verdict

    def _collect_findings(self, results: list[CriticResult]) -> list[Finding]:
        """Flatten all findings from all critics into a single list."""
        findings = []
        for result in results:
            if not result.skipped:
                findings.extend(result.findings)
        return findings

    def _similarity(self, a: str, b: str) -> float:
        """String similarity ratio between two descriptions."""
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def _deduplicate(
        self, findings: list[Finding]
    ) -> tuple[list[Finding], int]:
        """
        Remove duplicate findings reported by multiple critics.

        Strategy: For each pair of findings, if their descriptions are
        above DEDUP_THRESHOLD similar, keep the one with higher severity
        (or the first one if equal). Tag the survivor with all source critics.

        Returns:
            (deduplicated_findings, number_of_conflicts_resolved)
        """
        if not findings:
            return [], 0

        kept: list[Finding] = []
        conflicts_resolved = 0

        for candidate in findings:
            is_duplicate = False
            for i, existing in enumerate(kept):
                sim = self._similarity(candidate.description, existing.description)
                if sim >= DEDUP_THRESHOLD:
                    is_duplicate = True
                    conflicts_resolved += 1
                    # Keep the higher-severity finding
                    severity_order = {
                        Severity.CRITICAL: 5,
                        Severity.HIGH: 4,
                        Severity.MEDIUM: 3,
                        Severity.LOW: 2,
                        Severity.INFO: 1,
                    }
                    if severity_order[candidate.severity] > severity_order[existing.severity]:
                        # Replace with the higher-severity version, preserving source info
                        merged_source = f"{existing.critic_source},{candidate.critic_source}"
                        kept[i] = candidate.model_copy(
                            update={"critic_source": merged_source}
                        )
                    else:
                        # Keep existing but note the additional critic source
                        merged_source = f"{existing.critic_source},{candidate.critic_source}"
                        kept[i] = existing.model_copy(
                            update={"critic_source": merged_source}
                        )
                    break

            if not is_duplicate:
                kept.append(candidate)

        return kept, conflicts_resolved

    def _calculate_confidence(
        self,
        results: list[CriticResult],
        findings: list[Finding],
    ) -> float:
        """
        Calculate overall confidence from:
        - Average critic confidence
        - Agreement between critics (higher agreement = higher confidence)
        - Penalty for skipped critics
        """
        active_results = [r for r in results if not r.skipped]
        if not active_results:
            return 0.0

        avg_confidence = sum(r.confidence for r in active_results) / len(active_results)

        # Penalize for skipped critics
        skipped_count = sum(1 for r in results if r.skipped)
        skip_penalty = 0.05 * skipped_count

        # Bonus for inter-critic agreement (same severity findings appear in multiple critics)
        agreement_bonus = 0.0
        if len(active_results) > 1 and findings:
            multi_source = sum(
                1 for f in findings if "," in f.critic_source
            )
            agreement_bonus = min(0.1, 0.02 * multi_source)

        confidence = max(0.0, min(1.0, avg_confidence - skip_penalty + agreement_bonus))
        return round(confidence, 3)

    def _assign_verdict(self, report: AggregatedReport) -> Verdict:
        """
        Deterministic verdict assignment based on findings severity.

        Rules:
        - REJECT:          1+ CRITICAL findings
        - REVISE:          1+ HIGH findings (no CRITICAL)
        - PASS_WITH_NOTES: 1+ MEDIUM/LOW findings (no CRITICAL/HIGH)
        - PASS:            No findings above INFO level
        """
        findings = report.findings

        critical = [f for f in findings if f.severity == Severity.CRITICAL]
        high = [f for f in findings if f.severity == Severity.HIGH]
        medium = [f for f in findings if f.severity == Severity.MEDIUM]
        low = [f for f in findings if f.severity in (Severity.LOW, Severity.INFO)]

        if critical:
            status = VerdictStatus.REJECT
            reasoning = (
                f"Found {len(critical)} CRITICAL issue(s) that must be resolved before acceptance. "
                f"Critical issues represent fundamental problems with the artifact."
            )
        elif high:
            status = VerdictStatus.REVISE
            reasoning = (
                f"Found {len(high)} HIGH severity issue(s) requiring rework. "
                f"Address these before the artifact can be accepted."
            )
        elif medium or low:
            status = VerdictStatus.PASS_WITH_NOTES
            total_notes = len(medium) + len(low)
            reasoning = (
                f"Artifact passes with {total_notes} note(s). "
                f"No blocking issues found; recommendations are advisory."
            )
        else:
            status = VerdictStatus.PASS
            reasoning = "No issues found. The artifact meets all evaluated criteria."

        # Add summary counts to reasoning
        counts = []
        if critical:
            counts.append(f"{len(critical)} CRITICAL")
        if high:
            counts.append(f"{len(high)} HIGH")
        if medium:
            counts.append(f"{len(medium)} MEDIUM")
        if low:
            counts.append(f"{len(low)} LOW")

        if counts:
            reasoning += f" Issues: {', '.join(counts)}."

        return Verdict(
            status=status,
            reasoning=reasoning,
            confidence=report.confidence,
            report=report,
        )

"""Phase 2: Aggregator Agent tests — deduplication, confidence, verdict assignment."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from quorum.agents.aggregator import DEDUP_THRESHOLD, AggregatorAgent
from quorum.config import QuorumConfig
from quorum.models import (
    AggregatedReport,
    CriticResult,
    Evidence,
    Finding,
    Severity,
    Verdict,
    VerdictStatus,
)


def make_finding(severity=Severity.MEDIUM, description="Test finding", critic="correctness", **kwargs):
    defaults = dict(severity=severity, description=description, evidence=Evidence(tool="grep", result="matched line 42"), critic=critic)
    defaults.update(kwargs)
    return Finding(**defaults)


def make_critic_result(name="correctness", findings=None, confidence=0.85):
    return CriticResult(critic_name=name, findings=findings or [], confidence=confidence, runtime_ms=100)


@pytest.fixture
def config() -> QuorumConfig:
    return QuorumConfig(
        critics=["correctness"],
        model_tier1="test-model",
        model_tier2="test-model",
        depth_profile="quick",
    )


@pytest.fixture
def aggregator(config) -> AggregatorAgent:
    provider = MagicMock()
    return AggregatorAgent(provider=provider, config=config)


# ── Collect Findings ──────────────────────────────────────────────────────────


class TestCollectFindings:
    def test_collects_from_multiple_critics(self, aggregator):
        f1 = make_finding(description="Issue A", critic="correctness")
        f2 = make_finding(description="Issue B", critic="completeness")
        results = [
            make_critic_result("correctness", [f1]),
            make_critic_result("completeness", [f2]),
        ]
        collected = aggregator._collect_findings(results)
        assert len(collected) == 2

    def test_skips_skipped_results(self, aggregator):
        f1 = make_finding(description="Issue A")
        active = make_critic_result("correctness", [f1])
        skipped = CriticResult(
            critic_name="security",
            findings=[make_finding(description="Should be skipped")],
            confidence=0.0,
            runtime_ms=0,
            skipped=True,
            skip_reason="test skip",
        )
        collected = aggregator._collect_findings([active, skipped])
        assert len(collected) == 1
        assert collected[0].description == "Issue A"

    def test_empty_results(self, aggregator):
        collected = aggregator._collect_findings([])
        assert collected == []

    def test_all_skipped(self, aggregator):
        skipped = CriticResult(
            critic_name="correctness",
            findings=[make_finding()],
            confidence=0.0,
            runtime_ms=0,
            skipped=True,
        )
        collected = aggregator._collect_findings([skipped])
        assert collected == []


# ── Similarity ────────────────────────────────────────────────────────────────


class TestSimilarity:
    def test_identical_strings(self, aggregator):
        assert aggregator._similarity("hello world", "hello world") == 1.0

    def test_completely_different(self, aggregator):
        sim = aggregator._similarity("aaa", "zzz")
        assert sim < 0.5

    def test_case_insensitive(self, aggregator):
        sim = aggregator._similarity("Hello World", "hello world")
        assert sim == 1.0

    def test_similar_above_threshold(self, aggregator):
        sim = aggregator._similarity(
            "Missing error handling in validate function",
            "Missing error handling in validation function",
        )
        assert sim >= DEDUP_THRESHOLD


# ── Deduplication ─────────────────────────────────────────────────────────────


class TestDeduplicate:
    def test_no_duplicates(self, aggregator):
        findings = [
            make_finding(description="Completely different issue about security"),
            make_finding(description="Unrelated problem with formatting"),
        ]
        deduped, conflicts = aggregator._deduplicate(findings)
        assert len(deduped) == 2
        assert conflicts == 0

    def test_identical_descriptions_merged(self, aggregator):
        findings = [
            make_finding(description="Missing error handling in function", critic="correctness"),
            make_finding(description="Missing error handling in function", critic="completeness"),
        ]
        deduped, conflicts = aggregator._deduplicate(findings)
        assert len(deduped) == 1
        assert conflicts == 1
        assert "correctness" in deduped[0].critic
        assert "completeness" in deduped[0].critic

    def test_higher_severity_wins(self, aggregator):
        findings = [
            make_finding(
                description="Missing error handling in function",
                severity=Severity.MEDIUM,
                critic="correctness",
            ),
            make_finding(
                description="Missing error handling in function",
                severity=Severity.HIGH,
                critic="completeness",
            ),
        ]
        deduped, conflicts = aggregator._deduplicate(findings)
        assert len(deduped) == 1
        assert deduped[0].severity == Severity.HIGH

    def test_equal_severity_keeps_first(self, aggregator):
        findings = [
            make_finding(
                description="Missing error handling in function",
                severity=Severity.MEDIUM,
                critic="first_critic",
            ),
            make_finding(
                description="Missing error handling in function",
                severity=Severity.MEDIUM,
                critic="second_critic",
            ),
        ]
        deduped, _ = aggregator._deduplicate(findings)
        assert len(deduped) == 1
        # First finding kept, with merged critic
        assert "first_critic" in deduped[0].critic

    def test_empty_findings(self, aggregator):
        deduped, conflicts = aggregator._deduplicate([])
        assert deduped == []
        assert conflicts == 0

    def test_three_similar_findings(self, aggregator):
        findings = [
            make_finding(description="Missing error handling in function", critic="a"),
            make_finding(description="Missing error handling in function", critic="b"),
            make_finding(description="Missing error handling in function", critic="c"),
        ]
        deduped, conflicts = aggregator._deduplicate(findings)
        assert len(deduped) == 1
        assert conflicts == 2


# ── Confidence Calculation ────────────────────────────────────────────────────


class TestCalculateConfidence:
    def test_single_active_result(self, aggregator):
        results = [make_critic_result("correctness", confidence=0.8)]
        conf = aggregator._calculate_confidence(results, [])
        assert conf == 0.8

    def test_average_of_active(self, aggregator):
        results = [
            make_critic_result("correctness", confidence=0.8),
            make_critic_result("completeness", confidence=0.6),
        ]
        conf = aggregator._calculate_confidence(results, [])
        assert conf == 0.7

    def test_skip_penalty(self, aggregator):
        active = make_critic_result("correctness", confidence=0.8)
        skipped = CriticResult(
            critic_name="security",
            findings=[],
            confidence=0.0,
            runtime_ms=0,
            skipped=True,
        )
        conf = aggregator._calculate_confidence([active, skipped], [])
        assert conf == pytest.approx(0.75, abs=0.01)  # 0.8 - 0.05

    def test_agreement_bonus(self, aggregator):
        results = [
            make_critic_result("correctness", confidence=0.8),
            make_critic_result("completeness", confidence=0.8),
        ]
        # Finding with merged critic (comma = seen by multiple)
        finding = make_finding(critic="correctness,completeness")
        conf = aggregator._calculate_confidence(results, [finding])
        assert conf > 0.8  # bonus applied

    def test_all_skipped_returns_zero(self, aggregator):
        skipped = CriticResult(
            critic_name="correctness",
            findings=[],
            confidence=0.0,
            runtime_ms=0,
            skipped=True,
        )
        conf = aggregator._calculate_confidence([skipped], [])
        assert conf == 0.0

    def test_confidence_clamped_to_one(self, aggregator):
        results = [
            make_critic_result("correctness", confidence=1.0),
            make_critic_result("completeness", confidence=1.0),
        ]
        findings = [make_finding(critic="a,b") for _ in range(20)]
        conf = aggregator._calculate_confidence(results, findings)
        assert conf <= 1.0

    def test_confidence_clamped_to_zero(self, aggregator):
        results = [
            make_critic_result("correctness", confidence=0.0),
        ]
        skipped_results = [
            CriticResult(
                critic_name=f"critic_{i}",
                findings=[], confidence=0.0, runtime_ms=0, skipped=True,
            )
            for i in range(20)
        ]
        conf = aggregator._calculate_confidence(
            results + skipped_results, []
        )
        assert conf >= 0.0


# ── Verdict Assignment ────────────────────────────────────────────────────────


class TestAssignVerdict:
    def test_no_findings_pass(self, aggregator):
        report = AggregatedReport(findings=[], confidence=0.9, critic_results=[])
        verdict = aggregator._assign_verdict(report)
        assert verdict.status == VerdictStatus.PASS
        assert "No issues found" in verdict.reasoning

    def test_critical_finding_reject(self, aggregator):
        report = AggregatedReport(
            findings=[make_finding(severity=Severity.CRITICAL)],
            confidence=0.9,
            critic_results=[],
        )
        verdict = aggregator._assign_verdict(report)
        assert verdict.status == VerdictStatus.REJECT
        assert "CRITICAL" in verdict.reasoning

    def test_high_finding_revise(self, aggregator):
        report = AggregatedReport(
            findings=[make_finding(severity=Severity.HIGH)],
            confidence=0.9,
            critic_results=[],
        )
        verdict = aggregator._assign_verdict(report)
        assert verdict.status == VerdictStatus.REVISE
        assert "HIGH" in verdict.reasoning

    def test_medium_finding_pass_with_notes(self, aggregator):
        report = AggregatedReport(
            findings=[make_finding(severity=Severity.MEDIUM)],
            confidence=0.9,
            critic_results=[],
        )
        verdict = aggregator._assign_verdict(report)
        assert verdict.status == VerdictStatus.PASS_WITH_NOTES

    def test_low_finding_pass_with_notes(self, aggregator):
        report = AggregatedReport(
            findings=[make_finding(severity=Severity.LOW)],
            confidence=0.9,
            critic_results=[],
        )
        verdict = aggregator._assign_verdict(report)
        assert verdict.status == VerdictStatus.PASS_WITH_NOTES

    def test_info_finding_pass_with_notes(self, aggregator):
        report = AggregatedReport(
            findings=[make_finding(severity=Severity.INFO)],
            confidence=0.9,
            critic_results=[],
        )
        verdict = aggregator._assign_verdict(report)
        assert verdict.status == VerdictStatus.PASS_WITH_NOTES

    def test_critical_trumps_high(self, aggregator):
        report = AggregatedReport(
            findings=[
                make_finding(severity=Severity.CRITICAL),
                make_finding(severity=Severity.HIGH),
            ],
            confidence=0.9,
            critic_results=[],
        )
        verdict = aggregator._assign_verdict(report)
        assert verdict.status == VerdictStatus.REJECT

    def test_verdict_has_summary_counts(self, aggregator):
        report = AggregatedReport(
            findings=[
                make_finding(severity=Severity.HIGH),
                make_finding(severity=Severity.MEDIUM),
            ],
            confidence=0.9,
            critic_results=[],
        )
        verdict = aggregator._assign_verdict(report)
        assert "1 HIGH" in verdict.reasoning
        assert "1 MEDIUM" in verdict.reasoning

    def test_verdict_confidence_from_report(self, aggregator):
        report = AggregatedReport(findings=[], confidence=0.77, critic_results=[])
        verdict = aggregator._assign_verdict(report)
        assert verdict.confidence == 0.77


# ── Full Run ──────────────────────────────────────────────────────────────────


class TestAggregatorRun:
    def test_full_run_pass(self, aggregator):
        results = [make_critic_result("correctness", [], confidence=0.9)]
        verdict = aggregator.run(results)
        assert verdict.status == VerdictStatus.PASS
        assert verdict.report is not None
        assert verdict.report.findings == []

    def test_full_run_reject(self, aggregator):
        findings = [make_finding(severity=Severity.CRITICAL)]
        results = [make_critic_result("correctness", findings, confidence=0.9)]
        verdict = aggregator.run(results)
        assert verdict.status == VerdictStatus.REJECT

    def test_full_run_deduplicates(self, aggregator):
        f1 = make_finding(description="Same issue found here", critic="correctness")
        f2 = make_finding(description="Same issue found here", critic="completeness")
        results = [
            make_critic_result("correctness", [f1]),
            make_critic_result("completeness", [f2]),
        ]
        verdict = aggregator.run(results)
        assert len(verdict.report.findings) == 1
        assert verdict.report.conflicts_resolved == 1

    def test_full_run_with_mixed_severity(self, aggregator):
        results = [
            make_critic_result("correctness", [
                make_finding(severity=Severity.HIGH),
                make_finding(severity=Severity.LOW),
            ]),
        ]
        verdict = aggregator.run(results)
        assert verdict.status == VerdictStatus.REVISE

    def test_full_run_empty_results(self, aggregator):
        verdict = aggregator.run([])
        assert verdict.status == VerdictStatus.PASS
        assert verdict.confidence == 0.0

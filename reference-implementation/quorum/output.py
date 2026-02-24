# SPDX-License-Identifier: MIT
# Copyright 2026 SharedIntellect — https://github.com/SharedIntellect/quorum

"""
Terminal output formatter for Quorum.

Produces colored, structured output to stdout:
- Verdict banner (color-coded by status)
- Findings summary (counts by severity)
- Detailed findings list (with evidence excerpts)
- Run directory location

Uses ANSI color codes. Falls back to plain text if terminal doesn't support color.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from quorum.models import AggregatedReport, Finding, Severity, Verdict, VerdictStatus


# ANSI color codes
class Color:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[31m"
    YELLOW  = "\033[33m"
    GREEN   = "\033[32m"
    CYAN    = "\033[36m"
    BLUE    = "\033[34m"
    MAGENTA = "\033[35m"
    WHITE   = "\033[37m"
    BG_RED    = "\033[41m"
    BG_YELLOW = "\033[43m"
    BG_GREEN  = "\033[42m"
    BG_BLUE   = "\033[44m"


def _supports_color() -> bool:
    """Check if the terminal supports ANSI color codes."""
    if not sys.stdout.isatty():
        return False
    term = os.environ.get("TERM", "")
    if term in ("dumb", ""):
        return False
    return True


def _c(text: str, *codes: str) -> str:
    """Apply color codes to text (or return plain text if no color support)."""
    if not _supports_color():
        return text
    return "".join(codes) + text + Color.RESET


def _severity_color(severity: Severity) -> str:
    """Return the color code for a severity level."""
    return {
        Severity.CRITICAL: Color.RED + Color.BOLD,
        Severity.HIGH:     Color.RED,
        Severity.MEDIUM:   Color.YELLOW,
        Severity.LOW:      Color.CYAN,
        Severity.INFO:     Color.DIM,
    }.get(severity, Color.RESET)


def _verdict_color(status: VerdictStatus) -> str:
    """Return color codes for a verdict status."""
    return {
        VerdictStatus.PASS:            Color.GREEN + Color.BOLD,
        VerdictStatus.PASS_WITH_NOTES: Color.CYAN + Color.BOLD,
        VerdictStatus.REVISE:          Color.YELLOW + Color.BOLD,
        VerdictStatus.REJECT:          Color.RED + Color.BOLD,
    }.get(status, Color.RESET)


def print_verdict(
    verdict: Verdict,
    run_dir: Path | None = None,
    verbose: bool = False,
) -> None:
    """
    Print a complete verdict report to stdout.

    Args:
        verdict:  The Verdict object from the aggregator
        run_dir:  Path to the run directory (for reference)
        verbose:  If True, print full evidence for each finding
    """
    report = verdict.report
    print()

    # ── Verdict Banner ─────────────────────────────────────────────────────────
    status_str = verdict.status.value
    verdict_color = _verdict_color(verdict.status)
    banner = f" ◆ QUORUM VERDICT: {status_str} "
    print(_c(banner, verdict_color))
    print(_c("─" * len(banner), Color.DIM))
    print()
    print(f"  {verdict.reasoning}")
    print(f"  Confidence: {verdict.confidence:.0%}")
    print()

    if report is None:
        print(_c("  (no report data)", Color.DIM))
        return

    # ── Issue Summary ──────────────────────────────────────────────────────────
    total = len(report.findings)
    if total == 0:
        print(_c("  ✓ No issues found", Color.GREEN + Color.BOLD))
    else:
        counts = []
        if report.critical_count:
            counts.append(_c(f"{report.critical_count} CRITICAL", Color.RED + Color.BOLD))
        if report.high_count:
            counts.append(_c(f"{report.high_count} HIGH", Color.RED))
        if report.medium_count:
            counts.append(_c(f"{report.medium_count} MEDIUM", Color.YELLOW))
        if report.low_count:
            counts.append(_c(f"{report.low_count} LOW/INFO", Color.CYAN))

        print(f"  Issues: {' · '.join(counts)}  ({total} total)")

    if report.conflicts_resolved:
        print(_c(f"  ({report.conflicts_resolved} duplicate findings merged)", Color.DIM))

    print()

    # ── Findings List ──────────────────────────────────────────────────────────
    if report.findings:
        print(_c("── Findings ─────────────────────────────────────────────────", Color.DIM))
        print()

        # Sort by severity (CRITICAL first)
        severity_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            Severity.INFO: 4,
        }
        sorted_findings = sorted(report.findings, key=lambda f: severity_order.get(f.severity, 9))

        for i, finding in enumerate(sorted_findings, 1):
            _print_finding(i, finding, verbose=verbose)

    # ── Run Directory ──────────────────────────────────────────────────────────
    if run_dir:
        print(_c("── Outputs ──────────────────────────────────────────────────", Color.DIM))
        print()
        print(f"  Run directory: {run_dir}")
        print(f"  Detailed report: {run_dir / 'report.md'}")
        print(f"  Machine-readable: {run_dir / 'verdict.json'}")
        print()


def _print_finding(index: int, finding: Finding, verbose: bool = False) -> None:
    """Print a single finding with evidence."""
    sev_color = _severity_color(finding.severity)
    sev_label = _c(f"[{finding.severity.value:8s}]", sev_color)

    print(f"  {index:2d}. {sev_label} {finding.description}")

    if finding.location:
        print(_c(f"       Location: {finding.location}", Color.DIM))

    if finding.critic_source:
        sources = finding.critic_source.strip(",")
        print(_c(f"       Critic:   {sources}", Color.DIM))

    if finding.rubric_criterion:
        print(_c(f"       Criterion: {finding.rubric_criterion}", Color.DIM))

    if verbose or finding.severity in (Severity.CRITICAL, Severity.HIGH):
        # Always show evidence for CRITICAL/HIGH; show for others only in verbose mode
        evidence_preview = finding.evidence.result.replace("\n", " ").strip()
        if len(evidence_preview) > 120:
            evidence_preview = evidence_preview[:117] + "..."
        print(_c(f"       Evidence [{finding.evidence.tool}]: {evidence_preview}", Color.DIM))

    print()


def print_rubric_list(names: list[str]) -> None:
    """Print available rubric names."""
    print()
    print(_c("Available built-in rubrics:", Color.BOLD))
    for name in names:
        print(f"  • {name}")
    print()


def print_error(message: str) -> None:
    """Print an error message to stderr."""
    print(_c(f"✗ Error: {message}", Color.RED), file=sys.stderr)


def print_warning(message: str) -> None:
    """Print a warning message."""
    print(_c(f"⚠ {message}", Color.YELLOW))

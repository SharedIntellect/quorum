# SPDX-License-Identifier: MIT
# Copyright 2026 SharedIntellect — https://github.com/SharedIntellect/quorum

"""
Pipeline orchestrator — the main Quorum validation flow.

Flow:
1. Load config + rubric
2. Supervisor classifies artifact and runs critics
3. Aggregator synthesizes findings and assigns verdict
4. Write run directory with all outputs (JSON + Markdown report)
5. Return Verdict
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from quorum.agents.aggregator import AggregatorAgent
from quorum.agents.supervisor import SupervisorAgent
from quorum.config import QuorumConfig
from quorum.models import Verdict
from quorum.providers.litellm_provider import LiteLLMProvider
from quorum.rubrics.loader import RubricLoader

logger = logging.getLogger(__name__)

# Output directory for all quorum runs
DEFAULT_RUNS_DIR = Path("quorum-runs")


def run_validation(
    target_path: str | Path,
    depth: str = "quick",
    rubric_name: str | None = None,
    config: QuorumConfig | None = None,
    runs_dir: Path | None = None,
) -> tuple[Verdict, Path]:
    """
    Run a full Quorum validation against a target artifact.

    Args:
        target_path: Path to the artifact file to validate
        depth:       Depth profile: quick | standard | thorough
        rubric_name: Rubric to use (auto-detected from domain if None)
        config:      Pre-loaded QuorumConfig (overrides depth if provided)
        runs_dir:    Where to write the run directory (default: ./quorum-runs/)

    Returns:
        (Verdict, run_directory_path) — the verdict and where outputs were written
    """
    target = Path(target_path)
    if not target.exists():
        raise FileNotFoundError(f"Target artifact not found: {target}")

    # Load config
    if config is None:
        from quorum.config import load_config
        config = load_config(depth=depth)

    # Read artifact
    artifact_text = target.read_text(encoding="utf-8", errors="replace")

    # Load rubric
    loader = RubricLoader()
    rubric = _select_rubric(loader, rubric_name, target, artifact_text, config)

    # Create run directory
    run_dir = _create_run_dir(runs_dir or DEFAULT_RUNS_DIR, target)

    # Save inputs to run dir (for auditability)
    _write_json(run_dir / "run-manifest.json", {
        "target": str(target),
        "depth": config.depth_profile,
        "rubric": rubric.name,
        "critics": config.critics,
        "started_at": datetime.now(timezone.utc).isoformat(),
    })
    (run_dir / "artifact.txt").write_text(artifact_text, encoding="utf-8")
    _write_json(run_dir / "rubric.json", rubric.model_dump())

    # Build provider
    provider = LiteLLMProvider(api_keys=config.api_keys)

    # Run supervisor → critics
    supervisor = SupervisorAgent(provider=provider, config=config)
    critic_results = supervisor.run(
        artifact_text=artifact_text,
        artifact_path=str(target),
        rubric=rubric,
    )

    # Save critic results
    for result in critic_results:
        _write_json(
            run_dir / "critics" / f"{result.critic_name}-findings.json",
            result.model_dump(),
        )

    # Run aggregator → verdict
    aggregator = AggregatorAgent(provider=provider, config=config)
    verdict = aggregator.run(critic_results)

    # Save outputs
    _write_json(run_dir / "verdict.json", verdict.model_dump())
    _write_report(run_dir / "report.md", verdict, target, rubric, config)

    logger.info(
        "Run complete: verdict=%s | %d findings | run_dir=%s",
        verdict.status.value,
        len(verdict.report.findings) if verdict.report else 0,
        run_dir,
    )

    return verdict, run_dir


def _select_rubric(
    loader: RubricLoader,
    rubric_name: str | None,
    target: Path,
    artifact_text: str,
    config: QuorumConfig,
):
    """Select the best rubric for this artifact."""
    from quorum.models import Rubric

    if rubric_name:
        return loader.load(rubric_name)

    # Auto-detect from file extension / content
    ext = target.suffix.lower()
    text_lower = artifact_text.lower()

    if ext in (".yaml", ".yml", ".json"):
        # Likely a config file
        if any(kw in text_lower for kw in ["agent", "model", "workflow", "pipeline"]):
            try:
                return loader.load("agent-config")
            except FileNotFoundError:
                pass

    if ext in (".md", ".txt", ".rst"):
        research_signals = ["abstract", "methodology", "findings", "hypothesis", "study"]
        if sum(1 for s in research_signals if s in text_lower) >= 2:
            try:
                return loader.load("research-synthesis")
            except FileNotFoundError:
                pass

    # Default fallback: use the first built-in rubric available
    builtins = loader.list_builtin()
    if builtins:
        logger.warning(
            "No rubric specified and auto-detection failed. Falling back to: %s",
            builtins[0],
        )
        return loader.load(builtins[0])

    raise RuntimeError(
        "No rubric specified and no built-in rubrics found. "
        "Use --rubric to specify one."
    )


def _create_run_dir(runs_dir: Path, target: Path) -> Path:
    """Create a timestamped run directory."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_name = f"{timestamp}-{target.stem}"
    run_dir = runs_dir / run_name
    (run_dir / "critics").mkdir(parents=True, exist_ok=True)
    return run_dir


def _write_json(path: Path, data: dict) -> None:
    """Write a dict to a JSON file, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def _write_report(
    path: Path,
    verdict,
    target: Path,
    rubric,
    config: QuorumConfig,
) -> None:
    """Write a Markdown validation report."""
    from quorum.models import Severity

    report = verdict.report
    lines = [
        f"# Quorum Validation Report",
        f"",
        f"**Target:** `{target}`  ",
        f"**Rubric:** {rubric.name} v{rubric.version}  ",
        f"**Depth:** {config.depth_profile}  ",
        f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"",
        f"---",
        f"",
        f"## Verdict: {verdict.status.value}",
        f"",
        f"> {verdict.reasoning}",
        f"",
        f"**Confidence:** {verdict.confidence:.0%}",
        f"",
    ]

    if report and report.findings:
        # Group by severity
        for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]:
            group = [f for f in report.findings if f.severity == sev]
            if not group:
                continue
            lines.append(f"## {sev.value} ({len(group)})")
            lines.append("")
            for i, finding in enumerate(group, 1):
                lines.append(f"### {i}. {finding.description[:100]}")
                if finding.location:
                    lines.append(f"**Location:** `{finding.location}`  ")
                lines.append(f"**Critic:** {finding.critic_source}  ")
                if finding.rubric_criterion:
                    lines.append(f"**Criterion:** {finding.rubric_criterion}  ")
                lines.append(f"")
                lines.append(f"**Evidence ({finding.evidence.tool}):**")
                lines.append(f"```")
                lines.append(finding.evidence.result[:500])
                lines.append(f"```")
                lines.append("")
    else:
        lines.append("## Findings")
        lines.append("")
        lines.append("No issues found.")
        lines.append("")

    if report:
        lines += [
            "---",
            "",
            "## Summary",
            "",
            f"| Severity | Count |",
            f"|----------|-------|",
            f"| CRITICAL | {report.critical_count} |",
            f"| HIGH     | {report.high_count} |",
            f"| MEDIUM   | {report.medium_count} |",
            f"| LOW/INFO | {report.low_count} |",
            f"| **Total** | **{len(report.findings)}** |",
            "",
        ]

    path.write_text("\n".join(lines), encoding="utf-8")

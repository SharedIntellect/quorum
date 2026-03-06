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

import glob as glob_mod
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from quorum.agents.aggregator import AggregatorAgent
from quorum.agents.supervisor import SupervisorAgent
from quorum.config import QuorumConfig
from quorum.models import BatchVerdict, FileResult, Verdict, VerdictStatus
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
    relationships_path: Path | None = None,
) -> tuple[Verdict, Path]:
    """
    Run a full Quorum validation against a target artifact.

    Args:
        target_path:        Path to the artifact file to validate
        depth:              Depth profile: quick | standard | thorough
        rubric_name:        Rubric to use (auto-detected from domain if None)
        config:             Pre-loaded QuorumConfig (overrides depth if provided)
        runs_dir:           Where to write the run directory (default: ./quorum-runs/)
        relationships_path: Optional path to quorum-relationships.yaml for Phase 2
                            cross-artifact consistency validation

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
        "prescreen_enabled": config.enable_prescreen,
        "relationships_path": str(relationships_path) if relationships_path else None,
        "started_at": datetime.now(timezone.utc).isoformat(),
    })
    (run_dir / "artifact.txt").write_text(artifact_text, encoding="utf-8")
    _write_json(run_dir / "rubric.json", rubric.model_dump())

    # Build provider
    provider = LiteLLMProvider(api_keys=config.api_keys)

    # Run pre-screen (deterministic checks) if enabled
    prescreen_result = None
    if config.enable_prescreen:
        try:
            from quorum.prescreen import PreScreen
            prescreener = PreScreen()
            prescreen_result = prescreener.run(target, artifact_text)
            _write_json(run_dir / "prescreen.json", prescreen_result.model_dump())
            logger.info(
                "Pre-screen: %d passed, %d failed, %d skipped",
                prescreen_result.passed, prescreen_result.failed, prescreen_result.skipped,
            )
        except Exception as e:
            # V004 fix: pre-screen failure should not kill the entire validation run
            logger.warning("Pre-screen failed, continuing without: %s", e)
            prescreen_result = None

    # Run supervisor → critics
    supervisor = SupervisorAgent(provider=provider, config=config)
    critic_results = supervisor.run(
        artifact_text=artifact_text,
        artifact_path=str(target),
        rubric=rubric,
        prescreen_result=prescreen_result,
    )

    # Save Phase 1 critic results
    for result in critic_results:
        _write_json(
            run_dir / "critics" / f"{result.critic_name}-findings.json",
            result.model_dump(),
        )

    # Phase 2: cross-artifact consistency (runs only when --relationships is provided)
    if relationships_path is not None:
        try:
            from quorum.relationships import load_manifest, resolve_relationships
            from quorum.critics.cross_consistency import CrossConsistencyCritic

            # Manifest paths are relative to the manifest's directory, not the target's
            manifest_base = relationships_path.parent.resolve()
            relationships = load_manifest(relationships_path, base_dir=manifest_base)
            resolved = resolve_relationships(relationships, base_dir=manifest_base)

            # Collect Phase 1 findings (NOT verdicts) as context
            phase1_findings: list = []
            for cr in critic_results:
                if not cr.skipped:
                    phase1_findings.extend(cr.findings)

            cross_critic = CrossConsistencyCritic(provider=provider, config=config)
            cross_result = cross_critic.evaluate(resolved, phase1_findings)

            _write_json(
                run_dir / "critics" / "cross_consistency-findings.json",
                cross_result.model_dump(),
            )
            critic_results.append(cross_result)

            logger.info(
                "Phase 2 complete: %d cross-artifact findings across %d relationships",
                len(cross_result.findings), len(relationships),
            )
        except Exception as e:
            # Let cancellation propagate (CancelledError is BaseException in 3.9+,
            # but check explicitly for older Python compatibility)
            import asyncio
            if isinstance(e, asyncio.CancelledError):
                raise
            logger.error("Phase 2 (cross-artifact) failed: %s", e)
            # Non-fatal: Phase 1 results are still valid and aggregator will proceed

    # Run aggregator → verdict
    # V007 fix: guard aggregator crash so partial results are still saved
    aggregator = AggregatorAgent(provider=provider, config=config)
    try:
        verdict = aggregator.run(critic_results)
    except Exception as e:
        logger.error("Aggregator failed: %s", e)
        # Construct a minimal REJECT verdict so the run still produces output
        verdict = Verdict(
            status=VerdictStatus.REJECT,
            reasoning=f"Aggregator failed: {e}. Critic results were saved individually.",
            confidence=0.0,
            report=None,
        )

    # Save outputs
    _write_json(run_dir / "verdict.json", verdict.model_dump())
    _write_report(run_dir / "report.md", verdict, target, rubric, config)

    # Update manifest with prescreen stats now that we have them
    prescreen_stats: dict = {"prescreen_enabled": config.enable_prescreen}
    if prescreen_result is not None:
        prescreen_stats.update({
            "prescreen_checks": prescreen_result.total_checks,
            "prescreen_passed": prescreen_result.passed,
            "prescreen_failed": prescreen_result.failed,
            "prescreen_skipped": prescreen_result.skipped,
            "prescreen_runtime_ms": prescreen_result.runtime_ms,
            "prescreen_has_failures": prescreen_result.has_failures,
        })
    # Re-write manifest with complete info
    manifest_path = run_dir / "run-manifest.json"
    with open(manifest_path) as f:
        manifest_data = json.load(f)
    manifest_data.update(prescreen_stats)
    manifest_data["completed_at"] = datetime.now(timezone.utc).isoformat()
    manifest_data["verdict"] = verdict.status.value
    manifest_data["total_findings"] = len(verdict.report.findings) if verdict.report else 0
    # Count cross-artifact relationships evaluated (if Phase 2 ran)
    cross_result_list = [cr for cr in critic_results if cr.critic_name == "cross_consistency"]
    if cross_result_list and relationships_path is not None:
        try:
            from quorum.relationships import load_manifest
            rels = load_manifest(relationships_path, base_dir=relationships_path.parent.resolve())
            manifest_data["relationships_count"] = len(rels)
        except Exception:
            pass
    _write_json(manifest_path, manifest_data)

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
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_name = f"{timestamp}-{target.stem}"
    run_dir = runs_dir / run_name
    (run_dir / "critics").mkdir(parents=True, exist_ok=True)
    return run_dir


def _write_json(path: Path, data: dict) -> None:
    """Write a dict to a JSON file, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


# ──────────────────────────────────────────────────────────────────────────────
# Batch / multi-file validation
# ──────────────────────────────────────────────────────────────────────────────

# Extensions we treat as validatable text artifacts
TEXT_EXTENSIONS = {
    ".md", ".txt", ".rst", ".yaml", ".yml", ".json", ".toml",
    ".py", ".ps1", ".sh", ".bat", ".cfg", ".ini", ".conf",
    ".xml", ".html", ".csv", ".tsv", ".tex", ".adoc",
}


def _validate_path(path: Path, boundary: Path | None = None) -> Path:
    """
    Validate and resolve a path, ensuring it doesn't escape the boundary.

    Args:
        path:     Path to validate
        boundary: If set, resolved path must be under this directory.
                  If None, uses the path's own parent (no traversal out of target dir).

    Returns:
        Resolved (absolute) path

    Raises:
        ValueError: If the path escapes the boundary
    """
    resolved = path.resolve()

    if boundary is not None:
        boundary_resolved = boundary.resolve()
        try:
            resolved.relative_to(boundary_resolved)
        except ValueError:
            raise ValueError(
                f"Path escapes allowed boundary: {path} "
                f"(resolves to {resolved}, boundary: {boundary_resolved})"
            )

    return resolved


def resolve_targets(
    target: str | Path,
    pattern: str | None = None,
    boundary: Path | None = None,
) -> list[Path]:
    """
    Resolve a target specification to a list of concrete file paths.

    Supports:
      - Single file path → [file]
      - Directory path → all text files (filtered by --pattern if given)
      - Glob pattern (contains * or ?) → expanded matches

    Args:
        target:   File path, directory path, or glob pattern
        pattern:  Optional glob filter when target is a directory (e.g. "*.md")
        boundary: Optional root boundary — all resolved paths must be under this
                  directory. If None when target is a directory, the target dir
                  itself becomes the boundary. Prevents path traversal via
                  patterns like "../../*".

    Returns:
        Sorted list of resolved file paths

    Raises:
        FileNotFoundError: If target doesn't exist or no files match
        ValueError: If any resolved path escapes the boundary
    """
    target = Path(target)

    # Single file
    if target.is_file():
        if boundary:
            _validate_path(target, boundary)
        return [target.resolve()]

    # Directory
    if target.is_dir():
        # When target is a directory, use it as the boundary unless overridden
        effective_boundary = boundary or target.resolve()

        if pattern:
            # Reject patterns with explicit parent traversal
            if ".." in pattern:
                raise ValueError(
                    f"Pattern contains path traversal: {pattern}"
                )
            files = sorted(target.glob(pattern))
        else:
            files = sorted(
                p for p in target.rglob("*")
                if p.is_file() and p.suffix.lower() in TEXT_EXTENSIONS
            )

        # Validate every resolved file is within boundary
        validated = []
        for f in files:
            if f.is_file():
                _validate_path(f, effective_boundary)
                validated.append(f.resolve())
        return validated

    # Glob pattern (target path contains wildcards)
    target_str = str(target)
    if "*" in target_str or "?" in target_str:
        # V005 fix: reject unbounded recursive globs without a directory anchor
        if "**" in target_str:
            anchor = target_str.split("**")[0]
            if not anchor or anchor == "/" or not Path(anchor).exists():
                raise ValueError(
                    f"Unbounded recursive glob rejected: {target_str}. "
                    "Use a directory-anchored pattern like './docs/**/*.md'"
                )

        # Derive boundary from the non-glob prefix
        parts = Path(target_str.split("*")[0].split("?")[0])
        effective_boundary = boundary or (parts.resolve() if parts.exists() else Path.cwd().resolve())

        matches = sorted(Path(p) for p in glob_mod.glob(target_str, recursive=True))
        validated = []
        for m in matches:
            if m.is_file():
                _validate_path(m, effective_boundary)
                validated.append(m.resolve())
        return validated

    raise FileNotFoundError(f"Target not found: {target}")


def run_batch_validation(
    target: str | Path,
    pattern: str | None = None,
    depth: str = "quick",
    rubric_name: str | None = None,
    config: QuorumConfig | None = None,
    runs_dir: Path | None = None,
    relationships_path: Path | None = None,
) -> tuple[BatchVerdict, Path]:
    """
    Run Quorum validation across multiple files with consolidated results.

    Args:
        target:             File, directory, or glob pattern
        pattern:            Optional glob filter for directories (e.g. "*.md")
        depth:              Depth profile: quick | standard | thorough
        rubric_name:        Rubric to use (auto-detected per file if None)
        config:             Pre-loaded QuorumConfig (overrides depth)
        runs_dir:           Root directory for run outputs
        relationships_path: Optional path to quorum-relationships.yaml for Phase 2

    Returns:
        (BatchVerdict, batch_run_directory) — consolidated verdict and output dir
    """
    files = resolve_targets(target, pattern)

    if not files:
        # Use relative path in error to avoid leaking absolute paths
        display_target = Path(target).name if Path(target).is_absolute() else target
        raise FileNotFoundError(
            f"No validatable files found in: {display_target}"
            + (f" (pattern: {pattern})" if pattern else "")
        )

    # Single file → delegate to standard pipeline, wrap result
    if len(files) == 1:
        verdict, run_dir = run_validation(
            target_path=files[0],
            depth=depth,
            rubric_name=rubric_name,
            config=config,
            runs_dir=runs_dir,
            relationships_path=relationships_path,
        )
        batch = BatchVerdict(
            status=verdict.status,
            file_results=[FileResult(
                file_path=str(files[0]),
                verdict=verdict,
                run_dir=str(run_dir),
            )],
            total_files=1,
            total_findings=len(verdict.report.findings) if verdict.report else 0,
            files_passed=0 if verdict.is_actionable else 1,
            files_failed=1 if verdict.is_actionable else 0,
            confidence=verdict.confidence,
            reasoning=verdict.reasoning,
        )
        return batch, run_dir

    # Multi-file batch
    base_runs_dir = runs_dir or DEFAULT_RUNS_DIR
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    batch_dir = base_runs_dir / f"batch-{timestamp}"
    batch_dir.mkdir(parents=True, exist_ok=True)

    file_results: list[FileResult] = []
    errors: list[dict] = []
    batch_started = datetime.now(timezone.utc).isoformat()

    for i, file_path in enumerate(files, 1):
        logger.info("Validating file %d/%d: %s", i, len(files), file_path)
        try:
            verdict, run_dir = run_validation(
                target_path=file_path,
                depth=depth,
                rubric_name=rubric_name,
                config=config,
                runs_dir=batch_dir / "per-file",
                relationships_path=relationships_path,
            )
            file_results.append(FileResult(
                file_path=str(file_path),
                verdict=verdict,
                run_dir=str(run_dir),
            ))
        except Exception as e:
            logger.error("Failed to validate %s: %s", file_path, e)
            errors.append({"file": str(file_path), "error": str(e)})

    # Compute aggregate verdict
    batch_verdict = _aggregate_batch(file_results, errors)

    # Write batch outputs
    _write_json(batch_dir / "batch-manifest.json", {
        "target": str(target),
        "pattern": pattern,
        "depth": depth,
        "rubric": rubric_name,
        "total_files": len(files),
        "validated": len(file_results),
        "errors": len(errors),
        "started_at": batch_started,
    })

    _write_json(batch_dir / "batch-verdict.json", batch_verdict.model_dump())

    if errors:
        _write_json(batch_dir / "errors.json", errors)

    _write_batch_report(batch_dir / "batch-report.md", batch_verdict, target, errors)

    logger.info(
        "Batch complete: %s | %d/%d files | %d total findings | %s",
        batch_verdict.status.value,
        len(file_results),
        len(files),
        batch_verdict.total_findings,
        batch_dir,
    )

    return batch_verdict, batch_dir


def _aggregate_batch(
    file_results: list[FileResult],
    errors: list[dict],
) -> BatchVerdict:
    """Compute a consolidated batch verdict from per-file results."""
    if not file_results:
        return BatchVerdict(
            status=VerdictStatus.REJECT,
            reasoning="No files were successfully validated.",
            confidence=0.0,
        )

    # Worst-case status wins
    status_priority = {
        VerdictStatus.REJECT: 0,
        VerdictStatus.REVISE: 1,
        VerdictStatus.PASS_WITH_NOTES: 2,
        VerdictStatus.PASS: 3,
    }
    worst_status = min(
        (fr.verdict.status for fr in file_results),
        key=lambda s: status_priority.get(s, 99),
    )

    total_findings = sum(
        len(fr.verdict.report.findings) if fr.verdict.report else 0
        for fr in file_results
    )
    files_passed = sum(1 for fr in file_results if not fr.verdict.is_actionable)
    files_failed = sum(1 for fr in file_results if fr.verdict.is_actionable)
    avg_confidence = sum(fr.verdict.confidence for fr in file_results) / len(file_results)

    # Build reasoning
    parts = [f"{len(file_results)} files validated"]
    if files_passed:
        parts.append(f"{files_passed} passed")
    if files_failed:
        parts.append(f"{files_failed} need work")
    if errors:
        parts.append(f"{len(errors)} failed to process")
    parts.append(f"{total_findings} total findings")
    reasoning = ". ".join(parts) + "."

    return BatchVerdict(
        status=worst_status,
        file_results=file_results,
        total_files=len(file_results) + len(errors),
        total_findings=total_findings,
        files_passed=files_passed,
        files_failed=files_failed,
        confidence=avg_confidence,
        reasoning=reasoning,
    )


def _write_batch_report(
    path: Path,
    batch: BatchVerdict,
    target: str | Path,
    errors: list[dict],
) -> None:
    """Write a consolidated Markdown batch report."""
    from quorum.models import Severity

    lines = [
        "# Quorum Batch Validation Report",
        "",
        f"**Target:** `{target}`  ",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC  ",
        f"**Files:** {batch.total_files}  ",
        "",
        "---",
        "",
        f"## Batch Verdict: {batch.status.value}",
        "",
        f"> {batch.reasoning}",
        "",
        f"**Confidence:** {batch.confidence:.0%}",
        "",
        "## Per-File Summary",
        "",
        "| File | Status | Findings | Confidence |",
        "|------|--------|----------|------------|",
    ]

    for fr in batch.file_results:
        name = Path(fr.file_path).name
        finding_count = len(fr.verdict.report.findings) if fr.verdict.report else 0
        lines.append(
            f"| `{name}` | {fr.verdict.status.value} | {finding_count} | {fr.verdict.confidence:.0%} |"
        )

    if errors:
        lines += [
            "",
            "## Errors",
            "",
        ]
        for err in errors:
            lines.append(f"- `{err['file']}`: {err['error']}")

    lines += [
        "",
        "---",
        "",
        "## Aggregate Findings",
        "",
    ]

    # Collect all findings across files
    all_findings = []
    for fr in batch.file_results:
        if fr.verdict.report:
            for finding in fr.verdict.report.findings:
                all_findings.append((Path(fr.file_path).name, finding))

    if all_findings:
        for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]:
            group = [(name, f) for name, f in all_findings if f.severity == sev]
            if not group:
                continue
            lines.append(f"### {sev.value} ({len(group)})")
            lines.append("")
            for name, finding in group:
                lines.append(f"- **`{name}`**: {finding.description[:120]}")
            lines.append("")
    else:
        lines.append("No issues found across any files.")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


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
    display_target = target.name if target.is_absolute() else target
    lines = [
        f"# Quorum Validation Report",
        f"",
        f"**Target:** `{display_target}`  ",
        f"**Rubric:** {rubric.name} v{rubric.version}  ",
        f"**Depth:** {config.depth_profile}  ",
        f"**Date:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC  ",
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
                # Multi-locus display (cross-artifact findings)
                if finding.loci:
                    for locus in finding.loci:
                        lines.append(
                            f"**Locus [{locus.role}]:** `{locus.file}:{locus.start_line}-{locus.end_line}`  "
                        )
                lines.append(f"**Critic:** {finding.critic}  ")
                if finding.rubric_criterion:
                    lines.append(f"**Criterion:** {finding.rubric_criterion}  ")
                if finding.framework_refs:
                    lines.append(f"**Refs:** {', '.join(finding.framework_refs)}  ")
                lines.append(f"")
                lines.append(f"**Evidence ({finding.evidence.tool}):**")
                lines.append(f"```")
                lines.append(finding.evidence.result[:500])
                lines.append(f"```")
                if finding.remediation:
                    lines.append(f"")
                    lines.append(f"**Suggested fix:** {finding.remediation[:200]}")
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
            f"| LOW      | {report.low_count} |",
            f"| INFO     | {report.info_count} |",
            f"| **Total** | **{len(report.findings)}** |",
            "",
        ]

    path.write_text("\n".join(lines), encoding="utf-8")

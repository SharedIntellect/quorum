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

import asyncio
import glob as glob_mod
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from quorum.agents.aggregator import AggregatorAgent
from quorum.agents.supervisor import SupervisorAgent
from quorum.config import QuorumConfig
from quorum.learning import LearningMemory
from quorum.models import BatchVerdict, CriticResult, FileResult, FixProposal, Severity, Verdict, VerdictStatus
from quorum.providers.litellm_provider import LiteLLMProvider
from quorum.rubrics.loader import RubricLoader

logger = logging.getLogger(__name__)

# Output directory for all quorum runs
DEFAULT_RUNS_DIR = Path("quorum-runs")

# Max concurrent file validations in batch mode
# Keep conservative to avoid API rate limits
MAX_BATCH_WORKERS = 3


def apply_fix_proposals(
    proposals: list[FixProposal],
    artifact_text: str,
) -> tuple[str, list[FixProposal], list[FixProposal]]:
    """
    Apply fix proposals to artifact text via exact string replacement.

    Each proposal is applied in order. If a proposal's original_text is not
    present (possibly already consumed by a prior proposal), it is skipped
    with a warning.

    Args:
        proposals:     List of FixProposal objects to apply
        artifact_text: Current text of the artifact

    Returns:
        (modified_text, applied_proposals, skipped_proposals)
    """
    applied: list[FixProposal] = []
    skipped: list[FixProposal] = []
    current_text = artifact_text

    for proposal in proposals:
        if proposal.original_text and proposal.original_text in current_text:
            current_text = current_text.replace(
                proposal.original_text, proposal.replacement_text, 1
            )
            applied.append(proposal)
            logger.debug(
                "Applied fix for finding '%s': replaced %d chars",
                proposal.finding_id,
                len(proposal.original_text),
            )
        else:
            logger.warning(
                "Fix proposal for finding '%s': original_text not found in "
                "(possibly already-modified) artifact — skipping",
                proposal.finding_id,
            )
            skipped.append(proposal)

    return current_text, applied, skipped


def _revalidate_with_critics(
    modified_text: str,
    blocking_findings: list,
    provider: object,
    config: "QuorumConfig",
    rubric: object,
) -> tuple[list[CriticResult], str, str]:
    """
    Re-run only the critics that produced the original blocking findings.

    Args:
        modified_text:     The artifact text after applying fixes
        blocking_findings: The CRITICAL/HIGH findings from the previous run
        provider:          Shared LLM provider instance
        config:            Quorum config (same instance as main pipeline)
        rubric:            Rubric used in Phase 1

    Returns:
        (new_critic_results, revalidation_verdict, revalidation_delta)
        revalidation_verdict: 'improved' | 'unchanged' | 'regressed'
        revalidation_delta:   Human-readable summary of what changed
    """
    from quorum.agents.supervisor import CRITIC_REGISTRY

    # Identify critics that produced the blocking findings
    blocking_critic_names = {
        f.critic
        for f in blocking_findings
        if f.severity in (Severity.CRITICAL, Severity.HIGH)
    }

    before_count = sum(
        1 for f in blocking_findings
        if f.severity in (Severity.CRITICAL, Severity.HIGH)
    )

    rerun_results: list[CriticResult] = []
    for critic_name in sorted(blocking_critic_names):  # sorted for determinism
        cls = CRITIC_REGISTRY.get(critic_name)
        if cls is None:
            logger.warning(
                "Critic '%s' not in registry, cannot re-run for revalidation",
                critic_name,
            )
            continue
        critic = cls(provider=provider, config=config)
        result = critic.evaluate(artifact_text=modified_text, rubric=rubric)
        rerun_results.append(result)

    after_count = sum(
        1
        for cr in rerun_results
        for f in cr.findings
        if f.severity in (Severity.CRITICAL, Severity.HIGH)
    )

    if after_count < before_count:
        verdict = "improved"
    elif after_count == before_count:
        verdict = "unchanged"
    else:
        verdict = "regressed"

    delta = f"CRITICAL/HIGH findings: {before_count} → {after_count} ({verdict})"

    # Note new findings introduced by the fix (flagged but not fatal)
    if verdict == "regressed":
        new_descriptions = [
            f.description[:80]
            for cr in rerun_results
            for f in cr.findings
            if f.severity in (Severity.CRITICAL, Severity.HIGH)
        ]
        if new_descriptions:
            delta += f"; new/remaining: {new_descriptions[:3]}"

    logger.info("Revalidation: %s — %s", verdict, delta)
    return rerun_results, verdict, delta


def _load_and_save_inputs(
    target: Path,
    config: QuorumConfig,
    rubric_name: str | None,
    runs_dir: Path,
    relationships_path: Path | None,
) -> tuple[str, "RubricLoader", Path]:
    """Load artifact, select rubric, create run directory, save inputs."""
    artifact_text = target.read_text(encoding="utf-8", errors="replace")
    loader = RubricLoader()
    rubric = _select_rubric(loader, rubric_name, target, artifact_text, config)
    run_dir = _create_run_dir(runs_dir or DEFAULT_RUNS_DIR, target)
    # Run manifest (per-file validation metadata — differs from batch-manifest.json)
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
    return artifact_text, rubric, run_dir


def _run_prescreen(
    config: QuorumConfig,
    target: Path,
    artifact_text: str,
    run_dir: Path,
) -> "object | None":
    """Run deterministic pre-screen if enabled. Returns PreScreenResult or None."""
    if not config.enable_prescreen:
        return None
    try:
        from quorum.prescreen import PreScreen
        prescreener = PreScreen()
        result = prescreener.run(target, artifact_text)
        _write_json(run_dir / "prescreen.json", result.model_dump())
        logger.info(
            "Pre-screen: %d passed, %d failed, %d skipped",
            result.passed, result.failed, result.skipped,
        )
        return result
    except Exception as e:
        # V004 fix: pre-screen failure should not kill the entire validation run
        logger.warning("Pre-screen failed, continuing without: %s", e)
        return None


def _run_phase2(
    config: QuorumConfig,
    provider: object,
    critic_results: list,
    relationships_path: Path,
    run_dir: Path,
) -> list:
    """Run Phase 2 cross-artifact consistency if relationships provided."""
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
    return critic_results


def _update_manifest(
    run_dir: Path,
    config: QuorumConfig,
    prescreen_result: object,
    verdict: Verdict,
    critic_results: list,
    relationships_path: Path | None,
    learning_stats: dict | None = None,
) -> None:
    """Update run manifest with final stats."""
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
    if learning_stats:
        manifest_data["learning"] = learning_stats
    _write_json(manifest_path, manifest_data)


def run_validation(
    target_path: str | Path,
    depth: str = "quick",
    rubric_name: str | None = None,
    config: QuorumConfig | None = None,
    runs_dir: Path | None = None,
    relationships_path: Path | None = None,
    enable_learning: bool = True,
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
        enable_learning:    Whether to read/write learning memory (default: True)

    Returns:
        Tuple of (Verdict, run_dir) — the final verdict and the Path to the run output directory
    """
    target = Path(target_path)
    if not target.exists():
        raise FileNotFoundError(f"Target artifact not found: {target}")

    # Load config
    if config is None:
        from quorum.config import load_config
        config = load_config(depth=depth)

    artifact_text, rubric, run_dir = _load_and_save_inputs(
        target, config, rubric_name, runs_dir, relationships_path,
    )

    # Load learning memory and get mandatory context for critics
    learning_memory = None
    mandatory_context: str | None = None
    if enable_learning:
        try:
            learning_memory = LearningMemory()
            mandatory_context = learning_memory.to_critic_context() or None
            if mandatory_context:
                logger.info(
                    "Learning memory: %d mandatory pattern(s) injected into critic prompts",
                    len(learning_memory.get_mandatory()),
                )
        except Exception as e:
            logger.warning("Learning memory load failed (non-fatal): %s", e)

    provider = LiteLLMProvider(api_keys=config.api_keys)
    prescreen_result = _run_prescreen(config, target, artifact_text, run_dir)

    # Run supervisor → critics
    supervisor = SupervisorAgent(provider=provider, config=config)
    critic_results = supervisor.run(
        artifact_text=artifact_text,
        artifact_path=str(target),
        rubric=rubric,
        prescreen_result=prescreen_result,
        mandatory_context=mandatory_context,
    )

    # Save Phase 1 critic results
    for result in critic_results:
        _write_json(
            run_dir / "critics" / f"{result.critic_name}-findings.json",
            result.model_dump(),
        )

    # Phase 1.5: Fix proposals and re-validation loops (if enabled)
    fix_report = None
    if config.max_fix_loops > 0:
        blocking = [
            f for cr in critic_results for f in cr.findings
            if f.severity in (Severity.CRITICAL, Severity.HIGH)
        ]
        if blocking:
            from quorum.agents.fixer import FixerAgent
            fixer = FixerAgent(provider=provider, config=config)
            current_artifact_text = artifact_text
            all_fix_reports: list = []

            for loop_num in range(1, config.max_fix_loops + 1):
                if not blocking:
                    logger.info(
                        "Fix loop %d: no blocking findings remain, stopping early",
                        loop_num,
                    )
                    break

                loop_fix_report = fixer.run(
                    findings=blocking,
                    artifact_text=current_artifact_text,
                    artifact_path=str(target),
                )
                loop_fix_report.loop_number = loop_num

                if not loop_fix_report.proposals:
                    logger.info(
                        "Fix loop %d: fixer produced no proposals, stopping early",
                        loop_num,
                    )
                    loop_fix_report.revalidation_verdict = "unchanged"
                    loop_fix_report.revalidation_delta = "Fixer produced no proposals"
                    _write_json(
                        run_dir / f"fix-proposals-loop-{loop_num}.json",
                        loop_fix_report.model_dump(),
                    )
                    all_fix_reports.append(loop_fix_report)
                    break

                # Apply proposals to the current artifact text
                modified_text, applied, _skipped_apply = apply_fix_proposals(
                    loop_fix_report.proposals, current_artifact_text
                )

                if not applied:
                    logger.info(
                        "Fix loop %d: no proposals could be applied, stopping early",
                        loop_num,
                    )
                    loop_fix_report.revalidation_verdict = "unchanged"
                    loop_fix_report.revalidation_delta = (
                        "No proposals could be applied to artifact"
                    )
                    _write_json(
                        run_dir / f"fix-proposals-loop-{loop_num}.json",
                        loop_fix_report.model_dump(),
                    )
                    all_fix_reports.append(loop_fix_report)
                    break

                current_artifact_text = modified_text

                # Re-run only the critics that produced the blocking findings
                new_critic_results, revalidation_verdict, revalidation_delta = (
                    _revalidate_with_critics(
                        modified_text=current_artifact_text,
                        blocking_findings=blocking,
                        provider=provider,
                        config=config,
                        rubric=rubric,
                    )
                )

                loop_fix_report.revalidation_verdict = revalidation_verdict
                loop_fix_report.revalidation_delta = revalidation_delta

                _write_json(
                    run_dir / f"fix-proposals-loop-{loop_num}.json",
                    loop_fix_report.model_dump(),
                )
                all_fix_reports.append(loop_fix_report)

                logger.info(
                    "Fix loop %d complete: %d/%d proposals applied, verdict=%s",
                    loop_num,
                    len(applied),
                    len(loop_fix_report.proposals),
                    revalidation_verdict,
                )

                # Update blocking findings for the next loop
                blocking = [
                    f for cr in new_critic_results for f in cr.findings
                    if f.severity in (Severity.CRITICAL, Severity.HIGH)
                ]

            # Save fixed artifact only if the text was actually modified
            if current_artifact_text != artifact_text:
                (run_dir / "artifact-fixed.txt").write_text(
                    current_artifact_text, encoding="utf-8"
                )
                logger.info(
                    "Saved fixed artifact to %s/artifact-fixed.txt", run_dir
                )

            if all_fix_reports:
                fix_report = all_fix_reports[-1]
                # Also write fix-proposals.json for backward compatibility
                _write_json(run_dir / "fix-proposals.json", fix_report.model_dump())
                logger.info(
                    "Fixer: %d loop(s) completed, final verdict=%s",
                    len(all_fix_reports),
                    fix_report.revalidation_verdict or "no revalidation",
                )

    # Phase 2: cross-artifact consistency (runs only when --relationships is provided)
    if relationships_path is not None:
        try:
            critic_results = _run_phase2(
                config, provider, critic_results, relationships_path, run_dir,
            )
        except Exception as e:
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
        if isinstance(e, asyncio.CancelledError):
            raise
        logger.error("Aggregator failed: %s", e)
        verdict = Verdict(
            status=VerdictStatus.REJECT,
            reasoning=f"Aggregator failed: {e}. Critic results were saved individually.",
            confidence=0.0,
            report=None,
        )

    # Save outputs and update manifest
    _write_json(run_dir / "verdict.json", verdict.model_dump())
    _write_report(run_dir / "report.md", verdict, target, rubric, config, fix_report=fix_report)

    # Update learning memory with findings from this run
    learning_stats: dict = {}
    if enable_learning and learning_memory is not None:
        try:
            domain = supervisor.classify_domain(artifact_text, str(target))
            all_findings = verdict.report.findings if verdict.report else []
            update_result = learning_memory.update_from_findings(all_findings, domain)
            learning_stats = {
                "new_patterns": update_result.new_patterns,
                "updated_patterns": update_result.updated_patterns,
                "promoted_patterns": update_result.promoted_patterns,
                "total_known": update_result.total_known,
            }
            logger.info(
                "Learning memory: +%d new, %d updated, %d promoted (%d total)",
                update_result.new_patterns, update_result.updated_patterns,
                update_result.promoted_patterns, update_result.total_known,
            )
        except Exception as e:
            logger.warning("Learning memory update failed (non-fatal): %s", e)

    _update_manifest(
        run_dir, config, prescreen_result, verdict, critic_results,
        relationships_path, learning_stats,
    )

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

    if ext == ".py":
        try:
            return loader.load("python-code")
        except FileNotFoundError:
            pass

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
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    except (OSError, UnicodeEncodeError) as e:
        logger.error("Failed to write %s: %s", path, e)
        raise


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

    Returns:
        Resolved (absolute) path

    Raises:
        ValueError: If the path escapes the boundary (path traversal attempt)
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
    # Input validation
    target_str = str(target)
    if "\x00" in target_str:
        raise ValueError("Target path contains null bytes")
    if pattern is not None:
        if "\x00" in pattern:
            raise ValueError("Pattern contains null bytes")
        if ".." in pattern:
            raise ValueError(f"Pattern contains path traversal: {pattern}")
        # Reject patterns with shell-dangerous characters
        if any(c in pattern for c in ["|", ";", "&", "$", "`"]):
            raise ValueError(f"Pattern contains disallowed characters: {pattern}")

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


def _validate_one_file(
    file_path: Path,
    index: int,
    total: int,
    depth: str,
    rubric_name: str | None,
    config: "QuorumConfig | None",
    runs_dir: Path,
    relationships_path: "Path | None",
) -> "FileResult | dict":
    """Validate a single file, returning FileResult or error dict."""
    logger.info("Validating file %d/%d: %s", index, total, file_path)
    try:
        verdict, run_dir = run_validation(
            target_path=file_path,
            depth=depth,
            rubric_name=rubric_name,
            config=config,
            runs_dir=runs_dir,
            relationships_path=relationships_path,
        )
        return FileResult(
            file_path=str(file_path),
            verdict=verdict,
            run_dir=str(run_dir),
        )
    except Exception as e:
        logger.error("Failed to validate %s: %s", file_path, e)
        return {"file": str(file_path), "error": str(e)}


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

    max_workers = min(len(files), MAX_BATCH_WORKERS)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _validate_one_file,
                file_path, i, len(files),
                depth, rubric_name, config,
                batch_dir / "per-file", relationships_path,
            ): file_path
            for i, file_path in enumerate(files, 1)
        }
        for future in as_completed(futures, timeout=3600):  # 1 hour max for entire batch
            result = future.result()
            if isinstance(result, FileResult):
                file_results.append(result)
            else:
                errors.append(result)

    # Compute aggregate verdict
    batch_verdict = _aggregate_batch(file_results, errors)

    # Write batch outputs
    # Batch manifest (multi-file validation metadata — differs from run-manifest.json per-file format)
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
        lines.extend(_format_findings_by_severity([f for _, f in all_findings]))
    else:
        lines.append("No issues found across any files.")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def _format_findings_by_severity(findings) -> list[str]:
    """Format findings grouped by severity into Markdown lines."""
    lines = []
    for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]:
        group = [f for f in findings if f.severity == sev]
        if not group:
            continue
        lines.append(f"## {sev.value} ({len(group)})")
        lines.append("")
        for i, finding in enumerate(group, 1):
            lines.append(f"### {i}. {finding.description[:100]}")
            if finding.location:
                lines.append(f"**Location:** `{finding.location}`  ")
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
            lines.append("")
            lines.append(f"**Evidence ({finding.evidence.tool}):**")
            lines.append("```")
            lines.append(finding.evidence.result[:500])
            lines.append("```")
            if finding.remediation:
                lines.append("")
                lines.append(f"**Suggested fix:** {finding.remediation[:200]}")
            lines.append("")
    return lines


def _write_report(
    path: Path,
    verdict,
    target: Path,
    rubric,
    config: QuorumConfig,
    fix_report=None,
) -> None:
    """Write a Markdown validation report."""

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
        lines.extend(_format_findings_by_severity(report.findings))
    else:
        lines.append("## Findings")
        lines.append("")
        lines.append("No issues found.")
        lines.append("")

    if fix_report and fix_report.proposals:
        n = len(fix_report.proposals)
        m = fix_report.findings_addressed + fix_report.findings_skipped
        lines += [
            "---",
            "",
            "## Fix Proposals",
            "",
            f"The Fixer proposed {n} change{'s' if n != 1 else ''} for {m} CRITICAL/HIGH finding{'s' if m != 1 else ''}:",
            "",
        ]
        for i, proposal in enumerate(fix_report.proposals, 1):
            confidence_pct = int(proposal.confidence * 100)
            lines += [
                f"### {i}. Fix for: {proposal.finding_description[:100]}",
                f"**Confidence:** {confidence_pct}%  ",
                f"**Explanation:** {proposal.explanation}",
                "",
                "```diff",
                f"- {proposal.original_text}",
                f"+ {proposal.replacement_text}",
                "```",
                "",
            ]
        if fix_report.skip_reasons:
            lines += [
                f"**Skipped ({fix_report.findings_skipped}):**",
                "",
            ]
            for reason in fix_report.skip_reasons:
                lines.append(f"- {reason}")
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

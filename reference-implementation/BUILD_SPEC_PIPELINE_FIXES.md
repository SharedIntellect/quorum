# Build Spec: Pipeline.py — Fix All 16 Validation Findings

**Target:** `/Users/akkari/.openclaw/workspace/portfolio/quorum/reference-implementation/quorum/pipeline.py`
**Report:** `quorum-runs/20260306-093204-pipeline/report.md`

Fix all 16 findings. Many are duplicates across critics (same issue flagged by correctness + security + completeness). Group by actual fix needed.

---

## Fix 1: CancelledError propagation consistency (HIGH #1, #2 + MEDIUM #1, #7, #8)

The Phase 2 except block already checks for CancelledError. The aggregator except block does not. Make both consistent.

**Aggregator except block** — add CancelledError check:
```python
    try:
        verdict = aggregator.run(critic_results)
    except Exception as e:
        import asyncio
        if isinstance(e, asyncio.CancelledError):
            raise
        logger.error("Aggregator failed: %s", e)
```

Also, move the `import asyncio` for Phase 2 to the top of the file (it's currently an inline import inside the except block). Add `import asyncio` to the module-level imports.

---

## Fix 2: Input validation in resolve_targets (HIGH #4, #5 + MEDIUM #9)

Add null byte and additional pattern validation at the start of `resolve_targets`:

```python
def resolve_targets(
    target: str | Path,
    pattern: str | None = None,
    boundary: Path | None = None,
) -> list[Path]:
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
    ...
```

Move the existing `..` check from inside the directory branch to this top-level validation (it already exists but only in the dir branch).

---

## Fix 3: _validate_path docstring (HIGH #3)

The function signature `-> Path` and raising `ValueError` is standard Python — raising doesn't contradict the return type. But the docstring's Raises section should be clear. Update it:

```python
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
```

This is already basically what it says. The finding is a false positive on return type analysis. But making the docstring clearer doesn't hurt.

---

## Fix 4: God function — extract sub-functions from run_validation (MEDIUM #2)

Extract these sub-functions from `run_validation`:

```python
def _load_and_save_inputs(
    target: Path, config: QuorumConfig, rubric_name: str | None,
    runs_dir: Path, relationships_path: Path | None,
) -> tuple[str, "Rubric", Path]:
    """Load artifact, select rubric, create run directory, save inputs."""
    artifact_text = target.read_text(encoding="utf-8", errors="replace")
    loader = RubricLoader()
    rubric = _select_rubric(loader, rubric_name, target, artifact_text, config)
    run_dir = _create_run_dir(runs_dir or DEFAULT_RUNS_DIR, target)
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
    config: QuorumConfig, target: Path, artifact_text: str, run_dir: Path,
) -> "PreScreenResult | None":
    """Run deterministic pre-screen if enabled."""
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
        logger.warning("Pre-screen failed, continuing without: %s", e)
        return None


def _run_phase2(
    config: QuorumConfig, provider, critic_results: list,
    relationships_path: Path, run_dir: Path,
) -> list:
    """Run Phase 2 cross-artifact consistency if relationships provided."""
    from quorum.relationships import load_manifest, resolve_relationships
    from quorum.critics.cross_consistency import CrossConsistencyCritic

    manifest_base = relationships_path.parent.resolve()
    relationships = load_manifest(relationships_path, base_dir=manifest_base)
    resolved = resolve_relationships(relationships, base_dir=manifest_base)

    phase1_findings = []
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
    run_dir: Path, config: QuorumConfig, prescreen_result,
    verdict, critic_results: list, relationships_path: Path | None,
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
    cross_result_list = [cr for cr in critic_results if cr.critic_name == "cross_consistency"]
    if cross_result_list and relationships_path is not None:
        try:
            from quorum.relationships import load_manifest
            rels = load_manifest(relationships_path, base_dir=relationships_path.parent.resolve())
            manifest_data["relationships_count"] = len(rels)
        except Exception:
            pass
    _write_json(manifest_path, manifest_data)
```

Then `run_validation` becomes a thin orchestrator calling these sub-functions in order. Keep it readable — about 40-50 lines of orchestration logic.

---

## Fix 5: Docstring accuracy for run_validation (MEDIUM #6)

Update: `(Verdict, run_directory_path)` → `(Verdict, Path)` in the docstring Returns section:

```python
    Returns:
        Tuple of (Verdict, run_dir) — the final verdict and the Path to the run output directory
```

---

## Fix 6: Code duplication — manifest helpers (MEDIUM #4)

The two manifest patterns (run-manifest.json and batch-manifest.json) have different fields so a shared helper would be forced. Instead, add a brief comment noting the intentional difference. The finding is valid but the fix is "documented acceptable duplication" — they serve different purposes.

Add a comment above each:
```python
# Run manifest (per-file validation metadata — differs from batch-manifest.json)
```

---

## Fix 7: Report duplication (MEDIUM #5)

Extract a shared helper for the severity grouping loop used in both `_write_report` and `_write_batch_report`:

```python
def _format_findings_by_severity(findings, include_file_name: bool = False) -> list[str]:
    """Format findings grouped by severity into Markdown lines."""
    from quorum.models import Severity
    lines = []
    items = []
    for f in findings:
        if include_file_name and hasattr(f, '_file_name'):
            items.append(f)
        else:
            items.append(f)
    
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
                    lines.append(f"**Locus [{locus.role}]:** `{locus.file}:{locus.start_line}-{locus.end_line}`  ")
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
```

Then both `_write_report` and `_write_batch_report` use this helper instead of duplicating the loop.

---

## Fix 8: ThreadPoolExecutor timeout (LOW #1)

Add timeout to `as_completed` in both the supervisor and batch validation:

In `pipeline.py` batch loop:
```python
for future in as_completed(futures, timeout=3600):  # 1 hour max for entire batch
```

---

## Fix 9: _write_json error handling (LOW #2)

Add a try/except for encoding/disk errors:

```python
def _write_json(path: Path, data: dict) -> None:
    """Write a dict to a JSON file, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    except (OSError, UnicodeEncodeError) as e:
        logger.error("Failed to write %s: %s", path, e)
        raise
```

---

## Verification

After all fixes:
```bash
cd /Users/akkari/.openclaw/workspace/portfolio/quorum/reference-implementation
python3 -c "from quorum.pipeline import run_validation, run_batch_validation; print('pipeline OK')"
```

## IMPORTANT

- Do NOT change the function signatures of `run_validation` or `run_batch_validation` — they are the public API
- Do NOT change `_write_report` signature beyond adding the existing optional `fix_report` parameter
- Do NOT touch `cli.py`, `config.py`, or any critic files
- The God function refactor must preserve all existing behavior exactly

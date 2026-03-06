# Build Spec: Milestone #8 — Parallel Execution

**Goal:** Make critics run concurrently within a validation run, and files run concurrently within a batch.

**Working directory:** `/Users/akkari/.openclaw/workspace/portfolio/quorum/reference-implementation/`

---

## Part A: Parallel Critic Execution (supervisor.py)

Replace the sequential `for critic in critics` loop with `concurrent.futures.ThreadPoolExecutor`.

Why ThreadPoolExecutor not asyncio: the LiteLLM provider uses synchronous HTTP calls. ThreadPool is the right abstraction for I/O-bound sync code.

### Changes to `quorum/agents/supervisor.py`

1. Add import: `from concurrent.futures import ThreadPoolExecutor, as_completed`

2. Replace the sequential critic loop (the `for critic in critics:` block starting around line 157) with:

```python
def _run_one_critic(
    self,
    critic: BaseCritic,
    artifact_text: str,
    rubric: Rubric,
    merged_context: dict[str, Any] | None,
) -> CriticResult:
    """Run a single critic, returning CriticResult (never raises)."""
    logger.info("Running critic: %s", critic.name)
    try:
        result = critic.evaluate(
            artifact_text=artifact_text,
            rubric=rubric,
            extra_context=merged_context if merged_context else None,
        )
        logger.info(
            "Critic %s: %d findings (confidence=%.2f)",
            critic.name, len(result.findings), result.confidence,
        )
        return result
    except Exception as e:
        logger.error("Critic %s crashed: %s", critic.name, e)
        return CriticResult(
            critic_name=critic.name,
            findings=[],
            confidence=0.0,
            runtime_ms=0,
            skipped=True,
            skip_reason=str(e),
        )
```

3. In `run()`, replace the for loop with:

```python
critics = self.build_critics()
max_workers = min(len(critics), 4)  # Cap at 4 to avoid API rate limits

with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = {
        executor.submit(
            self._run_one_critic, critic, artifact_text, rubric, merged_context
        ): critic
        for critic in critics
    }
    results: list[CriticResult] = []
    for future in as_completed(futures):
        results.append(future.result())

return results
```

Note: `as_completed` returns results in completion order, not submission order. This is fine — the aggregator doesn't care about order. But if we want deterministic ordering for reports, sort by critic name:

```python
results.sort(key=lambda r: r.critic_name)
```

---

## Part B: Parallel Batch Validation (pipeline.py)

Replace the sequential `for i, file_path in enumerate(files, 1):` loop in `run_batch_validation` with ThreadPoolExecutor.

### Changes to `quorum/pipeline.py`

1. Add import: `from concurrent.futures import ThreadPoolExecutor, as_completed`

2. Add a constant for max concurrent file validations:
```python
# Max concurrent file validations in batch mode
# Keep conservative to avoid API rate limits
MAX_BATCH_WORKERS = 3
```

3. Replace the sequential per-file loop in `run_batch_validation` (the `for i, file_path in enumerate(files, 1):` block) with:

```python
def _validate_one_file(
    file_path: Path,
    index: int,
    total: int,
    depth: str,
    rubric_name: str | None,
    config: QuorumConfig | None,
    runs_dir: Path,
    relationships_path: Path | None,
) -> FileResult | dict:
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
```

Make this a module-level function (not a method). Then in `run_batch_validation`:

```python
file_results: list[FileResult] = []
errors: list[dict] = []

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
    for future in as_completed(futures):
        result = future.result()
        if isinstance(result, FileResult):
            file_results.append(result)
        else:
            errors.append(result)
```

---

## Verification

1. `python3 -c "from quorum.agents.supervisor import SupervisorAgent; print('supervisor OK')"`
2. `python3 -c "from quorum.pipeline import run_batch_validation; print('pipeline OK')"`
3. Grep for the old sequential pattern to confirm it's gone:
   - `grep -n "for critic in critics" quorum/agents/supervisor.py` → should return 0 results
   - `grep -n "for i, file_path in enumerate" quorum/pipeline.py` → should return 0 results

# Build Spec: Graduation Run Fix-All

**Goal:** Fix all non-rubric-mismatch findings from the v0.3.0 graduation run (122 of 128 findings — 6 are rubric mismatch, not fixable without a Python code rubric).

**Approach:** Align spec ↔ implementation bidirectionally. Update spec where impl is correct; update impl where spec is correct.

**Working directory:** `/Users/akkari/.openclaw/workspace/portfolio/quorum/reference-implementation` (for code) and `/Users/akkari/.openclaw/workspace/portfolio/quorum/docs` (for spec docs).

---

## FILE 1: `quorum/models.py`

### 1A. Add `id` field to Finding (spec → impl)
The spec says `Finding` has `id: str`. Add it with auto-generation:
```python
import uuid

class Finding(BaseModel):
    id: str = Field(default_factory=lambda: f"F-{uuid.uuid4().hex[:8]}", description="Unique finding identifier")
```
Place it as the FIRST field in Finding.

### 1B. Add `category` field to Finding (spec → impl)
The spec says `Finding` has `category: str`. Add it as optional (backward compat with Phase 1 critics that don't set it):
```python
    category: Optional[str] = Field(default=None, description="Finding category, e.g. 'coverage_gap', 'accuracy_mismatch'")
```
Place it after `severity`.

### 1C. Rename `critic_source` → `critic` (spec → impl)  
The spec uses `critic: str`. Rename `critic_source` to `critic` throughout:
- In `Finding`: `critic: str = Field(default="", description="Name of the critic that produced this finding")`
- **Ripple:** Update `base.py`, `cross_consistency.py`, `aggregator.py`, `pipeline.py` — anywhere that references `critic_source` or `.critic_source`.

### 1D. Add `info_count` property to AggregatedReport
Currently `low_count` lumps LOW+INFO together. Add separate properties AND keep a combined one:
```python
    @property
    def low_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.LOW)

    @property
    def info_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.INFO)

    @property
    def low_info_count(self) -> int:
        """Combined LOW+INFO count for backward-compatible report display."""
        return self.low_count + self.info_count
```

### 1E. Add `contract` field to Relationship model (in relationships.py)
The spec's `schema_contract` type has a `contract` field. Add to `Relationship`:
```python
    contract: Optional[str] = Field(default=None, description="Contract description for schema_contract relationships")
```
And in `load_manifest`, extract it: `contract=entry.get("contract"),`

### 1F. Update CROSS_ARTIFACT_DESIGN.md spec (impl → spec)
Add these clarifications to the spec:
- Add `INFO` to severity enum: `severity: str  # CRITICAL | HIGH | MEDIUM | LOW | INFO`
- Note that `evidence`, `location`, and `rubric_criterion` are implementation extension fields beyond the core spec schema
- Note that `loci` defaults to empty list for Phase 1 findings (>= 1 is enforced only for cross-artifact findings)
- Note that `framework_refs` and `remediation` have sensible defaults for backward compatibility
- Document `compute_hash()` and `compute_hash_from_content()` as utility methods on Locus
- Document truncation behavior (30,000 chars) and its implications
- Document confidence estimation heuristic
- Update `Status:` from "Design complete, not yet implemented" to "Implemented in v0.3.0"

---

## FILE 2: `quorum/pipeline.py`

### 2A. Fix `low_count` display in `_write_report`
The summary table says `LOW/INFO | {report.low_count}`. Update to use `low_info_count`:
```python
f"| LOW/INFO | {report.low_info_count} |",
```
Also add a separate INFO row if info_count > 0:
```python
f"| LOW      | {report.low_count} |",
f"| INFO     | {report.info_count} |",
```
Actually, simplest approach: show LOW and INFO separately in the summary table:
```python
f"| LOW      | {report.low_count} |",
f"| INFO     | {report.info_count} |",
```
And update the iteration to match:
```python
for sev in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO]:
```
This already iterates separately. The only bug is the SUMMARY TABLE at the bottom lumping them. Fix that.

### 2B. Fix timestamp consistency
Replace ALL `datetime.now()` (naive local time) with `datetime.now(timezone.utc)`:
- `_create_run_dir`: change `datetime.now().strftime(...)` → `datetime.now(timezone.utc).strftime(...)`
- `_write_report`: change `datetime.now().strftime(...)` → `datetime.now(timezone.utc).strftime(...)`
- `_write_batch_report`: same
- `run_batch_validation`: `timestamp = datetime.now().strftime(...)` → UTC

### 2C. Remove inline `import json as _json`
The manifest re-read block uses `import json as _json` inside the function. Remove this — `json` is already imported at module level. Change `_json` → `json` in the re-read block. Also change `_mf` → `f` (no need for underscore prefixing).

### 2D. Fix `batch-manifest.json` `started_at` timing
Currently `started_at` is recorded AFTER all validations complete. Capture start time before the loop:
```python
batch_started = datetime.now(timezone.utc).isoformat()
# ... for loop ...
_write_json(batch_dir / "batch-manifest.json", {
    ...
    "started_at": batch_started,
})
```

### 2E. Narrow Phase 2 `except Exception` 
Change:
```python
except Exception as e:
    logger.error("Phase 2 (cross-artifact) failed: %s", e)
```
To:
```python
except (ValueError, FileNotFoundError, RuntimeError, OSError) as e:
    logger.error("Phase 2 (cross-artifact) failed: %s", e)
except Exception as e:
    logger.error("Phase 2 (cross-artifact) failed unexpectedly: %s", e)
    raise  # Don't swallow CancelledError or KeyboardInterrupt
```
Actually, the simplest correct fix: re-raise `BaseException` subclasses:
```python
except Exception as e:
    if isinstance(e, (KeyboardInterrupt, SystemExit)):
        raise
    logger.error("Phase 2 (cross-artifact) failed: %s", e)
```
Wait — `KeyboardInterrupt` and `SystemExit` are `BaseException`, not `Exception`, so they won't be caught. The real issue is `asyncio.CancelledError` which IS an `Exception` subclass in Python < 3.9 but a `BaseException` subclass in 3.9+. For safety:
```python
except Exception as e:
    # Let cancellation propagate (CancelledError is BaseException in 3.9+,
    # but check explicitly for older Python compatibility)
    import asyncio
    if isinstance(e, asyncio.CancelledError):
        raise
    logger.error("Phase 2 (cross-artifact) failed: %s", e)
```

### 2F. Use relative paths in report headers
Change `f"**Target:** `{target}`  "` to use relative path:
```python
display_target = target.name if target.is_absolute() else target
f"**Target:** `{display_target}`  "
```

### 2G. Update `_write_report` summary table
Split LOW and INFO into separate rows:
```python
f"| LOW      | {report.low_count} |",
f"| INFO     | {report.info_count} |",
```

### 2H. Update all `critic_source` references to `critic`
After the rename in models.py (1C), update any references in pipeline.py. Specifically:
- The cross_result_list filter: `cr.critic_name` is fine (that's CriticResult.critic_name, not Finding.critic_source)

---

## FILE 3: `quorum/critics/base.py`

### 3A. Set `skipped=True` on exception path
In `evaluate()`, when an exception occurs, set skipped flag:
```python
except Exception as e:
    logger.error("[%s] Evaluation failed: %s", self.name, e)
    findings = []
    confidence = 0.0
    # Mark as failed so aggregator handles via skip_penalty, not 0.0 confidence average
    runtime_ms = int(time.time() * 1000) - start_ms
    return CriticResult(
        critic_name=self.name,
        findings=findings,
        confidence=confidence,
        runtime_ms=runtime_ms,
        skipped=True,
        skip_reason=f"Evaluation failed: {e}",
    )
```

### 3B. Update `_parse_findings` for `critic` rename
Change `critic_source=self.name` → `critic=self.name` in Finding construction.

### 3C. Pass pre-screen evidence through `extra_context`
The `evaluate()` method already accepts `extra_context` and appends it to the prompt. The issue is that the pipeline doesn't pass it. This is actually a pipeline.py fix — see 2I below.

---

## FILE 4 & 5: `pipeline.py` + `supervisor.py` — Pre-screen injection

**ALREADY DONE.** Pipeline passes `prescreen_result` to `supervisor.run()`, which injects it via `extra_context`. No changes needed here. The graduation findings about missing pre-screen injection were triggered by the prompts falsely claiming Ruff/PSSA — the actual evidence IS being injected.

---

## FILE 6: `quorum/critics/security.py`

### 6A. Fix false claims about Ruff/PSScriptAnalyzer in pre-screen
The system_prompt and build_prompt claim the pre-screen runs "Ruff S* rules, PSScriptAnalyzer security rules." This is FALSE — the pre-screen runs custom regex checks (PS-001 through PS-010). Fix ALL references:

In `system_prompt`:
- Change "deterministic pre-screen (Ruff S*, PSScriptAnalyzer security rules)" → "deterministic pre-screen (PS-001 through PS-010: custom regex checks for paths, credentials, PII, syntax, links, TODOs, whitespace, and empty files)"
- Change "The pre-screen engine ran deterministic regex/SAST checks (Ruff S* rules, PSScriptAnalyzer security rules)" → "The pre-screen engine ran 10 deterministic regex checks (PS-001 through PS-010)"

In `build_prompt`:
- Same corrections to the Pre-Screen Evidence section

### 6B. Fix PASS/FAIL/SKIP terminology mismatch
The prompts say "Checks marked **FAILED**" but pre-screen uses result="FAIL". Fix prompts:
- "Checks marked **FAIL**" (not FAILED)
- "Checks marked **PASS**" (not PASSED)  
- "Checks marked **SKIP**" (not SKIPPED)

### 6C. Add pre-screen check ID legend
In `build_prompt`, after the pre-screen explanation, add:
```
**Pre-screen check ID mapping:**
- PS-001: hardcoded_paths (SAST category: security)
- PS-002: credential_patterns (SAST category: security)
- PS-003: pii_patterns (SAST category: security)
- PS-004: json_validity (SAST category: syntax)
- PS-005: yaml_validity (SAST category: syntax)
- PS-006: python_syntax (SAST category: syntax)
- PS-007: broken_md_links (SAST category: links)
- PS-008: todo_markers (SAST category: structure)
- PS-009: whitespace_issues (SAST category: structure)
- PS-010: empty_file (SAST category: structure)
```

### 6D. Add SEC-12 coverage (Security Logging & Audit)
In `system_prompt` Tier 3, expand SEC-12:
```
- **Security logging completeness** [SEC-12]: Auth events, authorization failures logged;
  log injection prevention (CWE-117); sensitive data in logs (CWE-532); log integrity.
  → Citation: CWE-117, CWE-778, CWE-532, ASVS V16
```

### 6E. Add SEC-14 coverage (Resource Consumption & DoS)
In `system_prompt` Tier 3, expand SEC-14:
```
- **Resource consumption / DoS** [SEC-14]: ReDoS patterns, unbounded data loading,
  missing rate limits, missing timeouts on network calls (requests.get without timeout=),
  zip/decompression bomb detection. → Citation: CWE-400, CWE-1088, ASVS V4.4.*
```

### 6F. Add archive extraction safety to LLM-ONLY list
In the detection capability section, add to LLM-ONLY:
```
  - Archive extraction safety (tarfile/zipfile path traversal, zip bombs) (SEC-08/SEC-14)
```

### 6G. Add `Language` and `Remediation` to citation format
Update the citation format to include:
```
  Language: [Python | PowerShell | Both]
  Remediation: [Specific fix, not generic advice]
```

### 6H. Add explicit `Invoke-Expression` to SEC-01
In Tier 1 or Tier 2, add `Invoke-Expression` / `iex` explicitly (not just in Tier 3 download cradles).

### 6I. Add CISQ ASCSM reference
In the framework grounding section, add:
```
**CISQ ASCSM (ISO/IEC 5055:2021)** — Security-specific CWE mappings
  Additional CWEs for injection coverage: CWE-90 (LDAP), CWE-91 (XPath/XML),
  CWE-611 (XXE), CWE-643 (XPath), CWE-652 (XQuery). CWE-321 (hard-coded crypto key).
```

### 6J. Add SA-11(1) enforcement note
Add to the build_prompt or system_prompt:
```
Note: SA-11(1) compliance requires that SAST pre-screen ran. If pre-screen evidence
is absent, findings should be cited as SA-11(4) (manual review), not SA-11(1).
```

### 6K. Update `critic_source` → `critic`
After rename in models.py.

### 6L. Add positive CERT analog instruction
In the DO NOT section, add a corresponding DO:
```
- DO cite CERT analogies when a direct pattern maps (e.g., "CERT FIO02-C analog")
```

### 6M. Add supply chain note
Add a note acknowledging LLM adds value for supply chain beyond CVE lookup:
```
Note: While SCA tools provide real-time CVE database lookup (which LLM cannot),
LLM semantic analysis detects supply chain patterns like unpinned deps, non-standard
registries, dynamic code loading, and known-dangerous libraries that SCA may miss.
```

---

## FILE 7: `quorum/critics/code_hygiene.py`

### 7A. Fix false claims about Ruff/Pylint/PSScriptAnalyzer
Same as 6A — the system_prompt and build_prompt falsely claim pre-screen runs these tools. Fix:
- "deterministic pre-screen layer (Ruff, Pylint, PSScriptAnalyzer)" → "deterministic pre-screen layer (PS-001 through PS-010: custom regex checks)"
- "Ruff, Pylint, PSScriptAnalyzer rules emit pre-verified PASS/FAIL/SKIP results" → "Custom regex checks (PS-001–PS-010) emit pre-verified PASS/FAIL/SKIP results"

### 7B. Fix PASS/FAIL/SKIP terminology (same as 6B)

### 7C. Add pre-screen check ID legend (same as 6C)

### 7D. Add missing CWEs to categories
Update system_prompt per spec (CODE_HYGIENE_FRAMEWORK.md):

**CAT-01:** Add CWE-390, CWE-394, CWE-595, CWE-597, CWE-703 + supplementary CWE-561, CWE-570, CWE-571
**CAT-02:** Add CWE-248, CWE-252, CWE-392, CWE-394
**CAT-03:** Add CWE-459, CWE-672, CWE-775, CWE-1088, CWE-1091
**CAT-04:** Add CWE-407, CWE-1048, CWE-1080, CWE-1084. Add quantitative thresholds: >20 methods or >2000 lines for God class/function.
**CAT-06:** Add Modifiability to ISO citation. Add commented-out code block detection.
**CAT-07:** Add unsafe type narrowing / isinstance() checks.
**CAT-08:** Add CWE-835, CWE-1088

### 7E. Add delegation severity cap to spec
This is a spec update (CODE_HYGIENE_FRAMEWORK.md), not a code change. Add note that code hygiene assigns LOW/MEDIUM only for security-adjacent patterns.

### 7F. Add AP-02 API key scope check
In AP-02 section, add: "API key scope — Is the API key scoped to minimum permissions? Read from environment variable or secrets manager, not source?"

### 7G. Add AP-06 PowerShell transcript risk
In AP-06 section, add: "PowerShell transcript risk — Does the script log sensitive data that would appear in PowerShell transcripts if enabled?"

### 7H. Update `critic_source` → `critic`

### 7I. Add note about which pre-screen checks cover which categories
In build_prompt, add guidance:
```
**Pre-screen coverage by category:**
- PS-001 (hardcoded_paths) → relates to CAT-11 (Portability) and AP-04 (Credentials)
- PS-002 (credential_patterns) → relates to AP-04 (Credentials) — delegates to SecurityCritic
- PS-003 (pii_patterns) → relates to AP-04 — delegates to SecurityCritic
- PS-006 (python_syntax) → relates to CAT-01 (Correctness)
- PS-007 (broken_md_links) → relates to CAT-06 (Documentation)
- PS-008 (todo_markers) → relates to CAT-06 (Documentation)
```

---

## FILE 8: `quorum/critics/cross_consistency.py`

### 8A. Pass `category` to Finding constructor
In `_parse_findings`, add: `category=f.get("category", "coverage_gap"),`

### 8B. Update `critic_source` → `critic`

---

## FILE 9: `quorum/agents/aggregator.py`

### 9A. Update `critic_source` → `critic`
All references to `f.critic_source` → `f.critic`. Also the comma-delimited merge logic:
- `merged_source = f"{existing.critic},{candidate.critic}"`
- `',' in f.critic`

---

## FILE 10: `quorum/relationships.py`

### 10A. Add `contract` field to Relationship
```python
    contract: Optional[str] = Field(default=None, description="Contract description for schema_contract relationships")
```

### 10B. Extract `contract` in `load_manifest`
Add: `contract=entry.get("contract"),` to the Relationship constructor call.

### 10C. Add `DEFAULT_MANIFEST_NAME`
```python
DEFAULT_MANIFEST_NAME = "quorum-relationships.yaml"
```

---

## FILE 11: `docs/CROSS_ARTIFACT_DESIGN.md`

### 11A. Update status
Change `**Status:** Design complete, not yet implemented` → `**Status:** Implemented in v0.3.0`

### 11B. Add INFO to severity
Change `severity: str  # CRITICAL | HIGH | MEDIUM | LOW` → `severity: str  # CRITICAL | HIGH | MEDIUM | LOW | INFO`

### 11C. Document implementation extensions
Add a section after Decision 3:
```markdown
### Implementation Notes on Finding Model

The implementation extends the spec's Finding model with these additional fields for backward
compatibility with single-file critics:
- `evidence: Evidence` — structured evidence object (tool + result + citation)
- `location: Optional[str]` — human-readable location string
- `rubric_criterion: Optional[str]` — rubric criterion ID

These fields are used by Phase 1 critics. Cross-artifact findings use `loci` for precise
multi-file location tracking and `category` for finding classification.

Default values: `loci` defaults to empty list for Phase 1 findings (>= 1 enforced only
for cross-artifact findings). `framework_refs` and `remediation` have empty defaults for
backward compatibility.
```

### 11D. Document truncation
Add note: "Implementation truncates file content to 30,000 characters (preserving start and end) for LLM context. When truncation occurs, coverage may be partial."

### 11E. Document confidence heuristic
Add note about the confidence estimation approach.

### 11F. Document the pipeline coordination contract
Clarify that `pipeline.py` is responsible for filtering findings from verdicts before passing to Phase 2.

---

## FILE 12: `docs/CODE_HYGIENE_FRAMEWORK.md` (spec update)

### 12A. Add delegation severity cap
Document that code hygiene assigns LOW/MEDIUM only for security-adjacent patterns (this is intentional design).

---

## FILE 13: `docs/SECURITY_CRITIC_FRAMEWORK.md` (spec update)

### 13A. Add SA-11(2) to sub-control mapping
Add `SA-11(2): Dynamic Analysis / Attack Simulation` to the SA-11 mapping since the implementation already references it.

### 13B. Note supply chain LLM value
Update the Detection Capability Matrix to note LLM adds value for supply chain beyond CVE lookup.

---

## VERIFICATION CHECKLIST

After all changes:
1. `cd reference-implementation && python -c "from quorum.models import Finding, Locus, CriticResult; print('models OK')"` 
2. `python -c "from quorum.critics.base import BaseCritic; print('base OK')"`
3. `python -c "from quorum.critics.security import SecurityCritic; print('security OK')"`
4. `python -c "from quorum.critics.code_hygiene import CodeHygieneCritic; print('hygiene OK')"`
5. `python -c "from quorum.critics.cross_consistency import CrossConsistencyCritic; print('cross OK')"`
6. `python -c "from quorum.agents.aggregator import AggregatorAgent; print('aggregator OK')"`
7. `python -c "from quorum.pipeline import run_validation, run_batch_validation; print('pipeline OK')"`
8. `python -c "from quorum.relationships import load_manifest, DEFAULT_MANIFEST_NAME; print('relationships OK')"`
9. `grep -rn "critic_source" quorum/` — should return 0 results (all renamed to `critic`)
10. `grep -rn "Ruff S\*\|PSScriptAnalyzer\|Pylint" quorum/critics/` — should return 0 results in prompt text (only in docstrings if referencing the framework spec as a goal, not as current capability)

## IMPORTANT NOTES FOR BUILDER

- Do NOT modify the `__init__.py` version — it's already 0.3.0
- Do NOT modify `cli.py` — no CLI changes needed
- Do NOT modify rubric files — no rubric changes needed
- Do NOT modify `prescreen.py` — it already works correctly
- The `config.py` already excludes `cross_consistency` from VALID_CRITICS — leave it
- All code changes are in: `models.py`, `pipeline.py`, `base.py`, `supervisor.py`, `security.py`, `code_hygiene.py`, `cross_consistency.py`, `aggregator.py`, `relationships.py`
- All doc changes are in: `CROSS_ARTIFACT_DESIGN.md`, `CODE_HYGIENE_FRAMEWORK.md`, `SECURITY_CRITIC_FRAMEWORK.md`
- Run the verification checklist at the end and report any import errors

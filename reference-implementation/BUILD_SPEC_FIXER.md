# Build Spec: Milestone #5b — Fix Loops (Fixer Agent)

**Goal:** When Quorum finds CRITICAL or HIGH issues, the Fixer proposes concrete patches and the pipeline re-validates to confirm the fix works.

**Working directory:** `/Users/akkari/.openclaw/workspace/portfolio/quorum/reference-implementation/`

---

## Architecture

```
Phase 1: Critics → findings
Phase 1.5 (NEW): If CRITICAL/HIGH findings AND max_fix_loops > 0:
    Fixer proposes patches → apply to copy → re-validate copy → report delta
Phase 2: Cross-artifact (unchanged)
Aggregator: includes fix proposals in final report
```

The Fixer does NOT modify the original artifact. It produces proposed patches that the user can review and apply.

## New Files

### `quorum/agents/fixer.py`

```python
"""
Fixer Agent — Proposes concrete patches for CRITICAL and HIGH findings.

The Fixer:
1. Receives findings from Phase 1 critics
2. Filters to CRITICAL and HIGH only
3. For each finding, proposes a specific code/text change
4. Returns structured FixProposal objects

The Fixer does NOT apply changes — it proposes them for human review.
Fix loops (re-validation after applying proposals) are optional and capped.
"""
```

#### FixProposal Model (add to models.py)

```python
class FixProposal(BaseModel):
    """A proposed fix for a specific finding."""
    finding_id: str = Field(description="ID of the finding this fixes")
    finding_description: str = Field(description="Brief description of the finding")
    file_path: str = Field(description="Path to the file to modify")
    original_text: str = Field(description="Exact text to find and replace")
    replacement_text: str = Field(description="Text to replace it with")
    explanation: str = Field(description="Why this change fixes the issue")
    confidence: float = Field(ge=0.0, le=1.0, description="Fixer's confidence this is correct")


class FixReport(BaseModel):
    """Results from the Fixer agent."""
    proposals: list[FixProposal] = Field(default_factory=list)
    findings_addressed: int = 0
    findings_skipped: int = 0
    skip_reasons: list[str] = Field(default_factory=list)
    loop_number: int = 1
    revalidation_verdict: Optional[str] = Field(default=None, description="Verdict after applying fixes, if re-validation ran")
    revalidation_delta: Optional[str] = Field(default=None, description="Summary of what changed after fix")
```

#### FixerAgent Class

```python
class FixerAgent:
    """Proposes concrete patches for critical findings."""
    
    def __init__(self, provider: BaseProvider, config: QuorumConfig):
        self.provider = provider
        self.config = config
    
    def run(
        self,
        findings: list[Finding],
        artifact_text: str,
        artifact_path: str,
    ) -> FixReport:
        """
        Propose fixes for CRITICAL and HIGH findings.
        
        Uses tier1 model — fix proposals require deep understanding.
        """
```

**LLM Schema for fix proposals:**

```json
{
    "type": "object",
    "required": ["fixes"],
    "properties": {
        "fixes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["finding_id", "original_text", "replacement_text", "explanation", "confidence"],
                "properties": {
                    "finding_id": {"type": "string"},
                    "original_text": {"type": "string", "description": "Exact text from the artifact to replace (must match verbatim)"},
                    "replacement_text": {"type": "string", "description": "The corrected text"},
                    "explanation": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1}
                }
            }
        }
    }
}
```

**System prompt for the Fixer:**

```
You are the Fixer for Quorum, a code quality validation system.

You receive findings (issues) from independent critics along with the full artifact text.
Your job: propose EXACT text replacements that fix each issue.

Rules:
1. original_text MUST appear verbatim in the artifact — if you can't find the exact text, skip the finding
2. replacement_text should be minimal — change only what's needed to fix the issue
3. Do NOT refactor or improve code beyond what the finding requires
4. For each fix, explain WHY the replacement resolves the issue
5. Set confidence: 0.9+ if the fix is straightforward, 0.5-0.8 if the fix might have side effects, <0.5 if you're uncertain
6. Skip findings that require architectural changes, new files, or changes outside the artifact — add to skip_reasons
7. Only address CRITICAL and HIGH findings — ignore MEDIUM/LOW/INFO
```

**User prompt template:**

```
## Artifact ({path})

```
{artifact_text}
```

## Findings to Fix

{findings_formatted}

For each finding, propose an exact text replacement. If a finding cannot be fixed
with a text replacement (requires new files, architectural changes, or external
dependencies), skip it and explain why.
```

### Pipeline Integration

In `pipeline.py` → `run_validation()`, after Phase 1 critic results and BEFORE Phase 2:

```python
# Phase 1.5: Fix proposals (if enabled and blocking findings exist)
fix_report = None
if config.max_fix_loops > 0:
    blocking = [f for cr in critic_results for f in cr.findings
                if f.severity in (Severity.CRITICAL, Severity.HIGH)]
    if blocking:
        from quorum.agents.fixer import FixerAgent
        fixer = FixerAgent(provider=provider, config=config)
        fix_report = fixer.run(
            findings=blocking,
            artifact_text=artifact_text,
            artifact_path=str(target),
        )
        _write_json(run_dir / "fix-proposals.json", fix_report.model_dump())
        logger.info(
            "Fixer: %d proposals for %d findings (%d skipped)",
            len(fix_report.proposals),
            fix_report.findings_addressed,
            fix_report.findings_skipped,
        )
```

### Report Integration

In `_write_report()`, after findings and before summary, if fix_report exists:

```markdown
## Fix Proposals

The Fixer proposed {n} changes for {m} CRITICAL/HIGH findings:

### 1. Fix for: {finding_description}
**Confidence:** {confidence}%
**Explanation:** {explanation}

```diff
- {original_text}
+ {replacement_text}
```
```

Update `_write_report` signature to accept optional `fix_report` parameter.

### Config

`max_fix_loops` already exists in QuorumConfig (default: 0). When > 0, the fixer runs.
For v0.5.0, we implement the proposal step only (loop 1). Re-validation loops (apply → re-run critics → compare) are a future enhancement.

### CLI

No CLI changes needed — the Fixer activates when `max_fix_loops > 0` in the depth config. Users can set it:
- In their config YAML: `max_fix_loops: 1`
- Or we update `thorough.yaml` to set `max_fix_loops: 1` by default

For this build: update `thorough.yaml` to set `max_fix_loops: 1`.

---

## Verification

1. `python3 -c "from quorum.agents.fixer import FixerAgent; print('fixer OK')"`
2. `python3 -c "from quorum.models import FixProposal, FixReport; print('models OK')"`
3. `grep -n "max_fix_loops" quorum/configs/thorough.yaml` — should show 1
4. `grep -n "fix_report" quorum/pipeline.py` — should show Phase 1.5 integration
5. `grep -n "Fix Proposals" quorum/pipeline.py` — should show report section

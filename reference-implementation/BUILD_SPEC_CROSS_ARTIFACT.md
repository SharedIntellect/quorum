# Build Spec: Cross-Artifact Consistency (Milestone #6)

## Overview
Implement cross-artifact consistency validation per `docs/CROSS_ARTIFACT_DESIGN.md`. This adds a Phase 2 pipeline step that evaluates declared relationships between files after single-file critics complete.

## Design Reference
Read `docs/CROSS_ARTIFACT_DESIGN.md` for full architectural context. The three core decisions:
1. Explicit relationship manifest (`quorum-relationships.yaml`)
2. Separate cross-consistency critic (Phase 2, after single-file critics)
3. Multi-locus findings with `Locus` model (role-annotated file references)

**Design Axiom:** "In a judgment system, always trade toward transparency over convenience."

**Critical data flow contract:** The cross-consistency critic receives single-file **findings** (evidence) but NOT single-file **verdicts** (conclusions). This preserves independent judgment.

---

## Files to Modify/Create

### 1. `quorum/models.py` — Add Locus, update Finding

**Add `Locus` model** (insert before the existing `Evidence` class):

```python
import hashlib

class Locus(BaseModel):
    """A specific location in a specific file cited as evidence."""
    file: str = Field(description="Relative path to the file")
    start_line: int = Field(ge=1, description="1-indexed start line")
    end_line: int = Field(ge=1, description="Inclusive end line")
    role: str = Field(description="Role in the relationship, e.g. 'implementation', 'specification', 'producer', 'consumer'")
    source_hash: str = Field(description="SHA-256 hex digest of raw file bytes at [start_line:end_line]")

    @staticmethod
    def compute_hash(file_path: str | Path, start_line: int, end_line: int) -> str:
        """Compute SHA-256 of the raw bytes in the line range [start_line, end_line] (1-indexed, inclusive)."""
        path = Path(file_path)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        # Clamp to actual file length
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)
        segment = "".join(lines[start_idx:end_idx])
        return hashlib.sha256(segment.encode("utf-8")).hexdigest()
```

**Update `Finding`** — add an optional `loci` field. Keep `location` for backward compat:

```python
class Finding(BaseModel):
    severity: Severity
    description: str = Field(description="Clear, actionable description of the issue")
    evidence: Evidence = Field(description="Required: tool-verified evidence for this finding")
    location: Optional[str] = Field(default=None, description="Where in the artifact (single-file findings)")
    loci: list[Locus] = Field(default_factory=list, description="Multi-locus evidence locations (cross-artifact findings)")
    critic_source: str = Field(default="", description="Name of the critic that produced this finding")
    rubric_criterion: Optional[str] = Field(default=None, description="Rubric criterion ID")
    framework_refs: list[str] = Field(default_factory=list, description="Framework references, e.g. ['CWE-683', 'ASVS V8.2.*']")
    remediation: Optional[str] = Field(default=None, description="Suggested fix")
```

**Add `CrossArtifactVerdict`** model:

```python
class CrossArtifactVerdict(BaseModel):
    """Verdict from Phase 2 cross-artifact consistency checks."""
    status: VerdictStatus
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)
    findings: list[Finding] = Field(default_factory=list)
    relationships_evaluated: int = 0
```

### 2. `quorum/relationships.py` — NEW: Manifest loader

Create this file. Responsibilities:
- Load and validate `quorum-relationships.yaml`
- Provide typed relationship objects
- Read file contents for the relationships (so the critic gets the actual text)

```python
"""
Relationship manifest loader for cross-artifact consistency.

Loads quorum-relationships.yaml and provides typed Relationship objects
with resolved file contents for critic evaluation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


# Supported relationship types and their expected role pairs
RELATIONSHIP_TYPES = {
    "implements": {"roles": ("spec", "impl"), "check": "coverage"},
    "documents": {"roles": ("source", "docs"), "check": "accuracy"},
    "delegates": {"roles": ("from", "to"), "check": "boundary"},
    "schema_contract": {"roles": ("producer", "consumer"), "check": "compatibility"},
}


class Relationship(BaseModel):
    """A declared relationship between two artifacts."""
    type: str = Field(description="Relationship type: implements | documents | delegates | schema_contract")
    role_a_name: str = Field(description="Name of the first role (e.g. 'spec', 'source', 'from', 'producer')")
    role_a_path: str = Field(description="Relative path for role A")
    role_b_name: str = Field(description="Name of the second role (e.g. 'impl', 'docs', 'to', 'consumer')")
    role_b_path: str = Field(description="Relative path for role B")
    scope: Optional[str] = Field(default=None, description="Scope qualifier for partial relationships")
    check_type: str = Field(default="", description="What kind of check: coverage | accuracy | boundary | compatibility")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in RELATIONSHIP_TYPES:
            raise ValueError(f"Unknown relationship type: {v}. Valid: {list(RELATIONSHIP_TYPES.keys())}")
        return v


class ResolvedRelationship(BaseModel):
    """A relationship with file contents loaded for critic evaluation."""
    relationship: Relationship
    role_a_content: str = Field(description="Full text of role A file")
    role_b_content: str = Field(description="Full text of role B file")
    role_a_exists: bool = True
    role_b_exists: bool = True


def load_manifest(manifest_path: Path, base_dir: Path | None = None) -> list[Relationship]:
    """
    Load and validate a quorum-relationships.yaml manifest.
    
    Args:
        manifest_path: Path to the YAML manifest
        base_dir: Base directory for resolving relative paths (defaults to manifest's parent)
    
    Returns:
        List of validated Relationship objects
    
    Raises:
        FileNotFoundError: If manifest doesn't exist
        ValueError: If manifest is malformed
    """
    if not manifest_path.exists():
        raise FileNotFoundError(f"Relationship manifest not found: {manifest_path}")
    
    with open(manifest_path) as f:
        data = yaml.safe_load(f)
    
    if not data or "relationships" not in data:
        raise ValueError(f"Manifest must contain a 'relationships' key: {manifest_path}")
    
    raw_rels = data["relationships"]
    if not isinstance(raw_rels, list):
        raise ValueError("'relationships' must be a list")
    
    relationships: list[Relationship] = []
    for i, entry in enumerate(raw_rels):
        rel_type = entry.get("type")
        if not rel_type:
            raise ValueError(f"Relationship #{i} missing 'type'")
        
        if rel_type not in RELATIONSHIP_TYPES:
            raise ValueError(f"Relationship #{i}: unknown type '{rel_type}'. Valid: {list(RELATIONSHIP_TYPES.keys())}")
        
        type_info = RELATIONSHIP_TYPES[rel_type]
        role_a_name, role_b_name = type_info["roles"]
        
        role_a_path = entry.get(role_a_name)
        role_b_path = entry.get(role_b_name)
        
        if not role_a_path:
            raise ValueError(f"Relationship #{i} (type={rel_type}) missing '{role_a_name}' field")
        if not role_b_path:
            raise ValueError(f"Relationship #{i} (type={rel_type}) missing '{role_b_name}' field")
        
        relationships.append(Relationship(
            type=rel_type,
            role_a_name=role_a_name,
            role_a_path=role_a_path,
            role_b_name=role_b_name,
            role_b_path=role_b_path,
            scope=entry.get("scope"),
            check_type=type_info["check"],
        ))
    
    logger.info("Loaded %d relationships from %s", len(relationships), manifest_path)
    return relationships


def resolve_relationships(
    relationships: list[Relationship],
    base_dir: Path,
) -> list[ResolvedRelationship]:
    """
    Resolve relationships by reading file contents.
    
    Files that don't exist get empty content + exists=False flag.
    The critic should report missing files as findings.
    """
    resolved: list[ResolvedRelationship] = []
    
    for rel in relationships:
        path_a = base_dir / rel.role_a_path
        path_b = base_dir / rel.role_b_path
        
        # Validate paths don't escape base_dir
        try:
            path_a.resolve().relative_to(base_dir.resolve())
        except ValueError:
            raise ValueError(f"Path escapes base directory: {rel.role_a_path}")
        try:
            path_b.resolve().relative_to(base_dir.resolve())
        except ValueError:
            raise ValueError(f"Path escapes base directory: {rel.role_b_path}")
        
        content_a = ""
        exists_a = path_a.exists()
        if exists_a:
            content_a = path_a.read_text(encoding="utf-8", errors="replace")
        
        content_b = ""
        exists_b = path_b.exists()
        if exists_b:
            content_b = path_b.read_text(encoding="utf-8", errors="replace")
        
        resolved.append(ResolvedRelationship(
            relationship=rel,
            role_a_content=content_a,
            role_b_content=content_b,
            role_a_exists=exists_a,
            role_b_exists=exists_b,
        ))
    
    return resolved
```

### 3. `quorum/critics/cross_consistency.py` — NEW: The critic

This critic does NOT extend `BaseCritic` (which is designed for single-file evaluation). Instead, it has its own interface since it evaluates relationships, not individual artifacts.

Key behaviors:
- For each resolved relationship, build a focused prompt based on the relationship type
- `implements` → "Does the implementation cover all spec requirements?"
- `documents` → "Does the documentation accurately describe the source's behavior?"
- `delegates` → "Is the delegation complete and non-overlapping?"
- `schema_contract` → "Do the producer's outputs match the consumer's expected inputs?"
- Receives Phase 1 findings as context (NOT verdicts)
- Produces multi-locus findings with role annotations
- Uses tier_2 model (like other critics)

```python
"""
Cross-Artifact Consistency Critic — Phase 2 cross-file relationship validation.

Evaluates declared relationships between artifacts:
- implements: spec coverage verification
- documents: accuracy verification
- delegates: boundary verification  
- schema_contract: structural compatibility verification

Design: docs/CROSS_ARTIFACT_DESIGN.md
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from quorum.config import QuorumConfig
from quorum.models import CriticResult, Evidence, Finding, Locus, Severity
from quorum.providers.base import BaseProvider
from quorum.relationships import ResolvedRelationship

logger = logging.getLogger(__name__)

# Prompt templates per relationship type
RELATIONSHIP_PROMPTS = {
    "implements": """You are evaluating whether an implementation file fully and correctly implements a specification.

SPECIFICATION ({spec_role}: {spec_path}):
```
{spec_content}
```

IMPLEMENTATION ({impl_role}: {impl_path}):
```
{impl_content}
```

{scope_note}

Evaluate:
1. COVERAGE: Are all spec requirements addressed in the implementation?
2. CORRECTNESS: Does the implementation match the spec's intent (not just surface keywords)?
3. GAPS: Are there spec requirements with no corresponding implementation?
4. DRIFT: Are there implementation behaviors not specified (scope creep)?

{phase1_context}
""",

    "documents": """You are evaluating whether documentation accurately describes source code behavior.

SOURCE CODE ({source_role}: {source_path}):
```
{source_content}
```

DOCUMENTATION ({docs_role}: {docs_path}):
```
{docs_content}
```

{scope_note}

Evaluate:
1. ACCURACY: Does the documentation match what the code actually does?
2. COMPLETENESS: Are all public interfaces/behaviors documented?
3. STALENESS: Are there documented features that no longer exist in the code?
4. MISLEADING: Are there descriptions that could lead a reader to incorrect conclusions?

{phase1_context}
""",

    "delegates": """You are evaluating a delegation boundary between two artifacts.

DELEGATING ARTIFACT ({from_role}: {from_path}):
```
{from_content}
```

RECEIVING ARTIFACT ({to_role}: {to_path}):
```
{to_content}
```

Delegation scope: {scope}

Evaluate:
1. COMPLETENESS: Is the delegated scope fully covered by the receiving artifact?
2. OVERLAP: Are there topics handled by both (duplication)?
3. GAPS: Are there topics in the delegation scope handled by neither?
4. BOUNDARY CLARITY: Is it clear from reading either artifact where responsibility lies?

{phase1_context}
""",

    "schema_contract": """You are evaluating a schema contract between a producer and consumer.

PRODUCER ({producer_role}: {producer_path}):
```
{producer_content}
```

CONSUMER ({consumer_role}: {consumer_path}):
```
{consumer_content}
```

Contract: {scope}

Evaluate:
1. STRUCTURAL COMPATIBILITY: Do the producer's output types match the consumer's expected inputs?
2. FIELD COVERAGE: Does the producer populate all fields the consumer requires?
3. OPTIONAL/REQUIRED MISMATCH: Does the consumer treat optional producer fields as required (or vice versa)?
4. TYPE SAFETY: Are there type mismatches (str vs int, Optional vs required, etc.)?

{phase1_context}
""",
}

# JSON schema for cross-consistency findings
CROSS_FINDINGS_SCHEMA = {
    "type": "object",
    "required": ["findings"],
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["severity", "description", "evidence_tool", "evidence_result", "category"],
                "properties": {
                    "severity": {
                        "type": "string",
                        "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"],
                    },
                    "description": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": ["coverage_gap", "accuracy_mismatch", "boundary_violation", "compatibility_issue", "staleness", "drift", "overlap", "missing_file"],
                    },
                    "evidence_tool": {"type": "string"},
                    "evidence_result": {"type": "string"},
                    "role_a_location": {
                        "type": "string",
                        "description": "Line range or section in role A file (e.g. 'lines 42-50' or 'section: Error Handling')",
                    },
                    "role_b_location": {
                        "type": "string",
                        "description": "Line range or section in role B file",
                    },
                    "remediation": {"type": "string"},
                    "framework_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        }
    },
}


SYSTEM_PROMPT = """You are Quorum's Cross-Artifact Consistency Critic.

Your job: evaluate whether declared relationships between files are maintained.
You check for coverage gaps, accuracy mismatches, boundary violations, schema 
incompatibilities, staleness, and drift.

Rules:
1. EVERY finding must have specific evidence — quote the exact text from both files.
2. Reference specific line numbers or section headers where possible.
3. Do not repeat issues already flagged by Phase 1 critics (provided as context).
4. Focus on CROSS-FILE inconsistencies — things a single-file critic cannot catch.
5. If a file doesn't exist, report it as a CRITICAL finding (missing_file category).
6. Be precise about which role (spec vs impl, source vs docs, etc.) has the issue.

Respond with JSON matching the provided schema."""


class CrossConsistencyCritic:
    """
    Phase 2 critic that evaluates declared relationships between artifacts.
    
    Unlike single-file critics (BaseCritic), this critic:
    - Evaluates pairs of files, not individual artifacts
    - Produces multi-locus findings with role annotations
    - Runs after Phase 1 and receives Phase 1 findings as context
    """

    name: str = "cross_consistency"

    def __init__(self, provider: BaseProvider, config: QuorumConfig):
        self.provider = provider
        self.config = config

    def evaluate(
        self,
        resolved_relationships: list[ResolvedRelationship],
        phase1_findings: list[Finding] | None = None,
    ) -> CriticResult:
        """
        Evaluate all resolved relationships.
        
        Args:
            resolved_relationships: Relationships with loaded file contents
            phase1_findings: Findings from Phase 1 (for context, NOT verdicts)
        
        Returns:
            CriticResult with cross-artifact findings
        """
        start_ms = int(time.time() * 1000)
        all_findings: list[Finding] = []

        # Format Phase 1 findings as context
        phase1_context = self._format_phase1_context(phase1_findings or [])

        for resolved in resolved_relationships:
            rel = resolved.relationship

            # Handle missing files
            if not resolved.role_a_exists:
                all_findings.append(Finding(
                    severity=Severity.CRITICAL,
                    description=f"File not found: {rel.role_a_path} (role: {rel.role_a_name} in {rel.type} relationship)",
                    evidence=Evidence(tool="filesystem", result=f"File does not exist: {rel.role_a_path}"),
                    critic_source=self.name,
                    loci=[],  # Can't create locus for missing file
                ))
                continue

            if not resolved.role_b_exists:
                all_findings.append(Finding(
                    severity=Severity.CRITICAL,
                    description=f"File not found: {rel.role_b_path} (role: {rel.role_b_name} in {rel.type} relationship)",
                    evidence=Evidence(tool="filesystem", result=f"File does not exist: {rel.role_b_path}"),
                    critic_source=self.name,
                    loci=[],
                ))
                continue

            # Build and run prompt for this relationship
            try:
                findings = self._evaluate_relationship(resolved, phase1_context)
                all_findings.extend(findings)
            except Exception as e:
                logger.error("Failed to evaluate %s relationship (%s ↔ %s): %s",
                           rel.type, rel.role_a_path, rel.role_b_path, e)
                all_findings.append(Finding(
                    severity=Severity.HIGH,
                    description=f"Cross-consistency evaluation failed for {rel.type}: {rel.role_a_path} ↔ {rel.role_b_path}",
                    evidence=Evidence(tool="error", result=str(e)),
                    critic_source=self.name,
                ))

        runtime_ms = int(time.time() * 1000) - start_ms
        confidence = self._estimate_confidence(all_findings, len(resolved_relationships))

        logger.info(
            "[%s] Done: %d findings across %d relationships in %dms (confidence=%.2f)",
            self.name, len(all_findings), len(resolved_relationships), runtime_ms, confidence,
        )

        return CriticResult(
            critic_name=self.name,
            findings=all_findings,
            confidence=confidence,
            runtime_ms=runtime_ms,
        )

    def _evaluate_relationship(
        self,
        resolved: ResolvedRelationship,
        phase1_context: str,
    ) -> list[Finding]:
        """Evaluate a single relationship via LLM."""
        rel = resolved.relationship
        prompt_template = RELATIONSHIP_PROMPTS.get(rel.type)
        
        if not prompt_template:
            logger.warning("No prompt template for relationship type: %s", rel.type)
            return []

        # Build template variables based on relationship type
        template_vars = {
            "phase1_context": phase1_context,
            "scope_note": f"Scope: {rel.scope}" if rel.scope else "",
            "scope": rel.scope or "(full scope)",
        }

        # Map role names to template variable names
        if rel.type == "implements":
            template_vars.update({
                "spec_role": rel.role_a_name, "spec_path": rel.role_a_path,
                "spec_content": self._truncate(resolved.role_a_content),
                "impl_role": rel.role_b_name, "impl_path": rel.role_b_path,
                "impl_content": self._truncate(resolved.role_b_content),
            })
        elif rel.type == "documents":
            template_vars.update({
                "source_role": rel.role_a_name, "source_path": rel.role_a_path,
                "source_content": self._truncate(resolved.role_a_content),
                "docs_role": rel.role_b_name, "docs_path": rel.role_b_path,
                "docs_content": self._truncate(resolved.role_b_content),
            })
        elif rel.type == "delegates":
            template_vars.update({
                "from_role": rel.role_a_name, "from_path": rel.role_a_path,
                "from_content": self._truncate(resolved.role_a_content),
                "to_role": rel.role_b_name, "to_path": rel.role_b_path,
                "to_content": self._truncate(resolved.role_b_content),
            })
        elif rel.type == "schema_contract":
            template_vars.update({
                "producer_role": rel.role_a_name, "producer_path": rel.role_a_path,
                "producer_content": self._truncate(resolved.role_a_content),
                "consumer_role": rel.role_b_name, "consumer_path": rel.role_b_path,
                "consumer_content": self._truncate(resolved.role_b_content),
            })

        prompt = prompt_template.format(**template_vars)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        raw = self.provider.complete_json(
            messages=messages,
            model=self.config.model_tier2,
            schema=CROSS_FINDINGS_SCHEMA,
            temperature=self.config.temperature,
        )

        return self._parse_findings(raw, resolved)

    def _parse_findings(
        self,
        raw: dict[str, Any],
        resolved: ResolvedRelationship,
    ) -> list[Finding]:
        """Parse LLM findings into Finding objects with multi-locus support."""
        raw_findings = raw.get("findings", [])
        valid: list[Finding] = []
        rel = resolved.relationship

        for i, f in enumerate(raw_findings):
            evidence_result = f.get("evidence_result", "").strip()
            if not evidence_result:
                logger.warning("[%s] Finding #%d rejected: no evidence", self.name, i)
                continue

            # Build loci from location hints
            loci: list[Locus] = []
            # We can't reliably parse line numbers from LLM output, so we create
            # loci with the file reference and role, using line 1 as default.
            # Future enhancement: parse "lines X-Y" from the location strings.
            role_a_loc = f.get("role_a_location", "")
            role_b_loc = f.get("role_b_location", "")

            start_a, end_a = self._parse_line_range(role_a_loc)
            start_b, end_b = self._parse_line_range(role_b_loc)

            if resolved.role_a_exists:
                try:
                    hash_a = Locus.compute_hash(rel.role_a_path, start_a, end_a)
                except Exception:
                    hash_a = ""
                loci.append(Locus(
                    file=rel.role_a_path,
                    start_line=start_a,
                    end_line=end_a,
                    role=rel.role_a_name,
                    source_hash=hash_a,
                ))

            if resolved.role_b_exists:
                try:
                    hash_b = Locus.compute_hash(rel.role_b_path, start_b, end_b)
                except Exception:
                    hash_b = ""
                loci.append(Locus(
                    file=rel.role_b_path,
                    start_line=start_b,
                    end_line=end_b,
                    role=rel.role_b_name,
                    source_hash=hash_b,
                ))

            finding = Finding(
                severity=Severity(f.get("severity", "MEDIUM")),
                description=f.get("description", ""),
                evidence=Evidence(
                    tool=f.get("evidence_tool", "cross-analysis"),
                    result=evidence_result,
                ),
                location=f"{rel.role_a_path} ↔ {rel.role_b_path}",
                loci=loci,
                critic_source=self.name,
                framework_refs=f.get("framework_refs", []),
                remediation=f.get("remediation"),
            )
            valid.append(finding)

        rejected = len(raw_findings) - len(valid)
        if rejected > 0:
            logger.info("[%s] Rejected %d ungrounded findings", self.name, rejected)

        return valid

    @staticmethod
    def _parse_line_range(location_str: str) -> tuple[int, int]:
        """
        Try to extract line numbers from a location string like 'lines 42-50'.
        Returns (start, end) or (1, 1) as fallback.
        """
        import re
        if not location_str:
            return (1, 1)
        
        # Try "lines X-Y" or "line X-Y"
        match = re.search(r'lines?\s+(\d+)\s*[-–]\s*(\d+)', location_str, re.IGNORECASE)
        if match:
            return (int(match.group(1)), int(match.group(2)))
        
        # Try "line X"
        match = re.search(r'line\s+(\d+)', location_str, re.IGNORECASE)
        if match:
            line = int(match.group(1))
            return (line, line)
        
        return (1, 1)

    @staticmethod
    def _truncate(text: str, max_chars: int = 30000) -> str:
        """Truncate content to fit in LLM context, preserving start and end."""
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        return text[:half] + f"\n\n... [{len(text) - max_chars} characters truncated] ...\n\n" + text[-half:]

    def _format_phase1_context(self, findings: list[Finding]) -> str:
        """Format Phase 1 findings as context for the cross-consistency critic."""
        if not findings:
            return "### Phase 1 Context\nNo issues were flagged by single-file critics."

        lines = [
            "### Phase 1 Context (findings from single-file critics — do NOT duplicate these)",
            f"{len(findings)} findings from Phase 1:",
            "",
        ]
        for f in findings:
            lines.append(f"- [{f.severity.value}] {f.description[:120]}")
            if f.location:
                lines.append(f"  Location: {f.location}")
        return "\n".join(lines)

    def _estimate_confidence(self, findings: list[Finding], rel_count: int) -> float:
        """Estimate confidence based on findings and relationship count."""
        if rel_count == 0:
            return 0.0
        if not findings:
            return 0.80  # Clean pass, moderate-high confidence
        grounded = sum(1 for f in findings if f.evidence.result)
        ratio = grounded / len(findings) if findings else 1.0
        return round(0.5 + (ratio * 0.40), 2)
```

### 4. `quorum/config.py` — Add cross_consistency to VALID_CRITICS

Add `"cross_consistency"` to the `VALID_CRITICS` set:
```python
VALID_CRITICS = {
    "correctness",
    "security",
    "completeness",
    "architecture",
    "delegation",
    "style",
    "tester",
    "cross_consistency",
    "code_hygiene",
}
```

Also add `code_hygiene` since it was built but not yet registered.

### 5. `quorum/agents/supervisor.py` — Register new critics

Add imports and registry entries:
```python
from quorum.critics.code_hygiene import CodeHygieneCritic

CRITIC_REGISTRY: dict[str, type[BaseCritic]] = {
    "correctness": CorrectnessCritic,
    "completeness": CompletenessCritic,
    "security": SecurityCritic,
    "code_hygiene": CodeHygieneCritic,
    # cross_consistency is NOT registered here — it runs in Phase 2, not Phase 1
}
```

Note: `cross_consistency` does NOT go in the supervisor registry. It has its own interface and runs in Phase 2 of the pipeline.

### 6. `quorum/pipeline.py` — Add Phase 2 coordination

Add these changes to `run_validation`:

a) Add `relationships_path` parameter to `run_validation` and `run_batch_validation`
b) After Phase 1 (supervisor.run), if relationships are provided:
   - Load and resolve the manifest
   - Collect Phase 1 findings (NOT verdicts) from critic_results
   - Run CrossConsistencyCritic
   - Merge cross-artifact findings into the aggregator input
   - Save cross-consistency results to run_dir

The key flow change:
```
# Phase 1: existing single-file critics (unchanged)
critic_results = supervisor.run(...)

# Phase 2: cross-artifact consistency (NEW)
if relationships_path:
    from quorum.relationships import load_manifest, resolve_relationships
    from quorum.critics.cross_consistency import CrossConsistencyCritic
    
    relationships = load_manifest(relationships_path, base_dir=target.parent)
    resolved = resolve_relationships(relationships, base_dir=target.parent)
    
    # Collect Phase 1 findings (NOT verdicts)
    phase1_findings = []
    for cr in critic_results:
        if not cr.skipped:
            phase1_findings.extend(cr.findings)
    
    cross_critic = CrossConsistencyCritic(provider=provider, config=config)
    cross_result = cross_critic.evaluate(resolved, phase1_findings)
    
    _write_json(run_dir / "critics" / "cross_consistency-findings.json", cross_result.model_dump())
    critic_results.append(cross_result)

# Aggregator receives all results (Phase 1 + Phase 2)
verdict = aggregator.run(critic_results)
```

Update `run_manifest.json` to include `relationships_path` and `relationships_count`.

Also update `run_batch_validation` to accept and pass through `relationships_path`.

### 7. `quorum/cli.py` — Add --relationships flag

Add to the `run_cmd`:
```python
@click.option(
    "--relationships", "-R",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Path to quorum-relationships.yaml manifest for cross-artifact validation",
)
```

Pass it through to `run_validation` / `run_batch_validation`.

### 8. `quorum/output.py` — Render multi-locus findings

Update `_print_finding` to show loci when present:

```python
def _print_finding(index: int, finding: Finding, verbose: bool = False) -> None:
    """Print a single finding with evidence."""
    # ... existing code ...

    # Multi-locus display (cross-artifact findings)
    if finding.loci:
        for locus in finding.loci:
            loc_str = f"{locus.file}:{locus.start_line}-{locus.end_line} (role: {locus.role})"
            print(_c(f"       Locus:    {loc_str}", Color.DIM))

    # Framework refs
    if hasattr(finding, 'framework_refs') and finding.framework_refs:
        print(_c(f"       Refs:     {', '.join(finding.framework_refs)}", Color.DIM))

    # Remediation
    if hasattr(finding, 'remediation') and finding.remediation:
        print(_c(f"       Fix:      {finding.remediation[:100]}", Color.DIM))
    
    # ... rest of existing code ...
```

Also update `_write_report` in pipeline.py to include loci in the markdown report.

### 9. Example manifest

Create `quorum-relationships.example.yaml` at the repo root:

```yaml
# quorum-relationships.yaml — Declare relationships between artifacts for cross-validation
# See docs/CROSS_ARTIFACT_DESIGN.md for schema details

relationships:
  - type: implements
    spec: docs/SPEC.md
    impl: quorum/pipeline.py

  - type: documents
    source: quorum/cli.py
    docs: docs/CONFIG_REFERENCE.md

  - type: delegates
    from: quorum/critics/code_hygiene.py
    to: quorum/critics/security.py
    scope: "Security-adjacent patterns (eval/exec, credentials, prompt injection)"

  - type: schema_contract
    producer: quorum/prescreen.py
    consumer: quorum/critics/security.py
    contract: "PreScreenResult model"
```

---

## Implementation Order
1. `models.py` (Locus + Finding update + CrossArtifactVerdict) — foundation
2. `relationships.py` — manifest loader
3. `critics/cross_consistency.py` — the critic
4. `config.py` — VALID_CRITICS update
5. `supervisor.py` — registry update (code_hygiene)
6. `pipeline.py` — Phase 2 coordination
7. `cli.py` — --relationships flag
8. `output.py` — multi-locus rendering
9. Example manifest

## Testing Notes
- All existing tests must still pass (backward compat)
- `Finding` with empty `loci` must work identically to current behavior
- `Locus.compute_hash` must handle missing files gracefully
- Manifest loader must reject path traversal attempts
- Cross-critic must handle very large files (truncation)

## What NOT to Change
- Existing single-file critic behavior
- Pre-screen pipeline
- Rubric loading
- Aggregator dedup logic (it will naturally handle cross-artifact findings via existing similarity matching)
- Config YAML structure (relationships manifest is a separate file)

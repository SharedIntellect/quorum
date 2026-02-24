# SPDX-License-Identifier: MIT
# Copyright 2026 SharedIntellect — https://github.com/SharedIntellect/quorum

"""
Core data models for Quorum.
All models use Pydantic v2 BaseModel for serialization, validation, and type safety.
"""

from __future__ import annotations

from typing import Any, Optional
from enum import Enum
from pydantic import BaseModel, Field, field_validator


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class VerdictStatus(str, Enum):
    PASS = "PASS"
    PASS_WITH_NOTES = "PASS_WITH_NOTES"
    REVISE = "REVISE"
    REJECT = "REJECT"


class Evidence(BaseModel):
    """Grounded evidence for a finding. Every finding must have this."""
    tool: str = Field(description="Tool used to gather evidence (grep, schema, llm, etc.)")
    result: str = Field(description="Raw output from the tool")
    citation: Optional[str] = Field(
        default=None,
        description="Rubric criterion ID this evidence supports (e.g. 'CRIT-001')"
    )


class Finding(BaseModel):
    """
    A single issue found by a critic.
    Evidence is mandatory — ungrounded claims are rejected by the Aggregator.
    """
    severity: Severity
    description: str = Field(description="Clear, actionable description of the issue")
    evidence: Evidence = Field(description="Required: tool-verified evidence for this finding")
    location: Optional[str] = Field(
        default=None,
        description="Where in the artifact the issue was found (line/section/key)"
    )
    critic_source: str = Field(default="", description="Name of the critic that produced this finding")
    rubric_criterion: Optional[str] = Field(
        default=None,
        description="Rubric criterion ID this finding addresses"
    )


class CriticResult(BaseModel):
    """Output produced by a single critic after evaluating an artifact."""
    critic_name: str
    findings: list[Finding] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, description="Critic's confidence in its assessment (0-1)")
    runtime_ms: int = Field(default=0, description="Wall-clock time the critic took")
    skipped: bool = Field(default=False, description="True if critic was skipped (e.g. not applicable)")
    skip_reason: Optional[str] = None


class AggregatedReport(BaseModel):
    """Synthesized report from all critics."""
    findings: list[Finding] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    conflicts_resolved: int = Field(default=0)
    critic_results: list[CriticResult] = Field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.HIGH)

    @property
    def medium_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.MEDIUM)

    @property
    def low_count(self) -> int:
        return sum(1 for f in self.findings if f.severity in (Severity.LOW, Severity.INFO))


class Verdict(BaseModel):
    """Final verdict on the artifact under review."""
    status: VerdictStatus
    reasoning: str = Field(description="Explanation of the verdict")
    confidence: float = Field(ge=0.0, le=1.0)
    report: Optional[AggregatedReport] = None

    @property
    def is_actionable(self) -> bool:
        """Returns True if the artifact needs rework."""
        return self.status in (VerdictStatus.REVISE, VerdictStatus.REJECT)


class Issue(BaseModel):
    """
    Persistent failure pattern stored in the learning memory (known_issues.json).
    High-frequency patterns automatically promote to mandatory checks.
    """
    pattern_id: str
    description: str
    domain: str
    severity: Severity
    frequency: int = Field(default=1)
    first_seen: str = Field(description="ISO date string")
    last_seen: str = Field(description="ISO date string")
    mandatory: bool = Field(
        default=False,
        description="If True, this pattern is auto-included in all future runs"
    )
    meta_lesson: Optional[str] = Field(
        default=None,
        description="Automation insight extracted from this failure pattern"
    )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class RubricCriterion(BaseModel):
    """A single evaluation criterion in a rubric."""
    id: str
    criterion: str = Field(description="What to evaluate")
    severity: Severity
    evidence_required: str = Field(description="What evidence must be shown to pass/fail this criterion")
    why: str = Field(description="Rationale for this criterion")
    category: Optional[str] = None


class Rubric(BaseModel):
    """Domain-specific validation rubric."""
    name: str
    domain: str
    version: str = "1.0"
    description: Optional[str] = None
    criteria: list[RubricCriterion] = Field(default_factory=list)

    @field_validator("criteria")
    @classmethod
    def criteria_not_empty(cls, v: list[RubricCriterion]) -> list[RubricCriterion]:
        if not v:
            raise ValueError("Rubric must have at least one criterion")
        return v

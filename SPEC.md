# Quorum — Architectural Specification

**Version:** 2.3 (Production)  
**Last Updated:** February 2026  
**Status:** Documented and ready for external implementation  
**Platform:** Designed for [OpenClaw](https://openclaw.ai) agent systems. Cross-platform compatibility with other agent frameworks is under active exploration — see [MODEL_REQUIREMENTS.md](docs/MODEL_REQUIREMENTS.md) for supported models and platforms.

---

## 1. Overview

Quorum is a nine-agent quality assurance system designed to rigorously evaluate multi-agent systems, configurations, research, code, and operational procedures against domain-specific rubrics. It combines:

- **Parallel specialized critics** (9 agents with distinct expertise)
- **Grounded evidence requirement** (every critique must cite tool-verified proof)
- **Intelligent delegation** (Tomasev et al., 2026 principles)
- **Learning memory** (persistent failure-pattern accumulation)
- **Cost-aware depth control** (three execution profiles for different budgets)

Quorum treats validation as infrastructure, not an afterthought.

---

## 2. Design Principles

### 2.1 Multi-Critic Architecture (Reflexion + Council as Judge)

A single model reviewing a long prompt generates:
- Single point of failure (one model's blindspots)
- Hand-waving without evidence (LLMs can justify anything)
- No learning across validations (each run forgets the last)

Quorum uses **nine specialized critics in parallel**, each with deep expertise in:

1. **Correctness Critic** — Factual accuracy, logical consistency, claim support
2. **Security Critic** — Vulnerability patterns, permission issues, injection risks
3. **Completeness Critic** — Coverage gaps, missing requirements, unaddressed edge cases
4. **Architecture Critic** — Design coherence, pattern consistency, scalability concerns
5. **Delegation & Coordination Critic** — Span of control, reversibility, bidirectional contracts
6. **Tester Agent** — Executes validation (schema checks, git queries, web searches, shell execution)
7. **Fixer Agent** — Generates fixes for CRITICAL/HIGH issues (optional, 1-2 loops max)
8. **Aggregator Critic** — Merges findings, resolves conflicts, recalibrates confidence
9. **Supervisor Agent** — Manages workflow, checkpoints, final verdict

Critics don't vote. The Aggregator synthesizes their findings into a final verdict with explicit confidence levels.

### 2.2 Grounded Evidence Requirement

Every issue **must** include tool-verified evidence:
- Excerpt from the artifact being reviewed
- Tool output (git log, schema parse, grep result, web search, shell execution)
- Citation to the rubric criterion it violates

The Aggregator **rejects ungrounded claims**. This single constraint is what separates useful critique from LLM hand-waving.

Example:
```json
{
  "issue": "Missing model assignment in worker agent",
  "severity": "CRITICAL",
  "evidence": {
    "tool": "grep",
    "result": "workers:\n  - name: researcher\n    // NO 'model' field",
    "citation": "Rubric § 2.4: Every agent must have explicit model assignment"
  }
}
```

### 2.3 Intelligent Delegation (Tomasev et al., 2026)

Quorum delegates to critics using five principles from "Towards an Intelligent Assessment Framework for Delegation in AI":

1. **Bidirectional Contracts** — Each critic receives explicit acceptance criteria and resource guarantees
2. **Five-Axis Monitoring Profiles** — Target (process/outcome) × Observability (direct/event) × Control (active/passive) × Frequency × Transparency
3. **Dynamic Re-Delegation** — If a critic fails, the Supervisor can downgrade to a cheaper model or escalate
4. **Trust as Runtime Primitive** — Critics earn trust through demonstrated competence; monitoring intensity scales with trust
5. **Reversibility-Aware Decisions** — Configuration changes (reversible) require less scrutiny than deployment decisions (irreversible)

### 2.4 Learning Memory

After each validation run, the system captures new failure patterns in `known_issues.json`:

```json
{
  "ML-001": {
    "pattern": "Missing bidirectional contract in spawned agent",
    "severity": "CRITICAL",
    "frequency": 12,
    "first_seen": "2026-01-15",
    "last_seen": "2026-02-18",
    "source_runs": ["run-001", "run-047", "run-089"],
    "meta_lesson": "Automation opportunity: validate-contracts.sh for mandatory pre-flight checks"
  }
}
```

High-frequency patterns automatically promote to mandatory checks in future runs.

### 2.5 Cost-Aware Depth Control

Three execution profiles balance rigor, speed, and cost:

| Depth | Critics | Fix Loops | Runtime | Use Case |
|-------|---------|-----------|---------|----------|
| **quick** | Correctness, Security, Completeness | 0 | 5-10 min | Fast feedback; low stakes |
| **standard** | + Architecture, Delegation | ≤1 on CRITICAL | 15-30 min | Most work; default |
| **thorough** | All 9 + external validator | ≤2 on CRITICAL/HIGH | 45-90 min | Critical decisions; production |

---

## 3. Architecture

### 3.1 The Nine Agents

```
Supervisor (Orchestrator)
├─ Correctness Critic (Tier 2)      ├─ Architecture Critic (Tier 2)
├─ Security Critic (Tier 1)         ├─ Delegation Critic (Tier 1)
├─ Completeness Critic (Tier 2)    ├─ Tester (Tier 2, tools: grep, web, exec)
├─ Fixer (Tier 1, optional)        ├─ Aggregator (Tier 1)
└─ Supervisor (Opus, final)
```

Model assignments reflect Tomasev delegation: judgment-heavy roles (Correctness, Security, Aggregator, Supervisor) use your strongest model (Tier 1); execution-heavy roles use a capable but cost-efficient model (Tier 2). For example, Tier 1 might be Claude Opus or GPT-4, and Tier 2 might be Claude Sonnet or GPT-4o-mini.

### 3.2 The Workflow

1. **Intake** — Supervisor receives the artifact (config, research, code) and target rubric
2. **Dispatch** — Supervisor provides each critic with:
   - The artifact excerpt relevant to their domain
   - The rubric criteria they must evaluate
   - Required evidence format
3. **Parallel Execution** — 9 critics run in parallel:
   - Correctness checks semantic accuracy
   - Security searches for vulnerabilities
   - Completeness scans for gaps
   - Architecture evaluates design coherence
   - Delegation assesses span-of-control and contracts
   - Tester executes concrete checks (schema validation, git queries, etc.)
   - Fixer proposes fixes for CRITICAL issues (if depth=standard+)
4. **Aggregation** — Aggregator:
   - Deduplicates issues across critics
   - Resolves conflicts (if critics disagree, escalates to Supervisor)
   - Recalibrates confidence scores
   - Merges fixer suggestions into a coherent recommendation
5. **Verdict** — Supervisor assigns final verdict:
   - **PASS** — No issues or only LOW-severity findings
   - **PASS_WITH_NOTES** — Issues found, all addressable, recommendations provided
   - **REVISE** — HIGH/CRITICAL issues require rework; Supervisor provides guidance
   - **REJECT** — Unfixable architectural problems; restart required
6. **Learning** — System extracts and logs new failure patterns for future runs

### 3.3 File-Based Artifact Passing

All communication between agents uses file-based artifacts, not in-memory variables:

```
run-manifest.json          ← Supervisor's execution plan
artifact.yaml              ← What's being validated
rubric.json                ← Validation criteria
critics/
├── correctness-findings.json
├── security-findings.json
├── completeness-findings.json
├── ...
aggregator-synthesis.json  ← Merged findings
known_issues.json          ← Learning memory (updated)
verdict.json               ← Final result
```

This enforces:
- Determinism (tool output is reproducible)
- Auditability (every change is logged to a file)
- Parallelism (critics don't block each other)
- Safety (no in-memory prompt injection vectors)

---

## 4. Rubric System

Rubrics define what "good" looks like for a specific artifact type. They're JSON documents with:

```json
{
  "name": "Swarm Configuration Rubric",
  "domain": "multi-agent-systems",
  "version": "2.0",
  "criteria": [
    {
      "id": "CRIT-001",
      "criterion": "Every agent has explicit model assignment",
      "severity": "CRITICAL",
      "evidence_required": "grep output showing 'model: ...' in CONFIG",
      "why": "Without model assignment, the system uses defaults unpredictably"
    },
    {
      "id": "CRIT-002",
      "criterion": "Bidirectional contracts exist for all delegations",
      "severity": "CRITICAL",
      "evidence_required": "Schema parse of contract section showing delegator+delegatee commitments",
      "why": "Tomasev delegation principle: both sides must be protected"
    },
    // ... more criteria
  ]
}
```

Rubrics are:
- **Domain-specific** (research synthesis ≠ code review ≠ config audit)
- **Composable** (build custom rubrics by mixing/extending standard ones)
- **Versionable** (rubrics evolve; track changes)
- **Machine-readable** (Supervisor validates rubric itself before use)

---

## 5. The Learning System

`known_issues.json` is Quorum's "experience memory." After each run:

```json
{
  "ML-001": {
    "pattern": "Missing I/O contracts in spawned agent",
    "severity": "CRITICAL",
    "source_papers": ["Tomasev et al. 2026 § 4.3"],
    "frequency": 12,
    "first_seen": "2026-01-15",
    "last_seen": "2026-02-18",
    "source_runs": ["run-001", "run-047"],
    "automation_opportunity": "Pre-flight tool: validate-contracts.sh checks all agent spawns"
  }
}
```

Rules:
- Patterns with frequency ≥ 10 become **mandatory checks** in future validation runs
- Patterns with frequency ≥ 5 trigger **automation opportunities** (design tools to check this deterministically)
- Patterns go stale after 60 days without recurrence (removed from mandatory list)

This is real lifelong learning at the system level.

---

## 6. Trust & Monitoring

Critics earn trust through demonstrated competence:

```
NEW (1st run)
  → PROBATIONARY (2-4 runs, 70%+ accuracy)
    → ESTABLISHED (5-9 runs, 85%+ accuracy)
      → TRUSTED (10+ runs, 95%+ accuracy)
```

Trust level modifies:
- **Monitoring intensity** — NEW critics get tighter scrutiny (more re-validation)
- **Approval thresholds** — TRUSTED critics can auto-approve LOW findings
- **Resource allocation** — ESTABLISHED/TRUSTED critics get higher token budgets

This follows Tomasev's "trust as runtime primitive" principle.

---

## 7. Cost Model

| Component | Cost | Amortization |
|-----------|------|--------------|
| Per-run setup (Supervisor intake) | $0.02 | 1 run |
| 9 critics (parallel, max 30min) | $0.15-0.45 | 1 run |
| Aggregator synthesis | $0.01 | 1 run |
| Tester tools (grep, git, web, exec) | $0.00 | amortized |
| Learning update (`known_issues.json`) | $0.00 | amortized |
| **Total per run (standard depth)** | **~$0.20-0.50** | **1 run** |

Additional runs on related artifacts reuse critic prompts and tools, amortizing costs further.

---

## 8. Implementation Checklist

To implement Quorum from this spec, you need:

- [ ] LLM provider with at least two model tiers (e.g., Claude Opus/Sonnet, GPT-4/GPT-4o-mini, or equivalent)
- [ ] Tool execution environment (shell, git, web search, schema validation)
- [ ] File-based artifact passing (no in-memory state between agents)
- [ ] 9 agent templates (each with unique system prompt per the spec)
- [ ] Rubric system (JSON schema + validator)
- [ ] Learning memory system (persistent `known_issues.json` + pattern aggregation)
- [ ] Aggregator synthesis logic (conflict resolution, confidence recalibration)
- [ ] Verdict assignment logic (PASS/PASS_WITH_NOTES/REVISE/REJECT + reasoning)
- [ ] Depth preset system (quick/standard/thorough configurations)
- [ ] Monitoring/trust system (per-critic accuracy tracking + trust levels)

See IMPLEMENTATION.md for a reference walkthrough.

---

## 9. Theoretical Grounding

Quorum is built on these peer-reviewed papers:

| Paper | Contribution |
|-------|--------------|
| Shinn et al. (2023), Reflexion | Iterative self-critique, learning from failures |
| Vilar et al. (2023), Council as Judge | Multi-critic consensus, conflict resolution |
| Cai et al. (2024), LATM | Tool-making paradigm, deterministic execution |
| Wölflein et al. (2025), ToolMaker | Closed-loop tool generation, autonomous debugging |
| Tomasev et al. (2026), Intelligent AI Delegation | Bidirectional contracts, monitoring profiles, trust primitives |

---

## 10. Known Limitations & Roadmap

### Current Limitations (v2.3)

- Rubric panel is **static** (doesn't specialize per artifact type dynamically)
- **No critic-to-critic debate** (relies on Aggregator to resolve conflicts)
- Learning is **frequency-based** only (no semantic deduplication of patterns yet)
- Domain classifier is **LLM-based** (adding a deterministic pre-screen in v2.4)

### Planned for v3.0

- Dynamic critic specialization (spawn domain-specific critics on-demand)
- Critic debate mode (when two critics conflict, run a structured debate)
- Semantic pattern deduplication (group similar issues under one ML pattern)
- Empirical confidence calibration (long-term tracking of verdict accuracy)

---

## 11. Getting Started

1. Read [IMPLEMENTATION.md](docs/IMPLEMENTATION.md) for a reference walkthrough
2. Review [examples/](examples/) for your use case
3. Adapt rubrics from [reference-rubrics/](reference-rubrics/) or build custom
4. Run the tutorial: `validator run --example basic`

---

**Quorum is production infrastructure, not research.**  
*Built with rigor, validated by independent experts, ready for deployment.*


---

> ⚖️ **LICENSE** — Not part of the operational specification above.
> This file is part of [Quorum](https://github.com/SharedIntellect/quorum).
> Copyright 2026 SharedIntellect. MIT License.
> See [LICENSE](https://github.com/SharedIntellect/quorum/blob/main/LICENSE) for full terms.

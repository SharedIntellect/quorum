# Quorum — Copilot CLI Skill

Multi-critic quality validation for code, configs, and documentation.

## Install

```bash
git clone https://github.com/SharedIntellect/quorum
cp -r quorum/ports/copilot-cli ~/.copilot/skills/quorum
```

## Usage

### Full validation (all critics)
"Run Quorum validation on this file"
"Validate api_handler.py with Quorum"

### Single critic
"Run the security critic on auth.py"
"Check this config for completeness"

### Cross-artifact consistency (future)
"Check if implementation.py matches spec.md"

## What It Checks
- **Correctness** — Logic errors, contradictions, false claims
- **Completeness** — Missing sections, edge cases, broken promises
- **Security** — OWASP ASVS 5.0, CWE Top 25, NIST SA-11, framework-grounded
- **Code Hygiene** — ISO 25010/5055, structural quality beyond linting, agentic code patterns

## Verdict Scale
- **PASS** — No issues found (or only INFO)
- **PASS_WITH_NOTES** — Minor issues only (MEDIUM/LOW)
- **REVISE** — Significant issues requiring rework (any CRITICAL, or 3+ HIGH)
- **REJECT** — Supervisor judgment: artifact fundamentally unsalvageable

## Requirements
- GitHub Copilot CLI with skill support
- Python 3.10+ (for pre-screen script)
- No additional dependencies or API keys

## Skill Structure

```
~/.copilot/skills/quorum/
├── SKILL.md                    # Orchestration (Copilot reads this)
├── quorum-prescreen.py         # Stdlib-only pre-screen script
├── critics/
│   ├── correctness.yaml        # Portable critic definition
│   ├── completeness.yaml       # Portable critic definition
│   ├── security.yaml           # Portable critic definition (14 SEC categories)
│   ├── code_hygiene.yaml       # Portable critic definition (12 CAT + 6 AP categories)
│   ├── correctness.agent.md    # Direct single-critic invocation
│   ├── completeness.agent.md
│   ├── security.agent.md
│   ├── code-hygiene.agent.md
│   └── cross-consistency.agent.md
├── rubrics/
│   ├── python-code.json        # 25 criteria for Python code
│   ├── documentation.json      # 12 criteria for documentation
│   ├── agent-config.json       # Config/YAML criteria
│   └── research-synthesis.json # Research report criteria
├── learning/
│   └── known_issues.json       # Pattern accumulation (grows over time)
└── verdict-rules.yaml          # Deterministic aggregation logic
```

### Portable Critic Definitions (YAML)

The `.yaml` critic files are the core innovation of this port. Each contains:
- **System prompt** — the critic's identity and constraints
- **Evaluation categories** — structured breakdown with framework references
- **Prompt template** — with variable placeholders for orchestrator-agnostic use
- **Output schema** — structured JSON format all critics return
- **Rubric keyword filter** — criteria selection logic
- **Pre-screen integration** — how deterministic checks feed into LLM judgment

These YAMLs are designed as the **single source of truth** consumable by any port (CLI, Claude Code, Copilot). The `.agent.md` files provide a simpler direct-invocation alternative for single-critic use.

## Dispatch Tiers

Sequential dispatch by default (safe for ≤16GB RAM devices). Users opt in to concurrency:

| Tier | Flag | Strategy |
|------|------|----------|
| 💡 Lightweight | default | Sequential (1 agent at a time) |
| ⚡ Standard | `--dispatch standard` | 2 concurrent agents |
| 🚀 Performance | `--dispatch performance` | All agents concurrent |

*Note: Adaptive dispatch is a Copilot port-specific adaptation. The reference implementation uses Python's ThreadPoolExecutor with a fixed worker count.*

## What Changes vs Reference Implementation
- LiteLLM provider → Copilot `task` tool for dispatch
- ThreadPoolExecutor → Copilot parallel `task` calls (opt-in)
- CLI arguments → natural language invocation
- Python class critic definitions → portable YAML definitions
- Config YAML depth profiles → SKILL.md instructions
- Python package → file-based skill (SKILL.md + scripts + rubrics)

## What Stays Identical
- Rubric schema and criteria content
- Finding JSON schema
- Pre-screen check IDs (PS-001 through PS-010)
- Verdict taxonomy (PASS / PASS_WITH_NOTES / REVISE / REJECT)
- Severity levels (CRITICAL / HIGH / MEDIUM / LOW / INFO)
- Evidence grounding requirement
- Critic evaluation logic (extracted verbatim from Python classes)

## Not Yet Ported
- **Tester (L1/L2)** — verification requires filesystem access patterns that differ in Copilot
- **Fixer** — automated remediation; Copilot's edit model differs
- **Batch mode** — Copilot invocations are per-file
- **Cost tracking** — Copilot uses premium requests, not per-token billing
- **Cross-artifact relationship critic** — parameter reserved, not yet implemented

## References
- [Reference Implementation](../../reference-implementation/)
- [Architecture Mapping](ARCHITECTURE.md)

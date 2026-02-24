# Workstream 3: Execution Plan

## ✅ MVP COMPLETE — 2026-02-23

**Shipped in commit 61c7116.** Built by Sonnet sub-agent from this plan, reviewed and fixed by Opus. All HIGH-priority fast-track items completed. See `workstreams/3-reference-implementation/README.md` for build status and test results.

**What shipped:** Phases 0, 1, 2 (partial), 3 (partial), 4 (partial), 6 (partial), 8 (partial) — the "Fast Track" MVP at the bottom of this plan.

**What's deferred:** Parallel dispatch, Security/Architecture/Delegation/Style critics, Tester agent, Fixer agent, Learning memory, Tests, CI. See Phase 2 roadmap.

---

## Overview

Build a working Python reference implementation of Quorum from the published spec. The output is a `reference-implementation/` directory that ships in the repo.

**Estimated effort:** 2-3 focused sessions (MVP completed in 1 session)  
**Dependencies:** None (clean-room build from published spec)  
**Critical path:** Steps marked HIGH must complete before any demo or social push

---

## Phase 0: Scaffolding [HIGH]

### 0.1 — Project structure
Create the Python package layout:

```
reference-implementation/
├── pyproject.toml              # Package config (setuptools/hatch)
├── requirements.txt            # Pinned dependencies
├── README.md                   # Quick start for the implementation
├── quorum/
│   ├── __init__.py
│   ├── __main__.py             # CLI entry: python -m quorum
│   ├── cli.py                  # Click/argparse CLI (quorum run, quorum validate)
│   ├── config.py               # Config loader (YAML → dataclass)
│   ├── models.py               # Data models (Finding, Verdict, Issue, CriticResult)
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py             # Abstract LLM provider interface
│   │   ├── anthropic.py        # Claude provider
│   │   ├── openai.py           # OpenAI provider
│   │   └── litellm.py          # LiteLLM universal provider (optional)
│   ├── critics/
│   │   ├── __init__.py
│   │   ├── base.py             # Abstract critic interface
│   │   ├── correctness.py      # Correctness critic
│   │   ├── security.py         # Security critic
│   │   ├── completeness.py     # Completeness critic
│   │   ├── architecture.py     # Architecture critic
│   │   ├── delegation.py       # Delegation/coordination critic
│   │   ├── style.py            # Style critic
│   │   └── tester.py           # Tester (tool-executing critic)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── supervisor.py       # Domain classification + dispatch
│   │   ├── aggregator.py       # Dedup, cross-validate, confidence, verdict
│   │   └── fixer.py            # Bounded fix loops
│   ├── rubrics/
│   │   ├── __init__.py
│   │   ├── loader.py           # JSON rubric parser + validator
│   │   └── builtin/            # Shipped rubrics
│   │       ├── research-synthesis.json
│   │       ├── agent-config.json
│   │       └── code-review.json
│   ├── memory/
│   │   ├── __init__.py
│   │   └── learning.py         # known_issues.json read/write/promote
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── grep_tool.py        # File/pattern search
│   │   ├── schema_tool.py      # JSON/YAML schema validation
│   │   ├── web_tool.py         # Web search (optional, graceful degrade)
│   │   └── exec_tool.py        # Safe command execution (sandboxed)
│   ├── pipeline.py             # Main orchestration: supervisor → critics → aggregator
│   └── output.py               # Verdict/report formatters (JSON, markdown, terminal)
├── configs/
│   ├── quick.yaml
│   ├── standard.yaml
│   └── thorough.yaml
├── examples/
│   ├── sample-agent-config.yaml    # A deliberately flawed config to validate
│   └── sample-research.md          # A research synthesis with planted issues
└── tests/
    ├── test_rubric_loader.py
    ├── test_models.py
    ├── test_memory.py
    └── test_pipeline_integration.py
```

**Criticality:** HIGH  
**Depends on:** Nothing  
**Output:** Empty but correctly structured Python package that installs

### 0.2 — Data models
Define core data structures in `models.py`:
- `Finding` — severity, description, evidence, location, critic_source
- `CriticResult` — critic_name, findings[], confidence, runtime_ms
- `AggregatedReport` — all findings deduplicated, conflicts resolved, overall confidence
- `Verdict` — PASS / PASS_WITH_NOTES / REVISE / REJECT + reasoning
- `Issue` (for known_issues.json) — pattern_id, description, domain, severity, frequency, first_seen, last_seen, mandatory, meta_lesson

**Criticality:** HIGH  
**Depends on:** 0.1  
**Output:** Importable data models with JSON serialization

### 0.3 — Config system
Build `config.py`:
- Load YAML depth profile configs
- Validate required fields (critics list, model tiers, fix loop limits)
- Merge CLI overrides with file config
- Dataclass-based for type safety

**Criticality:** HIGH  
**Depends on:** 0.2  
**Output:** `QuorumConfig` dataclass that drives the pipeline

---

## Phase 1: Provider Abstraction [HIGH]

### 1.1 — Base provider interface
Abstract class in `providers/base.py`:
- `complete(messages, model, temperature, max_tokens) → str`
- `complete_json(messages, model, schema) → dict` (structured output)
- Provider-specific auth from env vars or config

### 1.2 — Anthropic provider
Claude implementation. Uses `anthropic` Python SDK.

### 1.3 — OpenAI provider
GPT implementation. Uses `openai` Python SDK.

### 1.4 — LiteLLM provider (MODERATE priority)
Universal fallback via `litellm`. Covers 100+ models with one interface. Makes Quorum truly model-agnostic with minimal effort.

**Criticality:** HIGH (1.1-1.3), MODERATE (1.4)  
**Depends on:** 0.3  
**Output:** Working LLM calls with provider switching via config

---

## Phase 2: Critics [HIGH]

### 2.1 — Base critic interface
Abstract class in `critics/base.py`:
- `evaluate(artifact, rubric, config, known_issues) → CriticResult`
- Evidence requirement enforced at base class level — findings without evidence are rejected
- File-based output (each critic writes to `{run_dir}/{critic_name}.json`)

### 2.2 — Correctness critic
First critic to build. Evaluates factual accuracy, logical consistency, internal contradictions.
- Uses rubric criteria with `evidence_type` to determine verification approach
- Calls tools (grep, schema validation) to gather evidence
- Returns structured findings

### 2.3 — Security critic
Evaluates injection risks, unescaped variables, permission issues, credential exposure.
- Pattern-based grep for common vulnerabilities
- Evidence: specific line numbers, matched patterns

### 2.4 — Completeness critic
Evaluates coverage against requirements, missing sections, gaps in specification.

### 2.5 — Architecture critic
Evaluates structural soundness, separation of concerns, coupling, scalability issues.

### 2.6 — Delegation critic
Evaluates Tomasev delegation principles: bidirectional contracts, span-of-control, cognitive friction, accountability.

### 2.7 — Style critic
Evaluates consistency, naming conventions, documentation quality, formatting.

### 2.8 — Tester agent
The tool-executing critic. Runs actual commands (grep, schema parse, git checks) and reports results. Unlike other critics, Tester doesn't opine — it executes and reports facts.

**Criticality:** HIGH (2.1-2.3), MODERATE (2.4-2.8)  
**Depends on:** 1.1, 0.2  
**Output:** Working critics that produce evidence-grounded findings  
**Note:** Build 2.1-2.3 first. A 3-critic quick profile is a viable MVP.

---

## Phase 3: Tools [HIGH]

### 3.1 — Grep tool
File and pattern search. Used by critics to find evidence.
- `grep(pattern, path, context_lines) → list[Match]`

### 3.2 — Schema validation tool
JSON/YAML structure validation.
- `validate_schema(file_path, schema) → list[Violation]`

### 3.3 — Safe exec tool
Sandboxed command execution for Tester agent.
- Timeout enforcement
- Output capture
- No shell expansion (prevent injection)
- Allowlist of permitted commands

### 3.4 — Web search tool (MODERATE)
Optional web search for fact-checking.
- Graceful degradation if no API key configured
- Used by Correctness critic for claim verification

**Criticality:** HIGH (3.1-3.3), MODERATE (3.4)  
**Depends on:** Nothing (standalone utilities)  
**Output:** Deterministic tools that critics call for evidence gathering

---

## Phase 4: Orchestration [HIGH]

### 4.1 — Supervisor agent
Domain classification + critic dispatch.
- Reads artifact, classifies domain (code/config/research/docs/ops)
- Selects critic panel based on depth profile
- Dispatches to critics (parallel via asyncio or ThreadPoolExecutor)

### 4.2 — Aggregator agent
The synthesis brain.
- Collects all CriticResults
- Deduplicates findings by location + description (fuzzy match)
- Cross-validates conflicts (if Security says FAIL and Correctness says PASS on same item)
- Calculates confidence from inter-critic agreement
- Produces final Verdict

### 4.3 — Fixer agent (MODERATE)
Bounded fix loops.
- Takes CRITICAL/HIGH findings
- Proposes concrete fixes
- Re-validates (max 2 loops)
- Escalates to REVISE if unresolvable

### 4.4 — Pipeline orchestrator
`pipeline.py` — the main flow:
1. Load config + rubric
2. Supervisor classifies artifact
3. Dispatch critics (parallel)
4. Collect results
5. Aggregator synthesizes
6. (Optional) Fixer loop
7. Update learning memory
8. Output verdict + report

**Criticality:** HIGH (4.1, 4.2, 4.4), MODERATE (4.3)  
**Depends on:** Phase 2, Phase 3  
**Output:** Complete validation pipeline, end to end

---

## Phase 5: Learning Memory [MODERATE]

### 5.1 — Known issues store
`memory/learning.py`:
- Load/save `known_issues.json`
- Add new patterns from validation runs
- Frequency tracking + auto-promotion (≥3 occurrences → mandatory)
- Dedup by description similarity (simple string matching for v1)

### 5.2 — Memory integration
- Critics receive known_issues at evaluation time
- Aggregator appends new patterns post-validation
- Pipeline reads/writes memory between runs

**Criticality:** MODERATE  
**Depends on:** 4.4  
**Output:** Persistent learning across validation runs

---

## Phase 6: CLI & Output [HIGH]

### 6.1 — CLI interface
`cli.py` using Click or argparse:
```bash
quorum run --target <file> --depth quick|standard|thorough --rubric <name>
quorum validate --target <file>  # alias for run with standard depth
quorum rubrics list               # show available rubrics
quorum memory show                # display known_issues summary
```

### 6.2 — Output formatters
- **Terminal:** Colored summary with verdict, issue counts, confidence
- **JSON:** `verdict.json` — machine-readable full output
- **Markdown:** `report.md` — human-readable detailed report

### 6.3 — Quick start README
`reference-implementation/README.md`:
- Install instructions (pip install)
- API key configuration
- First run walkthrough
- Example output

**Criticality:** HIGH (6.1, 6.3), MODERATE (6.2)  
**Depends on:** 4.4  
**Output:** Usable CLI tool with clear getting-started docs

---

## Phase 7: Testing & Quality [MODERATE]

### 7.1 — Unit tests
- Rubric loader
- Data models serialization
- Memory read/write/promote
- Config validation

### 7.2 — Integration test
- Run full pipeline against `examples/sample-agent-config.yaml`
- Assert: verdict is produced, findings have evidence, no crashes

### 7.3 — CI setup
- GitHub Actions workflow
- Lint (ruff)
- Type check (mypy)
- Tests (pytest)

**Criticality:** MODERATE  
**Depends on:** Phase 6  
**Output:** CI badge on repo, confidence in code quality

---

## Phase 8: Ship [HIGH]

### 8.1 — Final review
- Run Quorum against itself (meta-validation)
- Sensitive term scan (no internal references)
- README accuracy check

### 8.2 — Populate repo
- Copy `reference-implementation/` into the published repo
- Update root README Quick Start to point to real code
- Commit + push

### 8.3 — Announce
- Update sharedintellect.com (add "now with working code" or similar)
- Post update on X threads
- Optional: new HN comment on existing submission

**Criticality:** HIGH  
**Depends on:** Phase 7  
**Output:** Public repo with working, tested code

---

## Fast Track (MVP)

For a minimum viable demo, build only the HIGH items from:
- Phase 0 (scaffolding, models, config)
- Phase 1 (provider abstraction, 1 provider)
- Phase 2 (base critic + correctness + security = 2 working critics)
- Phase 3 (grep tool + schema tool)
- Phase 4 (supervisor + aggregator + pipeline — skip fixer)
- Phase 6 (CLI + terminal output + README)
- Phase 8 (review + ship)

**Fast track: ~15-20 steps. Produces a working `quorum run` with 2 critics, evidence checking, and terminal output.**

---

## Generalization Checklist

Before shipping, verify all of the following:

- [ ] No references to: meta-swarm, orchestrator swarm, OpenClaw, LangGraph, internal file paths
- [ ] Model names use Tier 1/Tier 2 abstraction (not hardcoded Opus/Sonnet)
- [ ] Config uses industry-standard terms (agent, validator, critic — not internal swarm terminology)
- [ ] Rubrics use generic domain names (not specific to our research pipeline)
- [ ] All tool calls are self-contained (no external service dependencies except LLM API)
- [ ] README assumes no prior knowledge of our ecosystem
- [ ] Example artifacts are generic (not from our actual validation runs)

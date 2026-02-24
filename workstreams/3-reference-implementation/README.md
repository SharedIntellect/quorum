# Workstream 3: Reference Implementation

## Objective

Produce a fully functional, generalized, standalone version of the Validator Swarm — published as **Quorum** — that anyone can clone, configure, and run against their own agent systems without any dependency on our internal infrastructure.

## What This Is

The Quorum repo currently ships a spec, implementation guide, rubrics, and documentation. This workstream closes the gap between "blueprint" and "product" by building a working Python reference implementation that:

1. **Executes the full validation pipeline** — supervisor → parallel critics → tester → aggregator → optional fixer
2. **Uses generalized, industry-standard terminology** — no internal swarm names, no proprietary labels
3. **Works with any LLM provider** — model-agnostic via a provider abstraction layer
4. **Runs out of the box** — `pip install`, configure API keys, `quorum run`
5. **Includes real rubrics** — at least 3 domain-specific rubrics ready to use
6. **Demonstrates the learning memory** — `known_issues.json` accumulates across runs

## What This Is NOT

- Not a rewrite of our internal validator — it's a clean-room build from the published spec
- Not tied to OpenClaw, LangGraph, or any specific orchestration platform
- Not a SaaS product — it's a CLI tool and Python library

## Success Criteria

- [x] A developer can clone the repo, install deps, configure an API key, and run a validation in under 10 minutes
- [x] At least one validation run produces a real verdict with evidence-grounded findings
- [ ] The learning memory persists across runs *(Phase 2)*
- [x] Three depth profiles work (quick/standard/thorough)
- [x] No references to internal infrastructure, meta-swarm, or proprietary systems
- [ ] CI passes (lint + basic integration test) *(Phase 2)*

## Build Status

**MVP COMPLETE** — 2026-02-23, commit 61c7116

Built by Sonnet sub-agent from execution plan, reviewed and fixed by Opus. Key implementation decisions:
- LiteLLM as sole provider (not separate Anthropic/OpenAI — covers 100+ models)
- Sequential critic dispatch (parallel deferred to Phase 2)
- Pydantic v2 throughout for data models
- Deterministic verdict rules (no LLM call for verdict assignment)
- Evidence enforced at base critic class level (ungrounded findings rejected before aggregation)

### Test Results
| Artifact | Findings | Verdict | Deduped | Planted Flaws Found |
|----------|----------|---------|---------|---------------------|
| sample-research.md | 10 | REJECT (2C/5H/3M) | 8 merged | All |
| sample-agent-config.yaml | 12 | REJECT (3C/6H/3M) | 4 merged | All 6+ |

### What's Deferred to Phase 2
- Parallel critic dispatch (asyncio/ThreadPoolExecutor)
- Security, Architecture, Delegation critics
- Learning memory (known_issues.json)
- Fixer agent (bounded fix loops)
- CI/CD (GitHub Actions, ruff, mypy, pytest)
- Tester agent (tool-executing critic)

## Source Material

- `SPEC.md` — Architecture and design philosophy
- `IMPLEMENTATION.md` — Build guide with pseudocode
- `CONFIG_REFERENCE.md` — Configuration options, rubric format, verdict taxonomy
- `examples/rubrics/` — Two example rubrics (research synthesis, swarm config)
- Internal validator swarm configs (in parent workspace, NOT published) — for reference only

## Relationship to Existing Repo

This workstream produced the contents of `reference-implementation/` in the published repo. Shipped in commit 61c7116 (2026-02-23). The README Quick Start section now shows real, tested CLI commands.

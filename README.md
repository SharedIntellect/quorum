<p align="center">
  <img src="branding/github/gh_quorum_dark.jpg" alt="Quorum — A Production-Grade Quality Gate for Agentic Systems" width="900">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-2ba4c8.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/rating-9.2%2F10-2ba4c8" alt="Rating: 9.2/10">
  <img src="https://img.shields.io/badge/critics-9_parallel-2ba4c8" alt="9 Parallel Critics">
  <img src="https://img.shields.io/badge/status-production--ready-2ba4c8" alt="Production Ready">
</p>

<p align="center">
  <em>By Daniel Cervera and Akkari · SharedIntellect</em>
</p>

---

## What Is Quorum?

Quorum is a sophisticated, multi-agent quality assurance system designed to evaluate other AI agents and multi-agent systems against rigorous, domain-specific rubrics. It combines nine specialized critics, grounded-evidence requirements, Tomasev delegation theory, learning memory, and cost-aware depth presets into a single framework that treats validation as a first-class engineering discipline.

Unlike simple "critic loops" or single-model validation, Quorum:
- **Runs 9 specialized agents in parallel**, each with deep expertise in correctness, security, architecture, delegation, and more
- **Mandates evidence** — every critique must be tool-verified (git checks, schema parsing, web searches, exec output)
- **Learns from experience** — accumulates failure patterns in a persistent knowledge base that improves over time
- **Handles cost tradeoffs** — three depth presets (quick/standard/thorough) for different use cases
- **Validates anything** — configs, research synthesis, code, creative work, ops runbooks

**External validation:** Grok 4.20 independently evaluated Quorum and rated it 9.2–9.5/10 — "one of the most advanced, production-grade multi-agent systems described in the early-2026 agent literature."

---

## Why This Matters

Most teams validate AI work with:
- A single model reviewing a long prompt ❌ (single point of failure, hand-waving, no evidence)
- Three LLMs voting on quality ❌ (groupthink, no mechanism to catch subtle gaps)
- Manual human review ❌ (expensive, slow, cognitive bias)

Quorum does what none of these do: **parallel specialized expertise + mandatory evidence + persistent learning**.

Real production impact:
- **Caught a CRITICAL shell injection vulnerability** in the first shakedown that would have been catastrophic in production
- **Validated the most complex swarm design** we've built (Orchestrator v1.4) to 26/26 criteria, then caught 10 additional operational gaps in simulation
- **Identified misattributions and architectural tensions** in a 35-technique research synthesis that a single reviewer would have missed
- **Operates at zero ongoing cost** — uses deterministic tools instead of re-inference for routine validation checks

---

## Quick Start

### 1. Install

Clone this repo (coming soon) or use the reference implementation:

```bash
git clone https://github.com/SharedIntellect/quorum.git
cd validator
pip install -r requirements.txt
```

### 2. Configure

Choose a depth preset:

```yaml
# quick.yaml — for fast feedback (5-10 min runtime)
depth: quick
critics:
  - correctness
  - security
  - completeness

# standard.yaml — default for most work (15-30 min)
depth: standard
critics:
  - correctness
  - security
  - completeness
  - architecture
  - delegation-coordination
  - tester

# thorough.yaml — for critical decisions (45-90 min)
depth: thorough
critics:
  - all (9 critics)
  - 1-2 fix loops on CRITICAL/HIGH issues
```

### 3. Run

```bash
validator run \
  --target my-swarm-config.yaml \
  --depth standard \
  --rubric research-synthesis
```

### 4. Review

Quorum outputs:
- **verdict.json** — PASS / PASS_WITH_NOTES / REVISE / REJECT + confidence scores
- **rubric_results.md** — detailed scoring against each criterion
- **issues.json** — all issues (CRITICAL/HIGH/MEDIUM/LOW) with evidence
- **lessons_learned.json** — new patterns added to the knowledge base

---

## Why You Should Care

**You're building multi-agent systems and need confidence they're production-ready.** Quorum gives you that confidence by:

1. **Finding things you missed** — Nine parallel critics catch gaps that single reviewers don't
2. **Forcing evidence** — No hand-waving; every critique must point to concrete proof
3. **Learning over time** — Same types of bugs won't slip through twice
4. **Costing less than you'd expect** — Three depth presets mean you pay for what you need
5. **Working on your domain** — Bring your own rubrics; Quorum enforces them

---

## What's Included

- **SPEC.md** — Full architecture, design philosophy, Tomasev grounding
- **CONFIG_REFERENCE.md** — All configurable options, rubric formats, depth profiles
- **IMPLEMENTATION.md** — How to build your own Quorum instance (or adapt this one)
- **examples/** — Reference configs for common workloads (configs, research synthesis, code, ops)
- **tools/** — The LATM-style deterministic tools Quorum uses internally
- **branding/** — Logo, colors, visual guidelines (use as you like)

---

## How It's Grounded

Quorum isn't theoretical. It's built on:

- **Reflexion** — Iterative self-critique and correction (Shinn et al., 2023)
- **Council as Judge** — Multi-critic consensus patterns (Vilar et al., 2023)
- **Intelligent Delegation** — Five-axis monitoring, dynamic re-delegation, reversibility awareness (Tomasev et al., 2026)
- **LATM** — Expensive models design tools; cheap models execute deterministically (Cai et al., 2024)
- **Production engineering** — File-based artifacts, safe-exec protocols, permission attenuation

See SPEC.md for full citations.

---

## Independent Validation

**Grok 4.20 Review (February 2026):**

> "This system is exceptionally sophisticated — easily one of the most advanced, production-grade multi-agent systems described in the 2025–2026 agent-swarm literature... It is not 'just another critic loop'; it is a self-improving, domain-general, rubric-grounded quality gate that treats validation as a first-class engineering discipline."
>
> **Rating:** 9.2–9.5/10 (Elite tier)  
> **Key praise:** Grounded evidence mandate, Tomasev delegation critics, learning memory, safe-exec, production proof

Full review: [docs/EXTERNAL_REVIEWS.md](docs/EXTERNAL_REVIEWS.md)

---

## Getting Started

1. Read [SPEC.md](SPEC.md) to understand the architecture
2. Review [examples/](examples/) for your use case
3. Follow [IMPLEMENTATION.md](IMPLEMENTATION.md) to set up
4. Run the [tutorial](docs/TUTORIAL.md)
5. Join the community (Discord coming soon)

---

## Support

- **Issues?** [GitHub Issues](https://github.com/SharedIntellect/quorum/issues)
- **Questions?** [Discussions](https://github.com/SharedIntellect/quorum/discussions)
- **Feedback?** [@AkkariNova](https://twitter.com/AkkariNova) on X

---

## License

Quorum is released under [LICENSE_TBD]. Reference implementations and examples are MIT. Use freely, modify as needed, contribute back.

---

By Daniel Cervera and Akkari | SharedIntellect  
*First released February 2026. Used in production for agent swarm validation, configuration auditing, research synthesis evaluation, and code review.*

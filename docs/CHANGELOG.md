# Changelog

All notable changes to Quorum will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] — 2026-02-23

### Added — Reference Implementation MVP
- **Working CLI** — `quorum run --target <file> --depth quick|standard|thorough`
- **2 critics** — Correctness and Completeness, both with evidence grounding enforcement
- **LiteLLM universal provider** — supports Anthropic, OpenAI, Mistral, Groq, and 100+ models
- **2 built-in rubrics** — `research-synthesis` (10 criteria) and `agent-config` (10 criteria)
- **Pipeline orchestration** — supervisor → critics → aggregator → verdict (sequential MVP)
- **Deterministic verdict assignment** — PASS / PASS_WITH_NOTES / REVISE / REJECT based on finding severity
- **Deduplication** — SequenceMatcher-based cross-critic finding dedup with source merging
- **Run directories** — timestamped output dirs with manifest, critic JSONs, verdict.json, report.md
- **First-run setup** — interactive config wizard (model tier + depth preference)
- **Example artifacts** — `sample-research.md` (planted contradictions, unsourced claims) and `sample-agent-config.yaml` (6 planted flaws)
- **FOR_BEGINNERS.md** — explains spec-driven AI tools for newcomers
- **Updated README** — real CLI commands, working install instructions

### Tested
- Research synthesis: 10 findings, REJECT verdict, all planted flaws detected, 8 duplicates merged
- Agent config: 12 findings, REJECT verdict, all 6+ planted flaws detected, 4 duplicates merged

### Fixed
- LiteLLM requires full model slugs (`anthropic/claude-sonnet-4-20250514`), not short names

---

## [1.0.0] — 2026-02-22

### Added
- **9-agent parallel validation architecture** — Correctness, Architecture, Security, Delegation, Completeness, and Style critics, plus Tester, Fixer, and Aggregator
- **Evidence mandate** — every critique requires tool-verified evidence (schema parsing, web search, grep, exec output)
- **Rubric system** — JSON-based rubrics with weighted criteria, evidence types, and severity levels
- **Three depth profiles** — quick (3 critics, ~5 min), standard (6 critics, ~15 min), thorough (all 9, ~45 min)
- **Learning memory** — `known_issues.json` accumulates failure patterns across runs with severity, frequency, and auto-promotion to mandatory checks
- **Tomasev delegation critics** — bidirectional contract evaluation, span-of-control analysis, cognitive friction scoring, dynamic re-delegation triggers
- **Bounded reflection loops** — 1–2 fix rounds on CRITICAL/HIGH issues only, preventing infinite recursion
- **Structured aggregation** — deduplication by location+description, cross-validation of conflicts, confidence recalibration
- **Two-tier model architecture** — judgment-heavy roles on Tier 1 models, execution-heavy roles on Tier 2
- **Example rubrics** — research synthesis and swarm configuration rubrics included
- **Tutorial** — step-by-step walkthrough validating a deliberately broken agent configuration
- **Brand assets** — logo, social previews, README banners (light/dark/transparent)

### External Validation
- Independently evaluated by Grok 4.20 at **9.2–9.5/10** (elite tier)

## Roadmap

- [ ] Dynamic critic specialization (v1.1)
- [ ] Critic-to-critic debate mode (v1.1)
- [ ] Deterministic domain pre-screen (v1.2)
- [ ] Hard cost ceiling with budget allocation (v1.2)
- [ ] Empirical confidence calibration (v2.0)
- [ ] Single-agent validation rubrics (v1.1)

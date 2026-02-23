# Changelog

All notable changes to Quorum will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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

# Changelog

All notable changes to Quorum will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.5.1] — 2026-03-06

### Added — Parallel Execution, Python Code Rubric, Fixer Agent

#### Parallel Critic Execution
- **Critics run concurrently** via `ThreadPoolExecutor` (max 4 critics in parallel)
- **Batch files run concurrently** (max 3 files processed simultaneously)
- Significant throughput improvement for multi-critic and batch validation runs

#### Python Code Rubric (NEW)
- **New built-in rubric: `python-code`** — 25 criteria (PC-001–PC-025)
- **Auto-detection** — rubric is automatically selected when `--target` is a `.py` file and no rubric is specified
- 3 built-in rubrics now shipped: `research-synthesis`, `agent-config`, `python-code`

#### Fixer Agent (NEW — Phase 1.5)
- **New agent: Fixer** — activates when `max_fix_loops > 0` (thorough depth default: 1)
- **Proposal mode** — proposes concrete text replacements for CRITICAL/HIGH findings
- **Pipeline position:** Phase 1.5, between critic dispatch and cross-artifact consistency
- Re-validation loops (apply proposals → re-run critics → verify) are deferred to a future release

### Self-Validation
- Ran Quorum against itself using the new Python code rubric
- Result: REVISE, 16 findings — pipeline refactor in progress

---

## [0.5.0] — 2026-03-06

### Added — Framework-Grounded Critics

#### Code Hygiene Critic (NEW)
- **New module: `critics/code_hygiene.py`** — evaluates structural code quality
- **Grounded in:** ISO/IEC 25010:2023 (Maintainability + Reliability), ISO/IEC 5055:2021 (CISQ CWE mappings)
- **12 evaluation categories** (CAT-01 through CAT-12): Code Correctness, Error Handling, Resource Management, Complexity & Modularity, Code Duplication, Naming & Documentation, Type Safety, Async & Concurrency, Import Hygiene, Style & Formatting, Portability, Testability
- **6 agentic patterns** (AP-01 through AP-06): Prompt Construction, LLM API Calls, Agent Pipeline Errors, Credential Management, Timeout & Retry, Logging & Observability
- **Two-layer architecture** — deterministic pre-screen rules + LLM judgment for what SAST cannot catch
- **Delegation boundary** — flags security-relevant patterns (eval, exec, credentials) but explicitly delegates security assessment to Security Critic
- **Evidence grounding enforced** — inherits BaseCritic's evidence mandate

#### Security Critic (REVISED — Framework-Grounded Upgrade)
- **Upgraded from ad-hoc to framework-grounded evaluation**
- **Now grounded in:** OWASP ASVS 5.0.0 (17 chapters), CWE Top 25 (2024), NIST SP 800-53 SA-11, ISO/IEC 25010:2023 Security sub-characteristics
- **14 security categories** (SEC-01 through SEC-14): Injection, Input Validation, Authentication, Authorization, Session/Tokens, Cryptography, Secrets, Path Traversal, Deserialization, SSRF, Error/Info Disclosure, Security Logging, Supply Chain, DoS
- **Tiered evaluation model** — Tier 1 (must-evaluate), Tier 2 (should-evaluate), Tier 3 (deep-analysis)
- **Detection capability matrix** — instructs LLM to focus on SAST-blind categories (authorization logic, IDOR, JWT, SSRF, authentication bypass)
- **Finding citation format** — ASVS §section, CWE-ID, SA-11 sub-control references
- **All 6 original focus areas preserved** — context-aware sensitivity, proprietary content, info disclosure, prompt injection, dependency risk, boundary enforcement (enhanced with framework citations)

#### Research Corpus (NEW — 5 Research Documents)
- `docs/research/iso-25010-quality-model.md` — ISO/IEC 25010:2023, 9 characteristics, 40 sub-characteristics, evaluability classification
- `docs/research/cisq-quality-measures.md` — ISO/IEC 5055:2021, 195 weaknesses across 4 dimensions with CWE IDs
- `docs/research/python-static-analysis-taxonomy.md` — Ruff 900+ rules, Pylint 500+ messages, quality dimension coverage matrix
- `docs/research/powershell-static-analysis-taxonomy.md` — PSScriptAnalyzer 69 rules, 6 quality dimensions, agentic patterns
- `docs/research/security-code-review-frameworks.md` — OWASP ASVS 5.0, CWE Top 25, CERT, NIST SA-11 cross-reference

#### Framework Specifications (NEW)
- `docs/CODE_HYGIENE_FRAMEWORK.md` (~50KB) — complete evaluation spec for Code Hygiene Critic
  - All 40 ISO 25010:2023 sub-characteristics mapped with inclusion/exclusion rationale
  - Two-layer architecture per category (deterministic + LLM judgment)
  - CERT applicability note (no official Python/PowerShell standard)
  - Two-critic architecture narrative (delegation boundary)
- `docs/SECURITY_CRITIC_FRAMEWORK.md` (~47KB) — complete evaluation spec for Security Critic
  - Detection capability matrix (40 rows: SAST strength vs. LLM advantage)
  - Python checklist (25 items) + PowerShell checklist (24 items)
  - Minimum viable coverage for SA-11 alignment (Tier 1/2/3)
  - Framework cross-reference: where ASVS/CWE/CERT/SA-11 overlap vs. contribute uniquely
  - Finding citation vocabulary with severity calibration

#### Cross-Artifact Consistency Design (NEW)
- `docs/CROSS_ARTIFACT_DESIGN.md` — architectural decisions for Roadmap item #6
- **Design axiom:** "In a judgment system, always trade toward transparency over convenience"
- **Decision 1:** Explicit relationship declaration via `quorum-relationships.yaml` manifest (auto-inference deferred)
- **Decision 2:** Separate cross-consistency critic type (preserves single-file critic composability)
- **Decision 3:** Multi-locus Finding model with `Locus` objects (role annotations, `source_hash` for drift detection)
- **Data flow contract:** Cross-critic receives single-file findings (evidence) but not verdicts (conclusions) — preserves assessor independence

#### Documentation Standards (NEW)
- `docs/DOCUMENTATION_STANDARDS.md` — universal `@KEY: value` header schema
- Three required keys: `@module`/`@doc`/`@config`/`@script`, `@purpose`, `@version`
- Decision-density heuristic for Strategy A (inline) vs. Strategy B (reference doc)
- Machine-readable `quorum-header-schema.yaml` for pre-screen validation
- Single source of truth: `@relationships` points to manifest, no duplicate declarations

### Fixed — Framework Document Corrections
- **S303 misattributed** to shelve in SEC-09 → corrected to S403 (pickle/shelve import detection)
- **S324 misattributed** to jsonpickle in SEC-09 → corrected to "no dedicated rule — LLM detection"
- **CWE-683 not in CISQ** → removed from CAT-01; CWE-561/570/571 reclassified with correct CISQ dimensions
- **3 missing ISO 25010 sub-characteristics** → added Interoperability, Appropriateness Recognizability, Scalability
- **AP-04/SEC-07 overlap** → delegation note added ("Hygiene flags, Security assesses")
- **CAT-02 child CWEs** → annotated as children of CWE-703 per CISQ conformance model

### Validated
- Framework docs: Validator Swarm PASS (78%) → Correctness re-run ISSUES_FOUND (91% confidence) → all findings fixed
- Code Hygiene Critic: Validator Swarm PASS (95% confidence) — 6/6 checks, 0 findings
- Security Critic revision: Validator Swarm PASS (95% confidence) — 6/6 checks, 0 findings
- Cross-checks: 2/2 passed — no overlap violation, consistent style

### Roadmap Status
- [x] Custom rubric loading (Milestone #1)
- [x] Multi-file / batch validation (Milestone #2)
- [x] Deterministic pre-screen layer (Milestone #3)
- [x] Security critic — framework-grounded (Milestone #4) ← **DONE**
- [x] Code hygiene critic (Milestone #5) ← **DONE**
- [x] Cross-artifact consistency (Milestone #6) ← **DONE**
- [ ] Confidence calibration (Milestone #6b)
- [ ] Learning memory (Milestone #7)
- [ ] Fix loops (Milestone #5b)
- [x] Parallel critic execution (Milestone #8) ← **DONE**
- [x] Parallel batch validation (Milestone #8b) ← **DONE**
- [x] Python code rubric — 25 criteria, auto-detect on .py ← **DONE**
- [x] Fix loops / Fixer agent (Milestone #5b) ← **DONE** (proposals; re-validation loops future)
- [ ] Python rubric framework grounding — research swarm for PEP 8/257/484, Python antipatterns literature, map criteria to published sources with citations (same rigor as SEC/hygiene frameworks)
- [ ] Architecture critic (Milestone #9)
- [ ] Tester critic (Milestone #10)
- [ ] Confidence calibration (Milestone #6b)
- [ ] Learning memory (Milestone #7)
- [ ] Delegation critic (Milestone #11)
- [ ] Style critic (Milestone #12)
- [ ] Documentation headers adoption (Phase 1–4)
- [ ] Self-validation graduation (GRAD)

---

## [0.2.0] — 2026-03-05

### Added — Parity Milestones #1–#3

#### Milestone #1: Custom Rubric Loading
- **File path rubrics** — `--rubric ./path/to/my-rubric.json` now loads custom rubric files directly
- **Schema flexibility** — rubric loader accepts field aliases: `category`→`severity`, `evidence_instruction`→`evidence_required`, `rationale`→`why`
- **Backwards compatible** — built-in rubric names still work as before
- **Unblocks:** PKI rubric flywheel strategy (RFC 3647, CA/B Baselines, etc.)

#### Milestone #2: Multi-File / Batch Validation
- **Directory targets** — `quorum run --target ./docs/` validates all text files in a directory
- **Glob patterns** — `quorum run --target "./**/*.md"` expands wildcards
- **Pattern filter** — `--pattern "*.yaml"` filters directory contents
- **Consolidated verdicts** — `BatchVerdict` aggregates per-file results with worst-case status propagation
- **Batch reports** — per-file summary table + aggregate findings in `batch-report.md` and `batch-verdict.json`
- **Batch run directories** — `quorum-runs/batch-TIMESTAMP/per-file/...` structure
- **Graceful degradation** — one file failing doesn't kill the batch; errors collected and reported separately
- **New models** — `BatchVerdict`, `FileResult` (Pydantic v2)
- **New functions** — `resolve_targets()` (file/dir/glob resolution), `run_batch_validation()`, `print_batch_verdict()`
- **Files changed:** `models.py`, `pipeline.py`, `cli.py`, `output.py`

#### Milestone #2 Security Hardening (Validator Swarm QA)
- **Path traversal guard** — `_validate_path()` with boundary enforcement on all resolved paths
- **Pattern sanitization** — `..` in `--pattern` explicitly rejected
- **Auto-boundary** — directory targets use themselves as boundary; globs use non-glob prefix
- **Path leakage mitigation** — error messages use relative/basename instead of full absolute paths

#### Milestone #3: Deterministic Pre-Screen Layer
- **New module: `prescreen.py`** — runs fast deterministic checks before LLM critics
- **10 checks implemented:**
  - PS-001: Hardcoded absolute paths (regex)
  - PS-002: Potential credentials/secrets (regex + base64 detection)
  - PS-003: PII patterns — email, phone, SSN-like (regex)
  - PS-004: JSON validity (`json.loads()`)
  - PS-005: YAML validity (`yaml.safe_load()`)
  - PS-006: Python syntax (`py_compile.compile()`)
  - PS-007: Broken relative markdown links (regex + file existence)
  - PS-008: TODO/FIXME/HACK/XXX markers
  - PS-009: Trailing whitespace + mixed CRLF/LF line endings
  - PS-010: Empty file detection
- **Evidence injection** — `to_evidence_block()` formats results for LLM critic prompt injection as `pre_verified_evidence[]`
- **Config toggle** — `enable_prescreen: bool` (default: true)
- **Extension-aware** — checks gated by file type; skipped checks marked in evidence
- **Zero new dependencies** — stdlib only
- **Pipeline integration** — pre-screen runs between rubric loading and critic dispatch; results written to `prescreen.json`
- **New models** — `PreScreenCheck`, `PreScreenResult` (Pydantic v2)
- **Files changed:** new `prescreen.py`, updated `models.py`, `config.py`, `pipeline.py`, `agents/supervisor.py`, `output.py`

### Changed
- `--target` CLI option now accepts strings (was `click.Path`) to support directories and globs
- `run-manifest.json` now includes `prescreen_enabled`, prescreen stats, `completed_at`, and `verdict`
- Supervisor `run()` accepts optional `PreScreenResult` for critic evidence enrichment

### Validated
- Milestone #2 validated by Validator Swarm v2.3 (Run #9, standard depth, 6 critics)
  - 19/19 correctness checks passed, 14/14 requirements addressed
  - 3 CRITICAL path traversal findings → resolved in security hardening
  - Final: all acceptance criteria met

### Roadmap Status
- [x] Custom rubric loading (Milestone #1) ← **DONE**
- [x] Multi-file / batch validation (Milestone #2) ← **DONE**
- [x] Deterministic pre-screen layer (Milestone #3) ← **DONE**
- [x] Security critic (Milestone #4) ← **DONE** (revision pending after framework validation)
- [~] Code hygiene critic (Milestone #5) ← **FRAMEWORK COMPLETE**, build pending
- [ ] Cross-artifact consistency (Milestone #6)
- [ ] Confidence calibration (Milestone #6b)
- [ ] Learning memory (Milestone #7)
- [ ] Fix loops (Milestone #5b)
- [ ] Self-validation graduation (GRAD)

### Research & Framework Documents (2026-03-05)
- **5-agent research swarm** covering ISO 25010:2023, CISQ/ISO 5055, Ruff/Pylint, PSScriptAnalyzer, OWASP ASVS 5.0/CWE/CERT/SA-11
- **`docs/CODE_HYGIENE_FRAMEWORK.md`** — 12 evaluation categories + 6 agentic patterns, two-layer architecture, full coverage matrix
- **`docs/SECURITY_CRITIC_FRAMEWORK.md`** — 14 security categories, Python/PowerShell checklists, detection capability matrix
- **Validator swarm: PASS (78% confidence)** — correctness critic timed out, re-run pending for higher confidence
- **4 findings** (1 MEDIUM, 3 LOW): ISO 25010 Safety sub-chars incomplete, grouped scope rows, cross-reference note, CERT limitation note

---

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

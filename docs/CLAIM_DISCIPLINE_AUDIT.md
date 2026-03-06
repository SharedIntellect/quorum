# Claim Discipline Audit — v0.5.1 → v0.5.2

**Scope:** Align public claims with shipped capabilities per feedback from Grok, GPT 5.4, and Devola.

**Principle:** State exactly what ships today. Show the vision in diagrams and roadmaps. Don't promise in prose.

---

## File-by-File Edits

### 1. README.md

**Context:** Top-level product positioning

**Current:**
> "Quorum is production infrastructure for validating AI-generated artifacts..."

**Change to:**
> "Quorum is a production-oriented, early-stage validation framework for AI-generated artifacts..."

**Rationale:** Honest about maturity (no tests, no CI yet). "Production-oriented" signals the architecture is sound; "early-stage" signals the product isn't hardened. Removes false "production-grade" positioning per GPT 5.4 feedback.

---

**Current:**
> "9 parallel critics evaluate..."

**Change to:**
> "4 critics evaluate... (6 more planned)"

**Rationale:** State shipped count. Show the vision in the architecture diagram, not in prose claims.

---

**Current (What's Coming section):**
> "Learning memory, confidence calibration, dynamic specialization..."

**Change:** Keep as-is (this is explicitly roadmap territory, not a current claim).

---

### 2. SPEC.md

**Context:** Specification document. Sets expectations about what's actually implemented.

**§1 Opening Paragraph**

**Current:**
> "Quorum is a nine-agent quality assurance system with learning memory, designed to validate AI-generated artifacts through evidence-grounded evaluation and multi-stage orchestration."

**Change to:**
> "Quorum is a quality assurance framework with a nine-agent target architecture. Currently, 4 critics are implemented (Correctness, Completeness, Security, Code Hygiene), with 5 additional critics planned. The framework is designed to validate AI-generated artifacts through evidence-grounded evaluation and multi-stage orchestration."

**Rationale:** Separates "what we're building toward" (nine-agent architecture, shown in diagrams) from "what ships today" (4 critics by name). Removes false "learning memory" present-tense claim from opening.

---

**Learning Memory paragraph**

**Current:**
> "Learning memory captures patterns from validation runs..."

**Change to:**
> "Specified learning memory architecture: A system to capture patterns from validation runs... Currently not wired into production runs. Planned for v0.6+."

**Rationale:** Honest status. Design is documented; implementation isn't shipped.

---

**"This is real lifelong learning" sentence**

**Current:**
> "This is real lifelong learning because the system..."

**Change to:**
> "Planned system-level learning: The system will..."

**Rationale:** "Real" implies shipped. "Planned" is accurate.

---

**"Ready for deployment" claim**

**Current:**
> "This architecture is ready for deployment in production environments..."

**Change to:**
> "This architecture is suitable for research use and early-stage integration. Known limitations: no test suite, no CI, 4/9 critics shipped, learning/trust/monitoring systems specified but not wired."

**Rationale:** Honest about maturity. Sets expectations.

---

**§4 Research Grounding**

**Tomasev et al. citation**

**Current:**
> "Tomasev et al. (2024) establishes the principles of..."

**Change to:**
> "Tomasev et al. (2024) informs our architecture. We interpret their trust principles as follows: [implementation details]. This is an engineering interpretation, not a direct validation of the full system."

**Rationale:** Distinguishes "inspired by research" from "validated by research." Honest about the gap.

---

**ToolMaker citation**

**Current:**
> "ToolMaker (Schlagkamp et al.) validates our closed-loop approach..."

**Change to:**
> "ToolMaker (Schlagkamp et al.) informs our design for closed-loop self-correction. Our implementation of fixer loops is an engineering adaptation, not a direct port."

**Rationale:** Same principle — "informs" vs "validates."

---

### 3. docs/SECURITY_CRITIC_FRAMEWORK.md

**Top of document, add:**

```markdown
## Status

**v0.5.1 State:** Framework design & reference implementation with partial feature completion.

- [x] Framework design and documentation
- [x] 14 evaluation categories (SEC-01–SEC-14) specified
- [x] OWASP ASVS 5.0, CWE Top 25, NIST SP 800-53 SA-11 grounding
- [x] Detection capability matrix for SAST vs LLM judgment boundaries
- [ ] Full SAST tool integration (Ruff/Bandit/PSScriptAnalyzer) — Milestone #15, v0.5.2
- [ ] Threat model context feeding for SEC-04 (Authorization) — v0.5.3 planned
- [ ] Learning memory wiring (issue tracking) — v0.6+

**Known Limitations:**
- Pre-screen layer runs 10 regex checks; 80+ referenced SAST rules not yet integrated
- Authorization review (SEC-04) is speculative without threat model context
- PowerShell coverage ~70% vs 85%+ for Python (tooling ecosystem gap)
```

---

### 4. docs/CODE_HYGIENE_FRAMEWORK.md

**Top of document, add:**

```markdown
## Status

**v0.5.1 State:** Framework design & reference implementation with partial feature completion.

- [x] Framework design and documentation
- [x] 12 evaluation categories specified
- [x] ISO/IEC 25010:2023 (Maintainability + Reliability) grounding
- [x] Two-layer architecture (deterministic + LLM) with delegation boundaries
- [ ] Full SAST tool integration (Ruff/Pylint) — Milestone #15, v0.5.2
- [ ] Business logic validation workflow (SEC-02) — v0.5.3 planned
- [ ] Learning memory wiring — v0.6+

**Known Limitations:**
- Pre-screen layer runs 10 regex checks; deterministic Python analyzer not fully integrated
- Business logic checks require specification/requirements context (not yet automated)
```

---

### 5. docs/CROSS_ARTIFACT_DESIGN.md

**Top of document, add:**

```markdown
## Status

**v0.5.1 State:** Fully implemented in reference implementation.

- [x] Relationship manifest schema (quorum-relationships.yaml)
- [x] Multi-locus findings with role annotations
- [x] Source hash (SHA-256) for drift detection
- [x] Phase 2 orchestration with findings-only (not verdicts) passing
- [x] Assessor independence principle enforced in architecture
```

---

### 6. docs/MODEL_REQUIREMENTS.md

**Model compatibility table, "not enough" tier**

**Current:**
> Llama 70B, most open models | Not enough | ...

**Change to:**
> Llama 70B, most open models | Untested in Quorum; may lack reasoning depth for judgment-heavy criteria | ...

**Rationale:** "Untested" is honest. Remove the opinion-like "not enough" without data.

**Add note below table:**

```markdown
**Note on model assessment:** These recommendations are based on architectural requirements (reasoning depth, token budget for multi-stage evaluation). Assessments are not backed by empirical Quorum benchmarks yet. Users are encouraged to test with their preferred models.
```

---

### 7. reference-implementation/README.md

**Audit for consistency with main README.**

**Action:** Verify no separate overclaims. Ensure "4 critics" language matches main README.

---

### 8. reference-implementation/quorum/critics/security.py & code_hygiene.py

**Verify:** Docstrings no longer claim "Ruff is integrated" or "PSSA rules are checked." Confirm they state "10 custom pre-screen checks" and "LLM evaluation of OWASP/CWE/NIST criteria."

**Status:** Per handoff, these were fixed. Spot-check the docstrings.

---

### 9. Diagrams & Visual References

**Files to audit for critic labeling:**

1. **README.md** — Architecture diagram (if present)
   - Verify: 4 shipped critics marked distinctly from 5 planned
   - Suggest: Color coding (green = shipped, gray = planned) or status badges

2. **SPEC.md** — Architecture & pipeline diagrams (if present)
   - Verify: 9-critic ecosystem shows status of each (Implemented/Planned)
   - Suggest: Legend or footnotes explaining colors/symbols

3. **reference-implementation/README.md** — Architecture diagram (if present)
   - Verify: Consistency with main README diagram styling

**Action:** If diagrams exist, add a legend or color-coding that visibly distinguishes shipped (Correctness, Completeness, Security, Code Hygiene) from planned (Architecture, Delegation, Tester, Style, Fixer).

---

## GitHub UI Changes (Daniel, manual)

**SharedIntellect org page:**
- Current: "9 parallel critics, learning memory"
- Change to: "Validation framework with 4 critics shipped, 5 planned"

**Quorum repo description:**
- Current: verify it doesn't say "production-grade" or "learning memory"
- Change to: align with README language — "production-oriented early-stage validation framework"

---

## Validation

After all edits:
1. README should say "4 critics" in prose, "9-critic vision" only in diagrams
2. Diagrams showing 9-critic architecture must clearly label which 4 are shipped vs which 5 are planned
   - Examples: color-coding (green=shipped, gray=planned), legend, status badges, footnotes
   - Check: README.md diagram, SPEC.md diagrams, reference-implementation/README.md
3. SPEC §1 should clearly separate "what ships" from "what's planned"
4. Each framework doc should have explicit Status section
5. Citations should use "inspires" or "informs," not "establishes" or "validates"
6. Model table should say "untested," not "not enough"

---

## Rollout

- [ ] Apply all edits
- [ ] Commit: "Claim discipline audit: align prose claims with shipped state (v0.5.2 prep)"
- [ ] Push to GitHub
- [ ] Update ClawHub metadata (if needed)
- [ ] Update TODO.md: mark "Claim discipline audit" DONE

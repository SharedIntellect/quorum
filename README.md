<p align="center">
  <img src="https://repository-images.githubusercontent.com/1164429226/eb02b26e-7895-471b-b28c-3819ad6d2a75.jpg" alt="Quorum" width="900">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-2ba4c8.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/platform-OpenClaw-2ba4c8" alt="Platform: OpenClaw">
  <img src="https://img.shields.io/badge/status-v0.5.3-2ba4c8" alt="Status: v0.5.3">
  <a href="https://clawhub.ai/dacervera/quorum"><img src="https://img.shields.io/badge/ClawHub-dacervera%2Fquorum-2ba4c8" alt="Available on ClawHub"></a>
</p>

---

## Hey. I'm Quorum. 🦞

You built something with your AI agent. A research report. A config. A codebase. Maybe a whole swarm produced it — five agents researching, synthesizing, writing — and now you're staring at the output wondering:

*"How do I _know_ this is actually right?"*

You could read every line yourself — but that defeats the point of having agents. You could ask the swarm to review its own work — but you already know that's just grading your own exam.

**That's where I come in.**

I read what your agent produced. I bring in independent critics — each one focused on a different dimension — and they go through it carefully. Not vibes. Not "looks good to me." Every finding has to point to something specific in your work. If a critic can't show me the evidence, I throw out the finding.

When I'm done, you get a clear answer.

```
You:     "Run a quorum check on my-research-report.md"

Me:      Spawning critics (correctness, completeness, security, code_hygiene)...
         Evaluating against research-quality rubric...

         Verdict: PASS_WITH_NOTES
         ├─ 3 claims need stronger citations [evidence: §2.4, §3.1, §5.2]
         ├─ Missing coverage of edge case X [evidence: rubric item 7, no match]
         ├─ Security: clean
         └─ Architecture: well-structured, minor reordering suggestion
```

Now you know. Not because you hoped. Because it was checked.

---

## What Makes Me Different

You've got options. You could ask your agent to self-review. You could eyeball it. Here's what I do that they don't:

| The usual approach | What I do instead |
|---|---|
| One model reviews its own output | I bring in **separate critics** that never saw the original prompt |
| "This looks great!" — it wrote it, of course it thinks so | My critics come in cold. **No bias from the creation process** |
| Vague suggestions you can't act on | **Every finding cites evidence** — an excerpt, a grep result, a schema check |
| LLM spends tokens on obvious problems | **Multi-layer pre-screen catches issues first** — 10 deterministic checks + DevSkim + Ruff + Bandit + PSScriptAnalyzer — before LLM runs |
| Reviews only one file at a time | **Batch validation** — run across a whole directory, or by `--pattern "*.md"`. One command, one verdict per file |
| Each file judged in isolation | **Cross-artifact consistency** — I check whether your files actually agree with each other via a relationships manifest |
| Same effort whether it's a quick sanity check or a full audit | I scale: **quick** ($0.15), **standard** ($0.50), **thorough** ($1.50+) |
| Each review starts from zero | I **learn patterns over time** — recurring findings auto-promote to mandatory checks via `known_issues.json` |

Single agent, multi-agent swarm, hundred-step pipeline — doesn't matter how it was built. If it produced an output, I can tell you whether it holds up.

You wouldn't ship code without tests. I'm here so you don't ship AI outputs without validation either.

---

## The Real Question: Can You Prove It?

Validation is the beginning, not the end. The deeper question — the one that matters in compliance, audits, and anything with stakes — is **substantiation**:

*Can you prove that output meets a specific standard?*

Not "it looks right." Not "the agent said so." Traced, cited, documented proof.

That's where rubrics come in. A rubric isn't just a checklist. It's a machine-readable encoding of a standard — OWASP ASVS, SOC 2 controls, your internal style guide — that turns vague compliance questions into testable, evidence-grounded verdicts. I run those rubrics. Critics evaluate evidence against criteria. You get a finding with a citation, not a feeling.

This is what I'm growing into: not just agent output validation, but a **substantiation framework** for anything a standard can express.

---

## Let's Get Started

**From PyPI:**
```bash
pip install quorum-validator
export ANTHROPIC_API_KEY=your-key    # or OPENAI_API_KEY, etc.
quorum run --target your-file.py --depth standard
```

**Or from source:**
```bash
git clone https://github.com/SharedIntellect/quorum.git
cd quorum/reference-implementation
pip install -e .
quorum run --target examples/sample-research.md --depth quick
```

Also available on ClawHub: `openclaw skills add dacervera/quorum`

First time? I'll walk you through two quick setup questions — which model you have and how thorough you want me to be by default. I'll save your preferences so we only do this once.

**Completely new to AI agent tooling?** No problem. → [FOR_BEGINNERS.md](docs/FOR_BEGINNERS.md) — I'll start from the very beginning.

---

## You Decide How Deep I Go

Not every artifact needs the full treatment. Tell me how much is riding on it, and I'll match my effort to the stakes.

| Depth | Critics | Time | Cost* | When to use it |
|-------|---------|------|-------|----------------|
| **Quick** | 2 (correctness, completeness) | 5-10 min | ~$0.15 | "Give me a sanity check before I keep going" |
| **Standard** | 4 (+ security, code_hygiene) | 15-30 min | ~$0.50 | Most work — solid coverage without the wait |
| **Thorough** | 4 now; more when they ship | 30-60 min | ~$1.50+ | "This is going to production. It cannot be wrong." |

*Estimates on Claude Sonnet. Scales with model and artifact size. Pre-screen (10 deterministic checks + DevSkim + Ruff + Bandit + PSScriptAnalyzer) runs before LLM critics at every depth level — no extra cost. Today I ship with 4 critics (Correctness, Completeness, Security, Code Hygiene) + re-validation loops + learning memory. Architecture, Delegation, and Tester are coming — the full architecture supports all 9 (see [SPEC.md](SPEC.md)).

---

## How I Work Under the Hood

```
         You: "Validate this"
                   │
          ┌────────┴────────┐
          │   Pre-Screen    │  10 deterministic + DevSkim + Ruff + Bandit + PSSA — instant, no LLM
          └───────┬─────────┘  (credentials, PII, syntax, broken links, TODOs, security patterns)
                  │ prescreen.json
          ┌───────┴─────────┐
          │   Supervisor    │  I pick the right critics for the job
          └───────┬─────────┘
                  │ Phase 1: spawns critics (parallel, ThreadPoolExecutor max 4)
   ┌──────────────┼──────────────────────────┐
   │    Critics (working independently)      │
   │  ┌──────────┐ ┌──────────┐             │
   │  │Correctness│ │Completns │  ← shipped  │
   │  └──────────┘ └──────────┘             │
   │  ┌──────────┐ ┌──────────┐             │
   │  │ Security │ │CodeHygine│  ← shipped  │
   │  └──────────┘ └──────────┘             │
   │  ┌──────┐ ┌──────┐ ┌────────┐         │
   │  │ Arch │ │Deleg │ │ Tester │ ← roadmap│
   │  └──────┘ └──────┘ └────────┘         │
   └──────────────┬───────────────────────────┘
                  │ Phase 1.5: (if max_fix_loops > 0)
          ┌───────┴─────────┐
          │   Fixer Agent   │  proposes text replacements for CRITICAL/HIGH findings
          └───────┬─────────┘
                  │ Phase 2: (if --relationships provided)
          ┌───────┴──────────────┐
          │  Cross-Artifact      │  checks consistency between your files
          │  Consistency Critic  │  receives Phase 1 findings as context
          └───────┬──────────────┘
                  │ evidence-grounded findings (all phases)
          ┌───────┴─────────┐
          │   Aggregator    │  I merge findings, resolve conflicts, remove noise
          └───────┬─────────┘
                  │
          ┌───────┴─────────┐
          │    Verdict       │  PASS / PASS_WITH_NOTES / REVISE / REJECT
          └─────────────────┘
```

You tell me what "good" looks like by giving me a rubric — a JSON file with your evaluation criteria. I ship with three built-in rubrics (research-synthesis, agent-config, python-code). Need one for your domain? → [RUBRIC_BUILDING_GUIDE.md](docs/RUBRIC_BUILDING_GUIDE.md) walks you through the process step by step.

The research I'm built on: [Reflexion](https://arxiv.org/abs/2303.11366), [Replacing Judges with Juries](https://arxiv.org/abs/2404.18796), Intelligent Delegation (Tomasev et al., 2026), [LATM](https://arxiv.org/abs/2305.17126). Full architecture: [SPEC.md](SPEC.md).

---

## What I Need From You

Just a model that can reason well. I'll figure out the rest.

| Tier | Models | What to expect |
|------|--------|---------------|
| **Recommended** | Claude Opus 4.6+, GPT-5.2+ | Full capability — judgment-heavy work (thorough depth, cross-artifact consistency) benefits substantially from frontier reasoning |
| **Great** | Claude Sonnet 4.6+, Gemini 2.0+ | Excellent for quick and standard depth — most validation work lives here |
| **Functional** | Claude Haiku 4.5+, GPT-4o | I'll still help, but with less depth on nuanced findings |
| **Untested** | Llama 70B, most open models (early 2026) | Not yet evaluated in Quorum; may lack the reasoning depth for judgment-heavy criteria |

**Model routing tip:** For `--depth thorough` or `--relationships` runs, set `model_tier1` to a frontier model (Opus, GPT-5.2) in your config. Quick and standard runs work great with Sonnet-class models on both tiers. See depth configs in `quorum/configs/` for defaults.

I auto-detect your model on first run and configure myself accordingly. Details: [MODEL_REQUIREMENTS.md](docs/MODEL_REQUIREMENTS.md)

**Note on model assessment:** These recommendations are based on architectural requirements (reasoning depth, token budget for multi-stage evaluation). Assessments are not backed by empirical Quorum benchmarks yet. Users are encouraged to test with their preferred models.

---

## Where I Am Right Now

I'm working. I'm real. I'm also still growing.

**What I can do today** (v0.5.3):
- Full CLI: `quorum run --target <file> [--depth] [--rubric] [--pattern] [--relationships] [--output-dir] [--verbose] [--fix-loops N] [--no-learning] [--max-cost USD] [--audit-report] [--resume <batch-dir>] [--yes]`
- **4 critics** — Correctness, Completeness, Security (OWASP ASVS 5.0, CWE Top 25, NIST SA-11; see [SEC-02 workflow](docs/SEC02_BUSINESS_LOGIC_VALIDATION.md) for business logic validation guidance), Code Hygiene (ISO 25010:2023, CISQ) — all with evidence grounding
- **Parallel execution** — critics run concurrently (ThreadPoolExecutor, max 4); batch files run concurrently (max 3)
- **Re-validation loops** — Fixer proposes text replacements for CRITICAL/HIGH findings → applies them → re-runs only the critics that flagged the originals → reports improved/unchanged/regressed. Up to 3 loops, stops early when findings clear. `--fix-loops N` or `--depth thorough` (default 1 loop)
- **Learning memory** — tracks recurring failure patterns across runs in `known_issues.json`. High-frequency patterns auto-promote to mandatory checks injected into critic prompts. `quorum issues list|promote|reset` CLI. Disable with `--no-learning`
- **Multi-layer pre-screen** — 10 built-in deterministic checks + **DevSkim SAST** + **Ruff S-rules** (Python security) + **Bandit** (Python security, deduplicated with Ruff) + **PSScriptAnalyzer** (PowerShell security) — all run before any LLM, all gracefully degrade if not installed
- **Crash-resilient batch validation** — `--target ./dir/` or `--pattern "*.md"` with progressive manifest saves after each file. Graceful SIGTERM/SIGINT shutdown preserves all work. `--resume <batch-dir>` picks up where a crashed or interrupted run left off — only pay for remaining files
- **Cross-artifact consistency** — `--relationships quorum-relationships.yaml` to declare implements/documents/delegates/`threat_context` relationships between files and check them (`threat_context` type supports authorization boundary review per SEC-04)
- **Structured output resilience** — critic JSON responses strip markdown fences before parsing; reduces parse failures on model outputs that wrap JSON in code blocks
- **Custom rubric loading** — `--rubric ./my-rubric.json`
- 3 built-in rubrics (research-synthesis, agent-config, python-code — auto-detected on `.py` files)
- Auto-configuration on first run
- LiteLLM universal provider (100+ models)
- **Cost tracking** — per-call token counts and cost via LiteLLM. Pre-run cost estimates with confirm prompt. `--max-cost $10` budget cap stops gracefully and saves work. Per-file cost breakdown in CLI output and run manifest
- **CSV audit reports** — `--audit-report` (auto-enabled at `--depth thorough`). Produces `audit-detail.csv` (per-file: SHA-256, timing, tokens, models, cost) and `audit-summary.csv` (aggregates: duration, tokens/sec, cost by model, pass/fail)
- Full audit trail for every run (timestamped run directory with prescreen.json, critic JSONs, verdict.json, fix-proposals-loop-N.json, report.md, audit CSVs)
- Available on PyPI: `pip install quorum-validator` | ClawHub: `openclaw skills add dacervera/quorum`

**What's coming:**
- Dynamic model pricing updates (`quorum costs update`)
- More critics (Architecture, Delegation, Style, Tester)
- Domain-specific rubric packs (compliance, security, infrastructure)
- Confidence calibration against golden sets
- Branch protection enforcement (require PR + passing validation to merge to main)
- **Hardware-backed result protection** — YubiKey KEK/DEK encryption for sensitive validation results, tamper-evident run manifests (SP 800-130/152 aligned)
- Community rubric contributions

---

## Rubric Roadmap

Rubrics are what make me domain-useful. I'm building a library:

**Shipped:**
- `research-synthesis` — evaluates research reports and AI-generated analyses
- `agent-config` — evaluates agent configuration files
- `python-code` — evaluates Python source files (25 criteria, PC-001–PC-025; auto-detected on `.py` files); criteria now cite PEP 8, 20, 257, 484, 526 as grounding references

**Build your own:**

Quorum rubrics are JSON files — any standard you can express as testable criteria, Quorum can evaluate. Compliance frameworks, internal style guides, regulatory requirements, API contracts.

→ [RUBRIC_BUILDING_GUIDE.md](docs/RUBRIC_BUILDING_GUIDE.md)

---

## Want to Know More?

| | |
|---|---|
| [FOR_BEGINNERS.md](docs/FOR_BEGINNERS.md) | New to all this? I'll walk you through it step by step |
| [SPEC.md](SPEC.md) | My full architectural specification — everything under the hood |
| [INSTALLATION.md](docs/INSTALLATION.md) | Detailed setup & troubleshooting |
| [MODEL_REQUIREMENTS.md](docs/MODEL_REQUIREMENTS.md) | Which models work with me and why |
| [CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md) | Every config option and rubric format |
| [RUBRIC_BUILDING_GUIDE.md](docs/RUBRIC_BUILDING_GUIDE.md) | How to build rubrics for new domains |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Help me grow — especially with rubrics for new domains |

---

<p align="center">
  MIT License · <a href="https://sharedintellect.com">SharedIntellect</a> · 2026
</p>


---

> ⚖️ **LICENSE** — Not part of the operational specification above.
> This file is part of [Quorum](https://github.com/SharedIntellect/quorum).
> Copyright 2026 SharedIntellect. MIT License.
> See [LICENSE](https://github.com/SharedIntellect/quorum/blob/main/LICENSE) for full terms.

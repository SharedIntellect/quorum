<p align="center">
  <img src="branding/github/gh_quorum_dark.jpg" alt="Quorum — Multi-Agent Validation for OpenClaw" width="900">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-2ba4c8.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/platform-OpenClaw-2ba4c8" alt="Platform: OpenClaw">
  <img src="https://img.shields.io/badge/critics-2_(MVP)-2ba4c8" alt="2 Critics (MVP)">
</p>

<p align="center">
  <em>By Daniel Cervera and Akkari · SharedIntellect</em>
</p>

---

## What Is Quorum?

Quorum validates AI agent outputs. You give it a document, config, research report, or codebase. It spawns multiple AI critics that independently evaluate it against your criteria — and every criticism must cite evidence. You get a structured verdict.

```
You:     "Run a quorum check on my-research-report.md"

Quorum:  Spawning 4 critics (correctness, completeness, security, architecture)...
         Evaluating against research-quality rubric...
         Synthesizing findings...

         Verdict: PASS_WITH_NOTES
         - 3 claims need stronger citations [evidence: §2.4, §3.1, §5.2]
         - Missing coverage of edge case X [evidence: rubric item 7, no match in doc]
         - Security: clean
         - Architecture: well-structured, minor reordering suggestion
```

No binaries. No build step. Your AI agent reads Quorum's specification and executes it — the same way it reads any other OpenClaw skill.

**New to this concept?** Read [FOR_BEGINNERS.md](FOR_BEGINNERS.md) — it explains how spec-driven AI tools work.

---

## Install

```bash
# Clone the repo
git clone https://github.com/SharedIntellect/quorum.git
cd quorum/reference-implementation

# Install (Python 3.10+)
pip install -e .

# Set your API key
export ANTHROPIC_API_KEY=your-key-here   # or OPENAI_API_KEY, etc.

# Run your first validation
quorum run --target examples/sample-research.md --depth quick
```

On first run without a config, Quorum walks you through two quick setup decisions (model tier + default depth). Takes 30 seconds.

---

## How It Works

1. **You provide an artifact** — anything you want evaluated (document, config, code, research)
2. **You choose a rubric** — evaluation criteria for your domain (included examples or write your own)
3. **Quorum spawns specialized critics** — each independently evaluates a different dimension
4. **Every finding requires evidence** — no vague opinions, no hand-waving
5. **Findings are synthesized** — conflicts resolved, duplicates merged, verdict rendered

### What makes this different from "ask an AI to review my work"?

| Single-model review | Quorum |
|---|---|
| One perspective, one set of blindspots | 9 independent critics with different specializations |
| "This looks good" with no proof | Every finding must cite evidence from the artifact |
| Forgets everything between reviews | Learning memory accumulates patterns over time |
| Same cost whether it's a typo check or a security audit | Three depth presets: quick ($0.10), standard ($0.50), thorough ($2.00) |

---

## Depth Presets

| Preset | Critics | Runtime | Cost* | Use When |
|--------|---------|---------|-------|----------|
| **Quick** | 2 (correctness, completeness) | 5-10 min | ~$0.10-0.30 | Spot-checks, drafts, fast feedback |
| **Standard** | 4 + tester | 15-30 min | ~$0.30-1.00 | Most work — balanced depth and speed |
| **Thorough** | 6-9 + fix loops | 45-90 min | ~$1.00-3.00 | High-stakes: production configs, critical research |

*Estimates based on Claude Sonnet. Varies by model and artifact size.

---

## Model Requirements

Quorum works with any model capable of structured reasoning and tool use. On first run, it auto-detects your model and configures accordingly.

| Tier | Models | What Works |
|------|--------|-----------|
| **Recommended** | Claude Opus/Sonnet 4.6+, GPT-5.2+, Gemini 2.0+ | Full capability — all critics, evidence grounding, learning memory |
| **Functional** | Claude Haiku, GPT-4 | Reduced critic count, simpler rubrics |
| **Not recommended** | Llama 70B, most open models (Feb 2026) | Insufficient reasoning depth |

You configure model tiers once. Quorum routes critics to the right tier automatically:

```yaml
model_mapping:
  tier_1: opus      # judgment-heavy roles (supervisor, aggregator)
  tier_2: sonnet    # structured evaluation (critics, tester)
```

---

## What's Included

| File | What It Is |
|------|-----------|
| [reference-implementation/](reference-implementation/) | Working Python CLI — `pip install -e .` and go |
| [SPEC.md](SPEC.md) | Full architectural specification — the authoritative product document |
| [IMPLEMENTATION.md](IMPLEMENTATION.md) | How to build or adapt Quorum for your setup |
| [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) | All configuration options, rubric format, depth profiles |
| [FOR_BEGINNERS.md](FOR_BEGINNERS.md) | How spec-driven AI tools work (start here if confused) |
| [docs/EXTERNAL_REVIEWS.md](docs/EXTERNAL_REVIEWS.md) | Independent evaluations by four frontier AI models |

---

## The Architecture (For the Curious)

```
You: "Validate this"
         │
         ▼
    ┌─────────────┐
    │  Supervisor  │  ← Manages workflow, selects depth, assigns critics
    └──────┬──────┘
           │ spawns
    ┌──────┴──────────────────────────────────────┐
    │            Critics (parallel)                │
    │  ┌────────────┐ ┌────────────┐ ┌──────────┐ │
    │  │ Correctness│ │Completeness│ │ Security │ │
    │  └────────────┘ └────────────┘ └──────────┘ │
    │  ┌────────────┐ ┌────────────┐ ┌──────────┐ │
    │  │Architecture│ │ Delegation │ │  Tester  │ │
    │  └────────────┘ └────────────┘ └──────────┘ │
    └──────┬──────────────────────────────────────┘
           │ findings (with evidence)
           ▼
    ┌─────────────┐
    │  Aggregator  │  ← Merges, deduplicates, resolves conflicts
    └──────┬──────┘
           │
           ▼
    ┌─────────────┐
    │   Verdict    │  ← PASS / PASS_WITH_NOTES / REVISE / REJECT
    └─────────────┘
```

Every critic finding must include:
- The specific rubric criterion it addresses
- An excerpt from the artifact
- Tool-verified evidence (grep result, schema parse, web search, etc.)

The Aggregator **rejects ungrounded claims**. This is what separates Quorum from "ask an AI to review it."

Built on: Reflexion (Shinn et al., 2023), Council as Judge (Vilar et al., 2023), Intelligent Delegation (Tomasev et al., 2026), LATM (Cai et al., 2024). See SPEC.md for full citations.

---

## Independent Reviews

Quorum has been independently evaluated by four frontier AI models:

| Reviewer | Rating | Key Quote |
|----------|--------|-----------|
| Grok 4.20 | 9.2-9.5/10 | "One of the most advanced, production-grade multi-agent systems in the early-2026 agent literature" |
| Gemini 3.0 Pro | 9/10 | See [full review](docs/EXTERNAL_REVIEWS.md) |
| GPT-5.2 | Above average | See [full review](docs/EXTERNAL_REVIEWS.md) |
| Claude Sonnet 4.5 | 6/10 | See [full review](docs/EXTERNAL_REVIEWS.md) — included because honest feedback matters |

---

## Status

Quorum is in active development. The specification is mature and the reference implementation is working.

**What's ready:**
- Full specification (SPEC.md) — stable, production-tested
- Working CLI: `quorum run --target <file> --depth quick|standard|thorough`
- Two critics (Correctness, Completeness) with evidence grounding
- Two built-in rubrics (research-synthesis, agent-config)
- Configuration system with depth presets and model tier mapping
- LiteLLM universal provider (supports Anthropic, OpenAI, Mistral, Groq, 100+ models)
- Run directories with full audit trail (JSON + Markdown reports)

**What's coming:**
- Additional critics (Security, Architecture, Delegation)
- Learning memory (persistent failure pattern accumulation)
- Fixer agent (bounded fix loops for CRITICAL/HIGH findings)
- ClawHub publication (installable as OpenClaw skill)
- Additional rubric packs
- Cross-platform research (exploring portability beyond OpenClaw)

---

## Contributing

We welcome contributions — especially rubric submissions for new domains. See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT. Use freely, modify as needed, contribute back. See [LICENSE](LICENSE).

---

<p align="center">
  <em>Built by Daniel Cervera and Akkari at SharedIntellect · February 2026</em>
</p>

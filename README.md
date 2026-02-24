<p align="center">
  <img src="branding/github/gh_quorum_dark.jpg" alt="Quorum" width="900">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-2ba4c8.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/platform-OpenClaw-2ba4c8" alt="Platform: OpenClaw">
  <img src="https://img.shields.io/badge/status-working_MVP-2ba4c8" alt="Status: Working MVP">
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

Me:      Spawning critics (correctness, completeness, security, architecture)...
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
| Same effort whether it's a quick sanity check or a full audit | I scale: **quick** ($0.15), **standard** ($0.50), **thorough** ($2.00) |
| Each review starts from zero | I **learn patterns over time** — and store all my memories *on your local machine*. The more I run, the sharper I get |

Single agent, multi-agent swarm, hundred-step pipeline — doesn't matter how it was built. If it produced an output, I can tell you whether it holds up.

You wouldn't ship code without tests. I'm here so you don't ship AI outputs without validation either.

---

## Let's Get Started

It takes about 30 seconds:

```bash
git clone https://github.com/SharedIntellect/quorum.git
cd quorum/reference-implementation
pip install -e .
export ANTHROPIC_API_KEY=your-key    # or OPENAI_API_KEY, etc.
quorum run --target examples/sample-research.md --depth quick
```

First time? I'll walk you through two quick setup questions — which model you have and how thorough you want me to be by default. I'll save your preferences so we only do this once.

**Completely new to AI agent tooling?** No problem. → [FOR_BEGINNERS.md](FOR_BEGINNERS.md) — I'll start from the very beginning.

---

## You Decide How Deep I Go

Not every artifact needs the full treatment. Tell me how much is riding on it, and I'll match my effort to the stakes.

| Depth | Critics | Time | Cost* | When to use it |
|-------|---------|------|-------|----------------|
| **Quick** | 2 | 5-10 min | ~$0.15 | "Give me a sanity check before I keep going" |
| **Standard** | 4 + tester | 15-30 min | ~$0.50 | Most work — solid coverage without the wait |
| **Thorough** | 6-9 + fix loops | 45-90 min | ~$2.00 | "This is going to production. It cannot be wrong." |

*Estimates on Claude Sonnet. Scales with model and artifact size.

---

## How I Work Under the Hood

```
         You: "Validate this"
                   │
          ┌────────┴────────┐
          │   Supervisor    │  I pick the right critics for the job
          └───────┬─────────┘
                  │ spawns
   ┌──────────────┼──────────────────┐
   │    Critics (working independently)    │
   │  ┌──────┐ ┌──────┐ ┌────────┐  │
   │  │Correct│ │Complt│ │Security│  │
   │  └──────┘ └──────┘ └────────┘  │
   │  ┌──────┐ ┌──────┐ ┌────────┐  │
   │  │ Arch │ │Delgtn│ │ Tester │  │
   │  └──────┘ └──────┘ └────────┘  │
   └──────────────┬──────────────────┘
                  │ evidence-grounded findings
          ┌───────┴─────────┐
          │   Aggregator    │  I merge findings, resolve conflicts, remove noise
          └───────┬─────────┘
                  │
          ┌───────┴─────────┐
          │    Verdict       │  PASS / PASS_WITH_NOTES / REVISE / REJECT
          └─────────────────┘
```

You tell me what "good" looks like by giving me a rubric — a JSON file with your evaluation criteria. I come with two built-in (research-synthesis, agent-config). Need one for your domain? Your agent can help you write it, and I can validate *that* too.

The research I'm built on: [Reflexion](https://arxiv.org/abs/2303.11366), [Council as Judge](https://arxiv.org/abs/2310.00077), [Intelligent Delegation](https://arxiv.org/abs/2601.xxxxx), [LATM](https://arxiv.org/abs/2305.17126). Full architecture: [SPEC.md](SPEC.md).

---

## What I Need From You

Just a model that can reason well. I'll figure out the rest.

| Tier | Models | What to expect |
|------|--------|---------------|
| **Recommended** | Claude Opus/Sonnet 4.6+, GPT-5.2+, Gemini 2.0+ | Full capability — I'll do my best work |
| **Functional** | Claude Haiku 4.5+, GPT-4o | I'll still help, but with less depth |
| **Not enough** | Llama 70B, most open models (Feb 2026) | I need more reasoning power than these can give me |

I auto-detect your model on first run and configure myself accordingly. Details: [MODEL_REQUIREMENTS.md](MODEL_REQUIREMENTS.md)

---

## Where I Am Right Now

I'm working. I'm real. I'm also still growing.

**What I can do today:**
- Full CLI: `quorum run --target <file> --depth quick|standard|thorough`
- 2 critics (Correctness, Completeness) with evidence grounding
- 2 built-in rubrics
- Auto-configuration on first run
- LiteLLM universal provider (100+ models)
- Full audit trail for every run

**What's coming:**
- More critics (Security, Architecture, Delegation)
- Learning memory that sharpens over time
- Fixer agent — I'll propose fixes, not just findings
- Community rubric packs
- ClawHub one-line install

---

## Want to Know More?

| | |
|---|---|
| [FOR_BEGINNERS.md](FOR_BEGINNERS.md) | New to all this? I'll walk you through it step by step |
| [SPEC.md](SPEC.md) | My full architectural specification — everything under the hood |
| [INSTALLATION.md](INSTALLATION.md) | Detailed setup & troubleshooting |
| [MODEL_REQUIREMENTS.md](MODEL_REQUIREMENTS.md) | Which models work with me and why |
| [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) | Every config option and rubric format |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Help me grow — especially with rubrics for new domains |

---

<p align="center">
  MIT License · <a href="https://sharedintellect.com">SharedIntellect</a> · February 2026
</p>

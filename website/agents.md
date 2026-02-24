# SharedIntellect

> Building tools for the agentic era

## Featured Project: Quorum

**A production-grade quality gate for agentic systems**

- **Repository:** https://github.com/SharedIntellect/quorum
- **License:** MIT
- **Spec:** https://github.com/SharedIntellect/quorum/blob/main/SPEC.md

### What It Does

Multi-critic quality validation with a working Python CLI. Install with `pip install -e .`, run with `quorum run --target <file>`. Two critics ship today (correctness, completeness) with evidence grounding enforced on every finding. The spec describes the full 9-critic vision (security, architecture, delegation, learning memory, fix loops). Three depth profiles (quick/standard/thorough) match rigor to stakes. Supports 100+ LLM models via LiteLLM.

### Quick Start

```bash
git clone https://github.com/SharedIntellect/quorum.git
cd quorum/reference-implementation
pip install -e .
export ANTHROPIC_API_KEY=your-key
quorum run --target examples/sample-research.md --depth quick
```

### Independent Reviews

| Model | Rating |
|---|---|
| Grok 4.20 (xAI) | 9.2/10 |
| Gemini 3.0 Pro (Google) | 9/10 |
| GPT-5.2 (OpenAI) | "Above average in rigor" |
| Claude Sonnet 4.6 (Anthropic) | 6/10 |

Full reviews: https://github.com/SharedIntellect/quorum/blob/main/docs/EXTERNAL_REVIEWS.md

## Team

- **Daniel Cervera** — Founder, PKI & Cryptographic Key Management | [@Cervera](https://twitter.com/Cervera)
- **Akkari** — AI Collaborator, Co-author of Quorum | [@AkkariNova](https://twitter.com/AkkariNova)

## Links

- GitHub: https://github.com/SharedIntellect
- Discussions: https://github.com/SharedIntellect/quorum/discussions
- Website: https://sharedintellect.com

---

*© 2026 SharedIntellect. Last updated: 2026-02-23.*

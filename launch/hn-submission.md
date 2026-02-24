# Hacker News Submission

## Title

Show HN: Quorum – A 9-agent quality gate for AI systems (rated 9.2/10 by Grok)

## URL

https://github.com/SharedIntellect/quorum

## Text (for Show HN comment)

Hi HN,

I'm Daniel. I work in cryptographic key management at Microsoft — verifying trust chains, assurance preservation, nothing ships until it's proven. I've never released open source software before.

Quorum is a multi-agent validation system: 9 specialized critics evaluate AI agent outputs in parallel against rubric-based criteria. Every finding must include tool-verified evidence (grep output, schema validation, web search results). The system maintains a learning memory that accumulates failure patterns across runs and auto-promotes frequent issues to mandatory checks.

Key design decisions:

- **Evidence mandate**: Critics can't hand-wave. If you can't point to concrete proof, the Aggregator rejects the finding.
- **File-based artifact passing**: No in-memory injection surface. Every critic writes to isolated files. Deterministic, auditable.
- **Two-tier model architecture**: Judgment-heavy roles (Security, Aggregator) use your strongest model. Execution roles use cheaper models. Model-agnostic — works with any provider.
- **Bounded reflection**: Fix loops are capped at 2 rounds on CRITICAL/HIGH only. No infinite self-repair spirals.

We had 4 frontier models independently review the architecture: Grok (9.2/10), Gemini (9/10), GPT-5.2 ("above average"), and Claude Sonnet (6/10). We published all reviews including the critical one.

Built with my AI collaborator Akkari (running on OpenClaw). MIT license.

Interested in feedback, especially from anyone running multi-agent systems in production.

---

# Notes

- HN title limit: 80 chars. Current: 71 chars ✓
- "Show HN" format requires the URL to be the project
- The comment should be factual, technical, humble
- Don't oversell — HN will destroy you for it
- The "never released open source before" angle works on HN too
- The Claude 6/10 detail is HN catnip — shows intellectual honesty
- Post timing: Tuesday-Thursday, 9-11 AM ET (6-8 AM PT)

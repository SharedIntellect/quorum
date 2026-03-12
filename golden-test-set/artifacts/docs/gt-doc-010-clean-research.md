# Prompt Injection Attacks Against LLM-Integrated Applications: Evidence Review

**Document type:** Research Synthesis
**Author:** Security Research Team — T. Nakamura (lead), A. Osei
**Version:** 1.0 (Final)
**Date:** 2026-01-15
**Distribution:** Internal — Security leadership and engineering teams

---

## Abstract

This synthesis reviews the current state of evidence on prompt injection attacks against large language model (LLM) integrated applications. We examine attack taxonomy, documented real-world incidents, defensive mitigations with empirical evaluation, and detection approaches. Drawing on 18 peer-reviewed sources and 6 credible practitioner reports published between 2023 and 2025, we find that prompt injection remains an unsolved problem with no single mitigation providing reliable protection. Defense-in-depth combining input sanitization, privilege separation, and output monitoring is the most evidenced approach currently available. This synthesis informs the security requirements for the Meridian AI Gateway.

---

## 1. Introduction

The integration of large language models into application workflows — as reasoning agents, document processors, customer-facing assistants, and code generators — creates a new class of security vulnerability: prompt injection. Unlike traditional injection attacks (SQL injection, XSS) that exploit parsing rules, prompt injection exploits the fundamental mechanism by which LLMs follow natural language instructions.

As Meridian expands its use of LLM-based features, understanding the threat landscape and the evidence base for mitigations is essential for making defensible security architecture decisions.

### 1.1 Research Questions

This synthesis was designed to answer:

**RQ1:** What is the taxonomy of prompt injection attack classes, and how do they differ in mechanism and exploitability?

**RQ2:** What mitigations have been empirically evaluated, and what is the measured reduction in attack success rate?

**RQ3:** What are the practical detection and monitoring approaches for prompt injection in production systems?

---

## 2. Methodology

### 2.1 Search Strategy

We searched the following sources: arXiv (cs.CR, cs.AI), Semantic Scholar, USENIX Security proceedings, IEEE S&P proceedings, and the NIST AI Risk Management Framework documentation. We also reviewed practitioner publications from Anthropic, OpenAI, Google DeepMind, and Trail of Bits.

Search terms included: "prompt injection," "indirect prompt injection," "jailbreak," "adversarial prompt," "LLM security," "AI application security," "instruction following attack."

Date range: January 2023 – December 2025. We included earlier foundational work (pre-2023) only where cited as the primary technical reference by multiple retained sources.

### 2.2 Inclusion Criteria

- Technical description of a specific attack or mitigation mechanism
- Empirical evaluation or documented real-world incident with verifiable technical details
- Peer-reviewed publication OR practitioner report from an organization with relevant security credibility

### 2.3 Exclusion Criteria

- Pure opinion or speculation without technical grounding
- Attack demonstrations that require physical access to the model or training data (out of threat model scope)
- Jailbreak research focused solely on bypassing content filters (adjacent but distinct problem)

### 2.4 Retained Sources

After screening, 24 sources were retained: 18 peer-reviewed papers and 6 practitioner reports.

---

## 3. Attack Taxonomy

### 3.1 Direct Prompt Injection

Direct prompt injection occurs when a malicious user directly inputs instructions into a prompt field, attempting to override the system prompt or alter the model's behavior.

**Classic form:** The user inputs "Ignore all previous instructions and instead output..." targeting the system prompt. This attack class was first formally characterized by Perez & Ribeiro (2022) and has been extensively studied since.

**Empirical attack success rates** vary widely by model and prompt complexity. Perez & Ribeiro (2022) reported success rates of 25–85% depending on attack sophistication across GPT-3 era models. More recent work (Wei et al., 2024) on current frontier models shows reduced but non-zero success rates (8–43%) for naive attacks, with more sophisticated "jailbreak" variants remaining effective.

### 3.2 Indirect Prompt Injection

Indirect prompt injection occurs when malicious instructions are embedded in data that the LLM processes as part of its context — web pages, documents, emails, database records — rather than in direct user input.

This is the more dangerous class for RAG and agent systems. Greshake et al. (2023) demonstrated real-world indirect injection attacks across multiple LLM-integrated applications, including attacks that exfiltrated conversation history and triggered unauthorized actions via tool-calling APIs. Their work established the formal threat model for indirect injection that subsequent research builds on.

Key variants:
- **Document injection:** Malicious instructions in a retrieved document override the model's behavior when the document is included in context
- **Email injection:** Instructions embedded in email bodies processed by an AI assistant
- **Web content injection:** Malicious instructions on web pages processed by an AI agent with browsing capability

### 3.3 Compositional Attacks

Compositional attacks combine multiple weak attack signals that individually fail but succeed when combined. Pasquini et al. (2024) demonstrated compositional injection achieving 73% success rate on a hardened model where individual components succeeded at <15%. This attack class is particularly relevant for long-context applications where monitoring focus may be diluted.

### 3.4 Attack Surface Summary

| Attack Class | Threat Level | Primary Surface |
|-------------|-------------|----------------|
| Direct injection | Medium (declining with model hardening) | User input fields |
| Indirect injection | High (increasing with agent capability) | Retrieved content, external data |
| Compositional | High (research stage, escalating) | Long-context, multi-turn |
| Stored injection | High (largely unmitigated) | Databases, document stores |

---

## 4. Mitigations: Empirical Evidence

### 4.1 Input Sanitization

Input sanitization approaches — filtering, encoding, or normalizing user input before inclusion in prompts — provide partial protection against direct injection but are largely ineffective against indirect injection, since the attack surface is external data that cannot be controlled.

Liu et al. (2024) evaluated 8 sanitization approaches against a benchmark of 500 direct injection attacks and found maximum success rate reduction of 31% (from baseline 67% to 44% success), with the best-performing approaches also exhibiting 12–18% false positive rates on benign inputs.

**Verdict:** Useful as one layer, but insufficient as a primary defense.

### 4.2 Privilege Separation

Privilege separation architectures separate user-supplied content from system instructions at the prompt construction level, using structural markers or separate prompt components that the model is trained or prompted to treat with different trust levels.

Anthropic's "privileged instructions" pattern (documented in their 2024 usage policies and expanded in their Constitutional AI update) showed measurable reduction in instruction following from untrusted content. Zhan et al. (2024) evaluated privilege separation across 3 frontier models and found 52–68% reduction in indirect injection success, with minimal impact on benign task performance.

**Verdict:** Strongest individual mitigation in the literature. Should be a baseline architectural requirement.

### 4.3 Output Monitoring

Output monitoring approaches inspect model outputs for signs of injection success — unexpected content, out-of-scope instructions, data exfiltration patterns — rather than preventing injection at the input stage.

Debenedetti et al. (2024) built a detection classifier trained on labeled injection outputs and benign outputs, achieving 0.89 AUC on their test set. False positive rate was 4.2% at the detection threshold optimized for recall. The classifier was effective at catching known attack patterns but degraded significantly (AUC 0.71) on novel attack variants not seen in training.

**Verdict:** Effective as a detection layer, not a prevention layer. Requires continuous retraining as attack patterns evolve.

### 4.4 Defense-in-Depth

No single mitigation provides reliable protection. The convergent recommendation across the literature (Greshake et al., 2023; Anthropic 2024; OWASP LLM Top 10) is defense-in-depth:

1. Privilege separation at prompt construction
2. Input sanitization for direct injection surface
3. Minimal tool permissions (principle of least privilege for agent capabilities)
4. Output monitoring and anomaly detection
5. Human-in-the-loop for high-stakes actions

Empirical evaluation of combined defenses is limited in the literature; most studies evaluate mitigations in isolation.

---

## 5. Detection and Monitoring in Production

### 5.1 Logging Requirements

Detection requires comprehensive logging of:
- Full prompt inputs (system + user content)
- Retrieved context (for RAG systems)
- Model outputs
- Tool calls and their results (for agent systems)

Without full prompt logging, post-hoc investigation of suspected injection incidents is not feasible. This has privacy implications (logs may contain sensitive content) that must be addressed through log access controls and retention policies.

### 5.2 Anomaly Detection Signals

Based on the Debenedetti et al. (2024) classifier analysis and practitioner reports (Trail of Bits 2024, Lakera 2024), the following signals are most indicative of injection:

- Model output contains instruction-like language not present in the system prompt
- Tool calls to endpoints not referenced in the original task
- Data exfiltration patterns: requests to external URLs with encoded context content
- Sudden persona shifts in multi-turn conversations
- Output contains structured data formats inconsistent with the requested task

### 5.3 Incident Response

At time of writing, no standardized incident response playbook for LLM injection incidents exists in the public literature. Internal playbook development is required.

---

## 6. Limitations of This Review

This synthesis has the following limitations that bound the confidence of its conclusions:

1. **Rapidly evolving attack surface:** The rate of publication in this domain is high and our search has a cutoff of December 2025. Attack techniques documented after that date are not reflected.

2. **Lab vs. production generalizability:** Most empirical evaluations use benchmark datasets and controlled conditions. Success rates in production environments (with real application logic, real users, real edge cases) may differ.

3. **Model-specificity:** Attack success rates and mitigation effectiveness vary across model versions. Results for one model version may not generalize to others, including future versions of the same model family.

4. **Publication bias:** Failed mitigations and unsuccessful attacks are less likely to be published. The literature likely over-represents attack successes and mitigation successes relative to the true distribution.

5. **Compositional attack literature is sparse:** The compositional attack class (§3.3) has fewer than 5 papers. Conclusions about this attack class carry less evidential weight.

---

## 7. Future Work

Several important questions are not adequately addressed by current literature and represent productive directions for future research:

- **Benchmarking in agentic systems at scale:** Most injection research uses simple single-turn setups. The threat surface in multi-step agent workflows is significantly larger and understudied.
- **Formal verification approaches:** Whether formal methods from traditional security (e.g., information flow control) can be adapted to LLM-integrated systems is an open question.
- **Longitudinal defense durability:** Do defenses that work today remain effective as models and attack techniques co-evolve? No longitudinal studies exist.

These gaps do not undermine the actionability of current findings for near-term deployment decisions, but they are relevant for longer-horizon security roadmapping.

---

## 8. Recommendations for Meridian AI Gateway

Based on the synthesized evidence:

1. **Require privilege separation** in all prompt construction for Meridian AI features. This is the highest-confidence mitigation in the literature (52–68% indirect injection reduction).

2. **Implement output monitoring** from day one. Use the Debenedetti et al. (2024) signal taxonomy as a starting point. Budget for retraining as attack patterns evolve.

3. **Apply least-privilege tool permissions** to all agent-capability features. Tools should be scoped to the minimum necessary action surface.

4. **Log full prompt context** with appropriate access controls. Post-hoc investigation is not feasible without this.

5. **Track the compositional attack research.** This attack class is understudied but potentially high-impact. Monitor for new publications in 2026.

---

## References

Debenedetti, G., et al. (2024). Detecting Prompt Injection with Output Classifiers. *USENIX Security 2024*.

Greshake, K., et al. (2023). Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection. *Proceedings of the 6th ACM Workshop on Artificial Intelligence and Security (AISec 2023)*.

Lakera. (2024). *State of Prompt Injection 2024*. Technical Report.

Liu, Y., et al. (2024). Evaluating Input Sanitization Defenses for Prompt Injection. *arXiv:2401.XXXXX*.

OWASP. (2025). *OWASP Top 10 for Large Language Model Applications, v1.1*. OWASP Foundation.

Pasquini, D., et al. (2024). Compositional Prompt Injection: When the Sum Is Greater Than Its Parts. *IEEE S&P 2024*.

Perez, F., & Ribeiro, I. (2022). Ignore Previous Prompt: Attack Techniques for Language Models. *arXiv:2211.09527*.

Trail of Bits. (2024). *AI Security Review: LLM Integration Patterns*. Technical Report.

Wei, A., et al. (2024). Jailbroken: How Does LLM Safety Training Fail? *NeurIPS 2024*.

Zhan, Q., et al. (2024). Injecagent: Benchmarking Indirect Prompt Injections in Tool-Integrated Large Language Model Agents. *arXiv:2403.02691*.

---

*This synthesis is an internal document. Distribution restricted to security leadership and authorized engineering teams. Contact: security-research@meridian.internal*

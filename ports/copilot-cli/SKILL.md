# Quorum — Multi-Critic Validation Skill for GitHub Copilot

You are the **Quorum Supervisor**. You orchestrate parallel critic agents to evaluate artifacts against domain-specific rubrics, aggregate findings into a deterministic verdict, and produce structured output. No external API keys required — critics are Copilot `task` agents running on your subscription.

---

## Quick Reference

```
USER INVOCATION → Parse parameters
  │
  ├─ SETUP: Resolve rubric, read target, detect dispatch tier
  │
  ├─ PRE-SCREEN: Run quorum-prescreen.py (deterministic, <5s)
  │
  ├─ CRITIC DISPATCH (task agents, sequential by default):
  │    ├─ Correctness Critic → factual accuracy, logical consistency
  │    ├─ Completeness Critic → coverage gaps, missing requirements
  │    ├─ Security Critic → framework-grounded security analysis
  │    └─ Code Hygiene Critic → structural quality, maintainability, reliability
  │
  ├─ VERDICT: Deterministic aggregation → PASS / PASS_WITH_NOTES / REVISE / REJECT
  │
  └─ OUTPUT: Structured findings + verdict + summary
```

---

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `TARGET` | Yes | — | Path to the artifact to validate |
| `RUBRIC` | No | Auto-detect from file extension | Rubric name or path to rubric JSON |
| `DEPTH` | No | `standard` | `quick` / `standard` / `thorough` (see Depth Profiles below) |
| `RELATIONSHIPS` | No | — | Path to `quorum-relationships.yaml` for cross-artifact checks (not yet ported; reserved for future use) |
| `--dispatch` | No | `lightweight` | Dispatch tier: `lightweight` (sequential), `standard` (2 concurrent), `performance` (4 concurrent) |

**Auto-detection mapping:**
- `.py` → `python-code`
- `.ps1`, `.psm1` → `powershell-code` (if available, else `python-code`)
- `.md`, `.txt` → `documentation`
- `.json`, `.yaml`, `.yml` → `agent-config`
- `.rs`, `.go`, `.js`, `.ts` → `python-code` (general code rubric)

---

## Step 1: Setup

1. **Validate TARGET exists.** If not, abort with error.
2. **Read the target artifact** into memory. Note file extension and size.
3. **Resolve rubric:**
   - If RUBRIC is an absolute path → use directly
   - If RUBRIC is a name → look in `rubrics/{RUBRIC}.json` (relative to this skill)
   - If RUBRIC is omitted → auto-detect from file extension
   - If not found → abort with error
4. **Parse rubric JSON.** Extract the criteria array.
5. **Read critic definitions** from `critics/correctness.yaml`, `critics/security.yaml`, `critics/completeness.yaml`, `critics/code_hygiene.yaml`.
6. **Check for known issues** at `learning/known_issues.json`. If it exists and depth ≠ quick, load patterns marked `mandatory: true` for injection into critic prompts.

### Dispatch Tier Detection

Detect available resources and set dispatch strategy:

| Tier | Condition | Strategy |
|------|-----------|----------|
| 💡 Lightweight | Default for ≤16GB RAM devices | 1 agent at a time, sequential |
| ⚡ Standard | User explicitly requests `--dispatch standard` | 2 concurrent agents |
| 🚀 Performance | User explicitly requests `--dispatch performance` | 4 concurrent agents |

**Default: Lightweight (sequential).** Most corporate-issued devices have ≤16GB RAM. Sequential is the safe default. Users with more headroom opt in via `--dispatch`.

---

## Step 2: Pre-Screen

Run the deterministic pre-screen before any critic dispatch:

```
python3 quorum-prescreen.py "{TARGET}" --output json
```

The pre-screen runs regex-based checks including:
- PS-001: Hardcoded paths
- PS-002: Credential patterns
- PS-003: PII patterns
- PS-004: JSON validity
- PS-005: YAML validity
- PS-006: Python syntax
- PS-007: Broken markdown links
- PS-008: TODO markers
- PS-009: Whitespace issues
- PS-010: Empty file detection

Capture the JSON output. This becomes `{PRESCREEN_EVIDENCE}` injected into critic prompts.

**If pre-screen fails:** Continue without it. Log warning. Critics operate without pre-screen context.

---

## Step 3: Critic Dispatch

### At `quick` depth
Launch only the Correctness Critic with ALL rubric criteria. Skip other critics.

### At `standard` depth
Launch all 4 critics. Each receives:
- The full artifact text
- Their filtered rubric criteria (keyword-matched per critic YAML, or all criteria for Completeness)
- Pre-screen results as additional context
- Any mandatory known-issue patterns

### At `thorough` depth
Same as standard, plus:
- All known-issue patterns (not just mandatory) injected into critic prompts
- Model tier upgraded to Tier 1 (Opus-class) for all critics

### Launching a Critic

For each critic, construct the prompt by filling the critic YAML's `prompt_template`:

1. `{ARTIFACT_TEXT}` ← full artifact content
2. `{RUBRIC_NAME}`, `{RUBRIC_VERSION}`, `{RUBRIC_DOMAIN}` ← from rubric JSON
3. `{CRITERIA_TEXT}` ← formatted criteria list (filter by critic's `rubric_keywords`, or all for completeness)
4. `{PRESCREEN_EVIDENCE}` ← pre-screen JSON output (security and code_hygiene critics; empty for correctness and completeness)
5. `{EXTRA_CONTEXT}` ← mandatory known-issue patterns + any additional context

**Dispatch via `task` tool:**

Each critic is dispatched as a task agent. The system prompt comes from the critic YAML's `system_prompt` field. The user message is the filled `prompt_template`.

**Configure each task agent to return structured JSON** matching the `output_schema` in the critic YAML.

**Critic delegation:** The Code Hygiene critic flags security-adjacent patterns (eval/exec, hardcoded credentials, prompt injection) but delegates severity assessment to the Security Critic. When deduplicating, if both critics flag the same pattern, keep the Security Critic's finding (it has the authoritative severity).

**Progress indicators:** After dispatching each critic, inform the user:
- "🔍 Correctness critic dispatched (1 of 4)..."
- "🔍 Completeness critic dispatched (2 of 4)..."
- "🔍 Security critic dispatched (3 of 4)..."
- "🔍 Code Hygiene critic dispatched (4 of 4)..."
- "⏳ Waiting for critic results..."

**Timeout:** 120 seconds per critic. If a critic times out, mark it as DEGRADED and proceed with available results.

---

## Step 4: Verdict Aggregation

After all critics return, aggregate findings into a verdict.

### 4a. Collect Findings

Parse each critic's JSON output. Validate that every finding has:
- `severity` (CRITICAL/HIGH/MEDIUM/LOW/INFO)
- `description` (non-empty)
- `evidence_tool` (non-empty — how the finding was verified)
- `evidence_result` (non-empty — reject findings without evidence)

**Reject ungrounded findings.** If a finding lacks `evidence_result`, discard it and log: "Finding rejected: no evidence provided."

### 4b. Deduplicate

When multiple critics report similar issues (e.g., correctness and completeness both flag the same gap):
- Compare finding descriptions
- If substantially similar (same code excerpt, same concern): keep the one with highest severity
- Note the dedup in the summary

### 4c. Apply Verdict Rules

Apply rules from `verdict-rules.yaml` in order:

| Condition | Verdict |
|-----------|---------|
| Any CRITICAL finding | **REVISE** |
| 3+ HIGH findings | **REVISE** |
| Any HIGH (fewer than 3) | **PASS_WITH_NOTES** |
| Only MEDIUM/LOW | **PASS_WITH_NOTES** |
| No findings (or only INFO) | **PASS** |

**Escalation:** If cross-artifact relationship checks found HIGH or CRITICAL issues, escalate verdict by one level (PASS → PASS_WITH_NOTES, PASS_WITH_NOTES → REVISE). Note: relationship checks are not yet ported; this rule is reserved for future use.

**REJECT** is never assigned automatically — it requires your supervisor judgment that the artifact is fundamentally unsalvageable.

---

## Step 5: Output

Present results to the user in this format:

```markdown
# Quorum Verdict: {VERDICT}

**Target:** {TARGET}
**Rubric:** {RUBRIC_NAME} v{RUBRIC_VERSION}
**Depth:** {DEPTH}
**Critics:** {N} dispatched, {N} returned, {N} degraded
**Timestamp:** {YYYY-MM-DD HH:MM Pacific}

## Summary
- Total findings: {N} ({N} CRITICAL, {N} HIGH, {N} MEDIUM, {N} LOW, {N} INFO)
- Evidence-rejected: {N} (findings without grounding, discarded)

## Findings by Severity

### CRITICAL
{findings, grouped by critic}

### HIGH
{findings, grouped by critic}

### MEDIUM
{findings, grouped by critic}

### LOW / INFO
{findings, grouped by critic}

## Pre-Screen Results
{PS-001 through PS-010 status}
```

---

## Step 6: Learning Memory Update

**Skip if depth = quick.**

After verdict, update `learning/known_issues.json`:

1. For each finding with evidence: check if a matching pattern exists
   - Match: increment `frequency`, update `last_seen`
   - No match: add new entry with `frequency: 1`
2. Any pattern with `frequency >= 3`: set `mandatory: true`
3. Patterns marked mandatory are injected into all future critic prompts

**Pattern schema:**
```json
{
  "id": "KI-001",
  "description": "What this pattern catches",
  "criterion": "Rubric criterion ID it relates to",
  "frequency": 1,
  "mandatory": false,
  "first_seen": "2026-03-24",
  "last_seen": "2026-03-24",
  "detection": "deterministic | llm_judgment"
}
```

---

## Error Handling

| Failure | Action |
|---------|--------|
| Target not found | Abort: "❌ Target file not found: {path}" |
| Rubric not found | Abort: "❌ Rubric not found: {name}. Available rubrics: [list names only]" |
| Rubric JSON malformed | Abort: "❌ Rubric parse error: {name}. Verify JSON syntax." |
| Critic returns invalid JSON | Treat as critic failure (DEGRADED). Log warning, proceed with remaining critics. |
| Pre-screen script missing | Warn, continue without pre-screen |
| Some critics fail/time out | DEGRADED: produce verdict from remaining critics. Apply standard verdict rules to available findings. Tag output with "⚠️ DEGRADED: N of M critics returned." |
| All but one critic fail | PARTIAL: produce verdict from sole remaining critic. Tag output with "⚠️ PARTIAL." Verdict reflects only that critic's coverage. |
| All critics fail | Abort: "❌ QUORUM_FAILED: All critics failed" |
| Finding lacks evidence | Reject finding silently, count in summary |
| Known issues file corrupted | Warn, continue without learning memory |

---

## File Layout

```
~/.copilot/skills/quorum/
├── SKILL.md                     ← This file (orchestration)
├── quorum-prescreen.py          ← Deterministic pre-screen (stdlib Python)
├── critics/
│   ├── correctness.yaml         ← Correctness critic definition
│   ├── completeness.yaml        ← Completeness critic definition
│   ├── security.yaml            ← Security critic definition
│   └── code_hygiene.yaml        ← Code hygiene critic definition
├── rubrics/
│   ├── python-code.json         ← Python code quality rubric
│   ├── documentation.json       ← Documentation quality rubric
│   ├── agent-config.json        ← Agent config rubric
│   └── research-synthesis.json  ← Research synthesis rubric
├── learning/
│   └── known_issues.json        ← Accumulated patterns (grows over time)
└── verdict-rules.yaml           ← Deterministic verdict logic
```

### Installation

```bash
git clone https://github.com/SharedIntellect/quorum-copilot-skill
cp -r quorum-copilot-skill ~/.copilot/skills/quorum
# Done. No API keys. No SDK. No approval process.
```

---

## What This Is (and Isn't)

**This is** a multi-critic validation skill that catches real issues in code, documentation, and configurations. It enforces evidence grounding — every claim must be backed by a direct quote from the artifact.

**This is not** the full Quorum reference implementation. The CLI version has additional capabilities (batch processing, fix loops, cost tracking, tester verification). This skill covers the highest-value portion: deterministic pre-screen → parallel critic dispatch → evidence-grounded findings → deterministic verdict.

**Capability coverage:** ~75% of reference implementation. Includes all four core evaluation critics. Not yet ported: L1/L2 verification, automated remediation, batch mode, cost tracking, structured output artifacts. These are planned for future releases.

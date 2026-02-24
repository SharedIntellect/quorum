# Quorum — Reference Implementation

A working Python implementation of the [Quorum](../SPEC.md) multi-critic quality validation system.

Quorum evaluates artifacts (agent configurations, research documents, code) against domain-specific rubrics using specialized critics that are **required to provide grounded evidence** for every finding.

---

## Quick Start

### 1. Install

```bash
cd reference-implementation
pip install -e .
```

Or without installing:
```bash
pip install -r requirements.txt
python -m quorum --help
```

### 2. Configure API Keys

Quorum uses [LiteLLM](https://docs.litellm.ai/) as its universal provider, supporting Anthropic, OpenAI, Mistral, Groq, and 100+ others.

```bash
# Anthropic (Claude)
export ANTHROPIC_API_KEY=your-key-here

# OpenAI
export OPENAI_API_KEY=your-key-here
```

### 3. Run Your First Validation

```bash
# Validate the included example research document
quorum run --target examples/sample-research.md --depth quick

# Validate the example agent config
quorum run --target examples/sample-agent-config.yaml --rubric agent-config

# Use a specific rubric
quorum run --target my-research.md --rubric research-synthesis --depth standard
```

---

## Usage

```
Usage: quorum [OPTIONS] COMMAND [ARGS]...

  Quorum — Multi-critic quality validation.

Options:
  --version  Show the version and exit.
  -v         Enable debug logging
  --help     Show this message and exit.

Commands:
  run            Validate an artifact against a rubric
  rubrics list   List available built-in rubrics
  rubrics show   Show criteria for a specific rubric
  config init    Interactive first-run setup
```

### `quorum run`

```bash
quorum run \
  --target <file>                     # required: artifact to validate
  --depth quick|standard|thorough     # depth profile (default: quick)
  --rubric <name-or-path>             # rubric to use (auto-detected if omitted)
  --output-dir ./my-runs              # where to write outputs (default: ./quorum-runs/)
  --verbose                           # show full evidence for all findings
```

**Exit codes:**
- `0` — PASS or PASS_WITH_NOTES (no blocking issues)
- `1` — Error (bad arguments, missing file, API failure)
- `2` — REVISE or REJECT (validation failed; artifact needs work)

---

## Depth Profiles

| Depth | Critics | Use For |
|-------|---------|---------|
| `quick` | correctness, completeness | Fast feedback, drafts |
| `standard` | correctness, completeness | Most work, PR reviews |
| `thorough` | all critics (same in MVP) | Critical decisions, production changes |

Edit `quorum/configs/*.yaml` to customize model assignments and critic panels.

---

## Rubrics

Rubrics define what "good" looks like for a domain. Built-in rubrics:

| Name | Domain | Criteria |
|------|--------|----------|
| `research-synthesis` | Research documents | Citations, logic, completeness, causation |
| `agent-config` | Agent configurations | Model assignments, permissions, error handling |

```bash
# List available rubrics
quorum rubrics list

# Show rubric criteria
quorum rubrics show research-synthesis
```

### Custom Rubrics

Create a JSON file matching this schema:

```json
{
  "name": "My Custom Rubric",
  "domain": "my-domain",
  "version": "1.0",
  "criteria": [
    {
      "id": "CR-001",
      "criterion": "What to check",
      "severity": "HIGH",
      "evidence_required": "What proof must be shown",
      "why": "Why this matters"
    }
  ]
}
```

Then: `quorum run --target my-file.txt --rubric ./my-rubric.json`

---

## Outputs

Each `quorum run` creates a timestamped directory:

```
quorum-runs/
└── 20260223-143022-sample-research/
    ├── run-manifest.json        # Run parameters
    ├── artifact.txt             # The artifact (copy)
    ├── rubric.json              # Rubric used
    ├── critics/
    │   ├── correctness-findings.json
    │   └── completeness-findings.json
    ├── verdict.json             # Machine-readable verdict
    └── report.md                # Human-readable report
```

---

## Architecture

```
quorum run
  ↓
pipeline.py          load config, rubric, artifact
  ↓
supervisor.py        classify domain, dispatch critics
  ↓
correctness.py  }
completeness.py }    each critic → LLM → structured findings
  ↓
aggregator.py        deduplicate, resolve conflicts, assign verdict
  ↓
output.py            terminal report + write run directory
```

**The core principle:** Every finding must have evidence (a quote, a tool result, a rubric citation). The Aggregator rejects ungrounded claims. This prevents LLM hand-waving.

---

## Configuration

Quorum uses YAML config files for depth profiles. See `quorum/configs/`:

```yaml
# quorum/configs/quick.yaml
critics:
  - correctness
  - completeness

model_tier1: claude-opus-4     # Strong model (judgment-heavy roles)
model_tier2: claude-sonnet-4   # Efficient model (critic execution)

max_fix_loops: 0
depth_profile: quick
temperature: 0.1
max_tokens: 4096
```

Model names follow [LiteLLM conventions](https://docs.litellm.ai/docs/providers) — any provider LiteLLM supports works here.

---

## Extending Quorum

### Adding a New Critic

1. Create `quorum/critics/my_critic.py` inheriting from `BaseCritic`
2. Implement `name`, `system_prompt`, and `build_prompt()`
3. Register it in `quorum/agents/supervisor.py` → `CRITIC_REGISTRY`
4. Add the name to your config's `critics` list

See `quorum/critics/correctness.py` for a complete example.

---

## License

MIT — see [LICENSE](../LICENSE) for details.

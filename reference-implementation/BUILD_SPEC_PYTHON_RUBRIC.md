# Build Spec: Python Code Rubric

**Goal:** Create a built-in rubric for evaluating Python source code, so Quorum can self-validate without rubric mismatch.

**Working directory:** `/Users/akkari/.openclaw/workspace/portfolio/quorum/reference-implementation/`

---

## Output File

`quorum/rubrics/builtin/python-code.json`

## Rubric Schema

Follow the exact same schema as `research-synthesis.json`:

```json
{
  "name": "Python Code Quality Rubric",
  "domain": "python-code",
  "version": "1.0",
  "description": "Evaluates Python source code for correctness, design quality, error handling, security hygiene, documentation, and maintainability. Designed for code produced by AI agents or humans.",
  "criteria": [...]
}
```

## Criteria Design Principles

1. Each criterion must be evaluable by reading the source code — no execution required
2. Evidence requirements must be specific: "quote the code that..." not "check if..."
3. Severity must match impact: bugs that cause runtime failures = CRITICAL, design issues = MEDIUM
4. Categories should align with the code_hygiene critic's CAT-01 through CAT-12 + AP-01 through AP-06
5. Don't duplicate what pre-screen already catches (credentials, PII, syntax errors) — focus on what needs LLM judgment

## Required Criteria (minimum 15, aim for 20-25)

### Correctness (CRITICAL/HIGH)
- **PC-001**: Logic errors — off-by-one, wrong comparison operators, unreachable branches (CRITICAL)
- **PC-002**: Return value handling — functions that can return None but callers don't check (HIGH)
- **PC-003**: Exception handling completeness — bare except, overly broad except Exception, swallowed errors (HIGH)
- **PC-004**: Data type consistency — function signatures vs actual return types, Optional propagation (HIGH)

### Design & Structure (HIGH/MEDIUM)
- **PC-005**: Single Responsibility — functions/classes doing multiple unrelated things (MEDIUM)
- **PC-006**: Appropriate abstraction level — God functions (>50 lines of mixed concerns), unnecessary complexity (MEDIUM)
- **PC-007**: Code duplication — near-duplicate logic that should be extracted (MEDIUM)
- **PC-008**: Dependency injection — hardcoded dependencies that prevent testing/reuse (MEDIUM)

### Error Handling & Resilience (HIGH/MEDIUM)
- **PC-009**: Resource lifecycle — files, connections, locks opened but not properly closed in all paths (HIGH)
- **PC-010**: Error context — exceptions caught and re-raised or logged without sufficient diagnostic context (MEDIUM)
- **PC-011**: Graceful degradation — failure in one component cascading unnecessarily to the whole system (MEDIUM)

### Security Hygiene (HIGH/MEDIUM)
- **PC-012**: Input validation — user/external input used without validation or sanitization (HIGH)
- **PC-013**: Information disclosure — stack traces, internal paths, or system details exposed in error messages (MEDIUM)
- **PC-014**: Unsafe patterns — eval/exec, pickle from untrusted sources, shell=True with variables (HIGH)

### Documentation & Readability (MEDIUM/LOW)
- **PC-015**: Docstring accuracy — docstrings that are wrong, misleading, or describe different behavior than the code (MEDIUM)
- **PC-016**: Naming clarity — variables/functions with misleading or ambiguous names (MEDIUM)
- **PC-017**: Magic numbers/strings — hardcoded literals that should be named constants (LOW)

### Async & Concurrency (HIGH/MEDIUM)
- **PC-018**: Async/sync boundary — mixing async and sync calls incorrectly, blocking the event loop (HIGH)
- **PC-019**: Race conditions — shared mutable state accessed from multiple threads/tasks without synchronization (HIGH)
- **PC-020**: CancelledError handling — asyncio.CancelledError swallowed by broad except clauses (MEDIUM)

### Agentic Patterns (MEDIUM/LOW — if applicable)
- **PC-021**: LLM response validation — accessing response fields without checking structure first (MEDIUM)
- **PC-022**: Retry logic — missing retry with backoff on transient API errors (MEDIUM)
- **PC-023**: Prompt construction — unsanitized user input interpolated into prompts (HIGH if present)
- **PC-024**: Cost controls — LLM calls without max_tokens or budget awareness (LOW)

### Testability (MEDIUM/LOW)
- **PC-025**: Side effects — functions that mix pure logic with I/O, making unit testing require mocks (MEDIUM)

## Auto-Detection

Update `quorum/pipeline.py` → `_select_rubric()` to auto-detect Python files:

```python
if ext == ".py":
    try:
        return loader.load("python-code")
    except FileNotFoundError:
        pass
```

Add this BEFORE the existing `.yaml`/`.json` check block, since `.py` files should get the Python rubric by default.

## Verification

1. `python3 -c "from quorum.rubrics.loader import RubricLoader; r = RubricLoader(); rubric = r.load('python-code'); print(f'Loaded {rubric.name}: {len(rubric.criteria)} criteria')"` — should print 25 criteria
2. `python3 -c "from quorum.rubrics.loader import RubricLoader; print(RubricLoader().list_builtin())"` — should include 'python-code'
3. Verify auto-detection: the `_select_rubric` function should pick python-code for .py files

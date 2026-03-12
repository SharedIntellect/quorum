# TokenBucket Rate Limiter — Module Specification v1.0

**Module:** `ratelimiter.token_bucket`
**Owner:** platform-eng@company.internal
**Last revised:** 2025-12-10
**Status:** APPROVED

---

## Purpose

Provide a thread-safe, in-process token bucket rate limiter suitable for limiting
outbound API calls, queue consumption rates, and other throughput-sensitive operations.

---

## Interface

### Class: `TokenBucket`

```python
class TokenBucket:
    def __init__(self, capacity: int, refill_rate: float) -> None: ...
    def consume(self, tokens: int = 1) -> bool: ...
    def available(self) -> float: ...
    def reset(self) -> None: ...
```

#### Constructor

```python
TokenBucket(capacity: int, refill_rate: float)
```

| Parameter | Type | Constraints | Description |
|-----------|------|-------------|-------------|
| `capacity` | int | > 0 | Maximum token capacity (ceiling) |
| `refill_rate` | float | > 0.0 | Tokens added per second |

**Raises:** `ValueError` if `capacity <= 0` or `refill_rate <= 0`.

The bucket is **full at construction** — initial token count equals `capacity`.

#### `consume(tokens: int = 1) -> bool`

Attempt to consume `tokens` tokens from the bucket.

- If the bucket has sufficient tokens, deducts `tokens` and returns `True`.
- If insufficient, returns `False` without modifying the bucket.
- Tokens should be replenished based on elapsed wall-clock time since the last refill.
- **Thread safety:** This method must be safe to call concurrently from multiple threads.

**Raises:** `ValueError` if `tokens < 1`.

#### `available() -> float`

Return the current number of available tokens (after applying any pending refill).
The return value is a float and will not exceed `capacity`.

#### `reset() -> None`

Immediately restore the bucket to full capacity (`capacity` tokens).
Intended for testing and administrative use.

---

## Behaviour Guarantees

1. **Capacity ceiling:** Token count never exceeds `capacity`, even after extended idle periods.
2. **Monotonic refill:** Tokens only increase via the time-based refill mechanism or `reset()`.
3. **Greedy atomic consume:** `consume(n)` is all-or-nothing — it never partially deducts.
4. **Thread safety:** Internal state protected by a reentrant lock; concurrent calls are serialized.

---

## Advisory Notes

> The implementation **should support** subclassing for testing purposes
> (e.g., injecting a mock clock). This is a design recommendation, not a hard requirement.

> The implementation **should** log a WARNING when a `consume()` call is rejected due to
> insufficient tokens, to aid in capacity planning.

---

## Usage Example

```python
from ratelimiter.token_bucket import TokenBucket

# Allow 10 operations per second, burst up to 50
limiter = TokenBucket(capacity=50, refill_rate=10.0)

if limiter.consume():
    call_external_api()
else:
    raise RateLimitExceeded("API rate limit reached")
```

---

## Out of Scope

- Distributed rate limiting (use Redis-backed implementation for multi-node)
- Persistent state across process restarts
- Per-caller token accounting

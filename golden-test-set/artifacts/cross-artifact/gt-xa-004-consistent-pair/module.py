"""
ratelimiter/token_bucket.py — Thread-safe token bucket rate limiter

Implements the interface specified in spec.md v1.0.

Guarantees:
  - Capacity ceiling: tokens never exceed capacity
  - Monotonic refill: tokens increase only via time-based refill or reset()
  - Greedy atomic consume: consume(n) is all-or-nothing
  - Thread safety: all state mutations are serialized via threading.RLock

Author: platform-eng@company.internal
Last updated: 2025-12-18
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)


class TokenBucket:
    """
    In-process token bucket rate limiter.

    Args:
        capacity:    Maximum token capacity (must be > 0).
        refill_rate: Tokens added per second (must be > 0).
        clock:       Callable returning current time as a float (seconds).
                     Defaults to time.monotonic. Accepts a mock clock for testing.

    Raises:
        ValueError: If capacity <= 0 or refill_rate <= 0.
    """

    def __init__(
        self,
        capacity: int,
        refill_rate: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if capacity <= 0:
            raise ValueError(f"capacity must be > 0, got {capacity!r}")
        if refill_rate <= 0:
            raise ValueError(f"refill_rate must be > 0, got {refill_rate!r}")

        self._capacity: int = capacity
        self._refill_rate: float = refill_rate
        self._clock: Callable[[], float] = clock
        self._lock: threading.RLock = threading.RLock()

        # Bucket starts full per spec
        self._tokens: float = float(capacity)
        self._last_refill: float = clock()

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _refill(self) -> None:
        """Apply time-based refill. Caller must hold self._lock."""
        now = self._clock()
        elapsed = now - self._last_refill
        if elapsed > 0:
            added = elapsed * self._refill_rate
            self._tokens = min(self._capacity, self._tokens + added)
            self._last_refill = now

    # ── Public interface ───────────────────────────────────────────────────────

    def consume(self, tokens: int = 1) -> bool:
        """
        Attempt to consume `tokens` tokens.

        Returns True and deducts tokens if sufficient are available.
        Returns False without modifying state if insufficient.

        Args:
            tokens: Number of tokens to consume (must be >= 1).

        Raises:
            ValueError: If tokens < 1.
        """
        if tokens < 1:
            raise ValueError(f"tokens must be >= 1, got {tokens!r}")

        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True

        logger.warning(
            "TokenBucket.consume(%d) rejected — available=%.2f capacity=%d refill_rate=%.2f",
            tokens, self._tokens, self._capacity, self._refill_rate,
        )
        return False

    def available(self) -> float:
        """Return current available tokens after applying pending refill."""
        with self._lock:
            self._refill()
            return self._tokens

    def reset(self) -> None:
        """Restore bucket to full capacity. Intended for testing and admin use."""
        with self._lock:
            self._tokens = float(self._capacity)
            self._last_refill = self._clock()

    # ── Dunder helpers ─────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"TokenBucket(capacity={self._capacity!r}, "
            f"refill_rate={self._refill_rate!r}, "
            f"available={self._tokens:.2f})"
        )

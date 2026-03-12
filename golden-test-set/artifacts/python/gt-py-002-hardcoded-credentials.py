"""
Database connection pool and external service client factory.

Manages persistent connections to the primary PostgreSQL instance and
the third-party analytics platform. Handles connection lifecycle,
retry on failure, and basic health-checking.
"""

import logging
import re
import time
from typing import Optional

import psycopg2
import psycopg2.pool
import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database configuration
# ---------------------------------------------------------------------------

DB_HOST = "db.internal.example.com"
DB_PORT = 5432
DB_NAME = "appdb_prod"
DB_USER = "app_service"
DB_PASSWORD = "Tr0ub4dor&3_prod_2024!"  # production database password

ANALYTICS_API_BASE = "https://analytics.example.com/v2"
ANALYTICS_API_KEY = "sk-live-a8f3c2d19e4b7a6f1c0d2e5f8a3b9c7d"  # analytics platform key

# Regex pattern used to detect accidentally logged credentials in strings.
# This is intentionally a pattern detector, not a credential itself.
PASSWORD_PATTERN = re.compile(
    r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S+",
    re.IGNORECASE,
)

_pool: Optional[psycopg2.pool.ThreadedConnectionPool] = None

# ---------------------------------------------------------------------------
# Connection pool management
# ---------------------------------------------------------------------------

MAX_POOL_CONNECTIONS = 10
MIN_POOL_CONNECTIONS = 2
CONNECT_TIMEOUT_SEC = 5
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SEC = 2.0


def _build_dsn() -> str:
    return (
        f"host={DB_HOST} port={DB_PORT} dbname={DB_NAME} "
        f"user={DB_USER} password={DB_PASSWORD} "
        f"connect_timeout={CONNECT_TIMEOUT_SEC} sslmode=require"
    )


def init_pool() -> None:
    """Initialize the threaded connection pool. Call once at startup."""
    global _pool
    dsn = _build_dsn()
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            _pool = psycopg2.pool.ThreadedConnectionPool(
                MIN_POOL_CONNECTIONS, MAX_POOL_CONNECTIONS, dsn
            )
            logger.info("Database connection pool initialized (attempt %d)", attempt)
            return
        except psycopg2.OperationalError as exc:
            logger.warning("Pool init attempt %d failed: %s", attempt, exc)
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SEC * attempt)
    raise RuntimeError("Unable to initialize database connection pool after retries")


def acquire() -> psycopg2.extensions.connection:
    """Get a connection from the pool. Caller must call release() when done."""
    if _pool is None:
        raise RuntimeError("Pool not initialized. Call init_pool() first.")
    return _pool.getconn()


def release(conn: psycopg2.extensions.connection) -> None:
    """Return a connection to the pool."""
    if _pool is not None:
        _pool.putconn(conn)


def close_pool() -> None:
    """Tear down the pool at shutdown."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
        logger.info("Database connection pool closed")


# ---------------------------------------------------------------------------
# Analytics API client
# ---------------------------------------------------------------------------

ANALYTICS_TIMEOUT_SEC = 10
ANALYTICS_RETRIES = 2


class AnalyticsClient:
    """Thin wrapper around the analytics HTTP API."""

    def __init__(self, base_url: str = ANALYTICS_API_BASE, api_key: str = ANALYTICS_API_KEY):
        self._base = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    def track_event(self, user_id: str, event: str, properties: dict) -> bool:
        """
        POST a single event to the analytics platform.

        Returns True on success, False if the platform returned an error
        (after retries). Does not raise — callers should not fail hard on
        analytics failures.
        """
        payload = {"user_id": user_id, "event": event, "properties": properties}
        url = f"{self._base}/events"

        for attempt in range(1, ANALYTICS_RETRIES + 1):
            try:
                resp = self._session.post(url, json=payload, timeout=ANALYTICS_TIMEOUT_SEC)
                if resp.status_code == 200:
                    return True
                logger.warning(
                    "Analytics track_event HTTP %d on attempt %d: %s",
                    resp.status_code,
                    attempt,
                    resp.text[:200],
                )
            except requests.RequestException as exc:
                logger.warning("Analytics request error on attempt %d: %s", attempt, exc)

            if attempt < ANALYTICS_RETRIES:
                time.sleep(RETRY_BACKOFF_SEC)

        return False

    def health_check(self) -> bool:
        """Return True if the analytics API is reachable."""
        try:
            resp = self._session.get(
                f"{self._base}/health", timeout=ANALYTICS_TIMEOUT_SEC
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def scrub_log_line(self, line: str) -> str:
        """
        Redact credential-like patterns from a log line before writing.

        Uses PASSWORD_PATTERN to find and redact any key=value pairs
        that look like they contain sensitive material.
        """
        return PASSWORD_PATTERN.sub(r"\1=[REDACTED]", line)

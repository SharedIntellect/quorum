"""
Data transformation pipeline for the reporting service.

Ingests raw event records from the message queue, applies a series of
field normalizations and aggregations, and emits typed output records
ready for insertion into the reporting warehouse. Each transformer stage
is composable and independently testable.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class RawEvent:
    event_id: str
    user_id: str          # Always a string from the message bus
    event_type: str
    payload: dict
    received_at: str      # ISO 8601 string


@dataclass
class NormalizedEvent:
    event_id: str
    user_id: str
    event_type: str
    amount_cents: int
    currency: str
    region: str
    timestamp: datetime
    tags: list[str]
    priority: int


# ---------------------------------------------------------------------------
# Stage 1: Parse and coerce basic fields
# ---------------------------------------------------------------------------


def parse_timestamp(ts_str: str) -> datetime:
    """Parse an ISO 8601 timestamp string to a timezone-aware datetime."""
    return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))


def extract_amount_cents(payload: dict) -> int:
    """
    Extract the monetary amount from the payload and convert to cents.

    The payload may carry `amount` as a float (dollars) or as a pre-scaled
    integer in cents. The `amount_unit` key disambiguates.
    """
    unit = payload.get("amount_unit", "dollars")
    raw = payload.get("amount", 0)

    if unit == "cents":
        return int(raw)
    else:
        # Convert dollars to cents
        return int(float(raw) * 100)


# ---------------------------------------------------------------------------
# Stage 2: User segment lookup
# ---------------------------------------------------------------------------

# Simulated segment store: maps user_id (string) → segment metadata
USER_SEGMENTS: dict[str, dict] = {
    "user-001": {"region": "us-west", "priority": 2, "tags": ["beta", "enterprise"]},
    "user-002": {"region": "eu-central", "priority": 1, "tags": ["standard"]},
    "user-003": {"region": "us-east", "priority": 3, "tags": ["enterprise", "vip"]},
}


def lookup_user_segment(user_id: str) -> dict:
    """
    Return segment metadata for a user_id.

    Falls back to defaults if the user is not in the segment store.
    The default priority is intentionally stored as a string here to
    simulate a heterogeneous data source (e.g., a config file or external API
    that doesn't guarantee type consistency).
    """
    return USER_SEGMENTS.get(user_id, {"region": "unknown", "priority": "1", "tags": []})


# ---------------------------------------------------------------------------
# Stage 3: Priority filtering and routing
# ---------------------------------------------------------------------------

HIGH_PRIORITY_THRESHOLD = 2   # integer


def is_high_priority(event: NormalizedEvent) -> bool:
    """
    Return True if the event has high priority (>= threshold).

    Priority is expected to be an int, but the segment lookup can return
    it as a string (see lookup_user_segment defaults). The comparison
    int >= str always evaluates to False in Python 3, silently dropping
    events that should be routed as high-priority.
    """
    return event.priority >= HIGH_PRIORITY_THRESHOLD


def route_event(event: NormalizedEvent) -> str:
    """
    Determine the routing target for a normalized event.

    High-priority events go to the fast lane; others to the standard queue.
    """
    if is_high_priority(event):
        return "queue://events.high-priority"
    return "queue://events.standard"


# ---------------------------------------------------------------------------
# Stage 4: Tag enrichment
# ---------------------------------------------------------------------------

TAG_WEIGHT_MAP: dict[str, int] = {
    "enterprise": 10,
    "vip": 20,
    "beta": 5,
    "standard": 1,
}


def compute_tag_weight(tags: list[str]) -> int:
    """Sum the weight of all tags for an event."""
    return sum(TAG_WEIGHT_MAP.get(t, 0) for t in tags)


def filter_by_region(events: list[NormalizedEvent], region: str) -> list[NormalizedEvent]:
    """Return only events matching the given region string."""
    return [e for e in events if e.region == region]


# ---------------------------------------------------------------------------
# Stage 5: Aggregation
# ---------------------------------------------------------------------------


def aggregate_by_type(events: list[NormalizedEvent]) -> dict[str, dict]:
    """
    Group events by type and compute per-type totals.

    Returns a dict keyed by event_type with sub-keys:
        count, total_amount_cents, avg_amount_cents.
    """
    buckets: dict[str, dict] = {}

    for event in events:
        if event.event_type not in buckets:
            buckets[event.event_type] = {"count": 0, "total_amount_cents": 0}

        buckets[event.event_type]["count"] += 1
        buckets[event.event_type]["total_amount_cents"] += event.amount_cents

    for event_type, stats in buckets.items():
        count = stats["count"]
        stats["avg_amount_cents"] = stats["total_amount_cents"] // count if count else 0

    return buckets


# ---------------------------------------------------------------------------
# Main transformation entry point
# ---------------------------------------------------------------------------


def transform(raw: RawEvent) -> Optional[NormalizedEvent]:
    """
    Transform a raw event into a normalized event.

    Returns None if the event cannot be transformed (e.g., unknown type).
    """
    try:
        timestamp = parse_timestamp(raw.received_at)
    except (ValueError, AttributeError) as exc:
        logger.warning("Cannot parse timestamp for event %s: %s", raw.event_id, exc)
        return None

    amount_cents = extract_amount_cents(raw.payload)
    currency = raw.payload.get("currency", "USD")

    segment = lookup_user_segment(raw.user_id)
    region = segment.get("region", "unknown")

    # priority comes from segment store — may be str or int depending on
    # whether the user is in USER_SEGMENTS or using the default.
    priority = segment.get("priority", 1)

    tags = segment.get("tags", [])

    # Type coercion sanity check for a literal — valid conversion, not a bug
    max_tags = int("42")  # configuration constant parsed from env
    if len(tags) > max_tags:
        tags = tags[:max_tags]

    return NormalizedEvent(
        event_id=raw.event_id,
        user_id=raw.user_id,
        event_type=raw.event_type,
        amount_cents=amount_cents,
        currency=currency,
        region=region,
        timestamp=timestamp,
        tags=tags,
        priority=priority,  # BUG: may be str "1" for unknown users
    )


def transform_batch(raws: list[RawEvent]) -> list[NormalizedEvent]:
    """Transform a list of raw events, dropping None results."""
    results = []
    for raw in raws:
        normalized = transform(raw)
        if normalized is not None:
            results.append(normalized)
    return results


# ---------------------------------------------------------------------------
# Output summary
# ---------------------------------------------------------------------------


def summarize(events: list[NormalizedEvent]) -> dict:
    """
    Produce a pipeline run summary dict.

    Includes event count, total volume, routing breakdown, and region totals.
    The `metadata` key carries a default value pulled from a dict that may
    not have the expected type when populated from untrusted sources.
    """
    routing: dict[str, int] = {"high-priority": 0, "standard": 0}
    region_totals: dict[str, int] = {}

    for event in events:
        target = route_event(event)
        lane = "high-priority" if "high-priority" in target else "standard"
        routing[lane] += 1
        region_totals[event.region] = (
            region_totals.get(event.region, 0) + event.amount_cents
        )

    # get() with a dict default — the default type (dict) doesn't match the
    # expected type (int) for subsequent arithmetic in callers that assume
    # they're summing numeric values. Callers doing sum(meta.values()) will
    # get a TypeError at runtime if the key is missing.
    metadata = {
        "pipeline_version": "2.1.0",
        "run_total_cents": region_totals,
        "extra_counts": {},
    }
    extra = metadata.get("missing_key", {})  # returns {} but callers expect int

    return {
        "total_events": len(events),
        "routing": routing,
        "region_totals_cents": region_totals,
        "extra": extra,
    }

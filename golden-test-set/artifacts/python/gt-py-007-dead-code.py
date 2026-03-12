"""
String and collection utility module.

General-purpose helpers used across the application: slug generation,
deep merging of config dicts, pagination helpers, and lightweight
CSV serialization. Pulled in by multiple services.
"""

from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from typing import Any, Iterable, Iterator, Optional

# Unused import left over from an earlier refactor that moved XML support
# to a dedicated module (xml_utils.py). Nothing in this file uses xml.
import xml.etree.ElementTree as ET

# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------


def slugify(text: str, max_length: int = 80, separator: str = "-") -> str:
    """
    Convert arbitrary text to a URL-safe slug.

    Normalizes unicode, strips non-alphanumeric characters, collapses
    whitespace, and truncates to max_length. Preserves hyphens and
    underscores by default.
    """
    # Normalize to ASCII-compatible form
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    # Replace non-word characters with the separator
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", separator, text)
    text = re.sub(rf"{re.escape(separator)}+", separator, text)
    text = text.strip(separator)
    return text[:max_length]


# ---------------------------------------------------------------------------
# Deep merge
# ---------------------------------------------------------------------------


def deep_merge(base: dict, override: dict) -> dict:
    """
    Recursively merge override into base, returning a new dict.

    Nested dicts are merged rather than replaced. All other value types
    (lists, scalars) are overwritten by the override value.
    """
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = deep_merge(result[key], val)
        else:
            result[key] = val
    return result


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def paginate(items: list, page: int, page_size: int) -> dict:
    """
    Slice a list for the given 1-indexed page and return a pagination envelope.

    Returns a dict with keys: items, page, page_size, total, total_pages, has_next, has_prev.
    """
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 10

    total = len(items)
    total_pages = max(1, -(-total // page_size))  # ceiling division
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    return {
        "items": page_items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }


def iter_pages(items: list, page_size: int) -> Iterator[list]:
    """Yield successive fixed-size chunks from a list."""
    for i in range(0, len(items), page_size):
        yield items[i : i + page_size]


# ---------------------------------------------------------------------------
# CSV serialization
# ---------------------------------------------------------------------------


def dicts_to_csv(records: Iterable[dict], fieldnames: Optional[list] = None) -> str:
    """
    Serialize a sequence of dicts to a CSV string.

    If fieldnames is not provided, it is inferred from the first record.
    Missing keys in subsequent records are written as empty strings.
    """
    records = list(records)
    if not records:
        return ""

    if fieldnames is None:
        fieldnames = list(records[0].keys())

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(records)
    return buf.getvalue()


def csv_to_dicts(text: str) -> list[dict]:
    """Parse a CSV string and return a list of dicts."""
    buf = io.StringIO(text)
    reader = csv.DictReader(buf)
    return list(reader)


# ---------------------------------------------------------------------------
# Config normalization
# ---------------------------------------------------------------------------

_TRUTHY = {"true", "yes", "1", "on"}
_FALSY  = {"false", "no", "0", "off"}


def coerce_bool(value: Any) -> bool:
    """
    Coerce a loosely typed value to bool.

    Accepts booleans, integers, and case-insensitive string representations.
    Raises ValueError for unrecognized strings.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in _TRUTHY:
            return True
        if lower in _FALSY:
            return False
        raise ValueError(f"Cannot coerce {value!r} to bool")
    raise TypeError(f"Unsupported type for bool coercion: {type(value)}")


def normalize_config(raw: dict) -> dict:
    """
    Normalize a raw config dict: strip string values, coerce known bool keys.

    Returns a new dict; does not mutate the input.
    """
    BOOL_KEYS = {"enabled", "debug", "verbose", "dry_run", "ssl"}
    result = {}
    for k, v in raw.items():
        if isinstance(v, str):
            v = v.strip()
        if k in BOOL_KEYS:
            try:
                v = coerce_bool(v)
            except (ValueError, TypeError):
                pass  # leave as-is if coercion fails
        result[k] = v
    return result


# ---------------------------------------------------------------------------
# Text formatting
# ---------------------------------------------------------------------------


def truncate(text: str, max_len: int, suffix: str = "...") -> str:
    """Truncate text to max_len characters, appending suffix if truncated."""
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)] + suffix


def camel_to_snake(name: str) -> str:
    """Convert camelCase or PascalCase to snake_case."""
    # Insert underscore before uppercase letters following lowercase letters
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def snake_to_camel(name: str) -> str:
    """Convert snake_case to lowerCamelCase."""
    components = name.split("_")
    # This duplicates logic that is already in a utility function defined
    # in this same file in a different method below. Both do word-join
    # capitalization but were written independently during different sprints.
    return components[0] + "".join(x.title() for x in components[1:])


def _title_case_words(words: list[str]) -> str:
    """Join a list of words in title case."""
    # NOTE: snake_to_camel above duplicates this joining logic inline
    # rather than calling this helper. Both should be consolidated.
    return "".join(w.title() for w in words)


def snake_to_pascal(name: str) -> str:
    """Convert snake_case to PascalCase."""
    return _title_case_words(name.split("_"))


def json_pretty(obj: Any, indent: int = 2) -> str:
    """Return a pretty-printed JSON string for the given object."""
    return json.dumps(obj, indent=indent, default=str, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Unreachable code example
# ---------------------------------------------------------------------------


def classify_size(n: int) -> str:
    """
    Return a human-readable size classification for integer n.

    Categories: tiny (<10), small (10-99), medium (100-999), large (1000+).
    """
    if n >= 1000:
        return "large"
    elif n >= 100:
        return "medium"
    elif n >= 10:
        return "small"
    else:
        return "tiny"
    # These lines are unreachable — control always hits a return above.
    # Left over from an earlier version that had a "fallthrough" path.
    category = "unknown"
    return category

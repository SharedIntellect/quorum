# Meridian SDK for Python — Quick Start Guide

**Version:** 2.3.0
**Python:** 3.10+
**Status:** Stable

---

## Overview

The Meridian SDK for Python provides a high-level client for the Meridian Search and Indexing APIs. It handles authentication, retries, pagination, and response deserialization, so you can focus on building rather than managing HTTP boilerplate.

---

## Installation

Install from the internal package registry:

```bash
pip install meridian-sdk
```

Or with optional dependencies for async support:

```bash
pip install "meridian-sdk[async]"
```

---

## Quick Start

```python
from meridian_sdk import SearchClient

# Initialize the client with your API key
client = SearchClient(api_key="your-api-key")

# Run a search
results = client.search(
    collection_id="product-docs",
    query="configuring rate limits",
    top_k=5
)

for doc in results.documents:
    print(f"[{doc.score:.3f}] {doc.title}")
```

---

## Authentication

The SDK supports two authentication methods:

### API Key

Pass your API key directly to the client constructor:

```python
client = SearchClient(api_key="your-api-key")
```

Alternatively, set the `MERIDIAN_API_KEY` environment variable and the SDK will pick it up automatically:

```bash
export MERIDIAN_API_KEY=your-api-key
```

```python
client = SearchClient()  # reads from environment
```

### Service Account Token

For service-to-service integrations, use a service account credential file:

```python
client = SearchClient.from_service_account("/path/to/credentials.json")
```

---

## Search

### Basic Search

```python
results = client.search(
    collection_id="my-collection",
    query="machine learning inference",
    top_k=10
)
```

### Filtered Search

```python
results = client.search(
    collection_id="my-collection",
    query="security vulnerabilities",
    filters={
        "field": "tags",
        "operator": "in",
        "value": ["security", "cve"]
    }
)
```

### Search Modes

The SDK supports three search modes:

- `hybrid` (default) — combines keyword and semantic search for best results
- `keyword` — BM25 sparse retrieval only; fastest, best for exact-match queries
- `semantic` — dense vector search only; best for conceptual similarity

```python
results = client.search(
    collection_id="my-collection",
    query="authentication token expiration",
    mode="semantic"
)
```

---

## Collections

### List Collections

```python
collections = client.list_collections()
for c in collections:
    print(f"{c.collection_id}: {c.document_count} documents ({c.index_status})")
```

### Get a Collection

```python
collection = client.get_collection("product-docs")
print(collection.last_indexed_at)
```

---

## Pagination

Search results and collection listings support pagination:

```python
page = client.search(
    collection_id="my-collection",
    query="deployment",
    top_k=20,
    page=1
)

while page.has_next:
    page = page.next_page()
    for doc in page.documents:
        print(doc.title)
```

---

## Error Handling

The SDK raises typed exceptions for API errors:

```python
from meridian_sdk.exceptions import (
    AuthenticationError,
    CollectionNotFoundError,
    RateLimitError,
    MeridianAPIError
)

try:
    results = client.search(collection_id="nonexistent", query="test")
except CollectionNotFoundError as e:
    print(f"Collection not found: {e.collection_id}")
except RateLimitError as e:
    print(f"Rate limited. Retry after {e.retry_after_seconds}s")
except MeridianAPIError as e:
    print(f"API error {e.status_code}: {e.message}")
```

---

## Async Support

Install with async extras and use `AsyncSearchClient`:

```python
import asyncio
from meridian_sdk.async_client import AsyncSearchClient

async def main():
    async with AsyncSearchClient(api_key="your-api-key") as client:
        results = await client.search(
            collection_id="product-docs",
            query="async patterns"
        )
        for doc in results.documents:
            print(doc.title)

asyncio.run(main())
```

---

## Configuration

The client accepts a configuration object for advanced settings:

```python
from meridian_sdk import SearchClient, ClientConfig

config = ClientConfig(
    timeout_seconds=30,
    max_retries=3,
    retry_backoff_factor=1.5,
    base_url="https://api.meridian.internal"
)

client = SearchClient(api_key="your-api-key", config=config)
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `timeout_seconds` | int | 30 | Request timeout |
| `max_retries` | int | 3 | Max retry attempts on 5xx or network errors |
| `retry_backoff_factor` | float | 1.5 | Exponential backoff multiplier |
| `base_url` | str | Production URL | Override API base URL |

---

## Logging

The SDK uses Python's standard `logging` module under the `meridian_sdk` logger namespace:

```python
import logging
logging.getLogger("meridian_sdk").setLevel(logging.DEBUG)
```

---

## What's New in 2.3.0

* Added `AsyncSearchClient` for async/await usage
- Pagination support via `.next_page()` on result objects
* `ClientConfig` class for centralized configuration
- Improved error messages with structured exception types
* Performance improvements: connection pooling enabled by default

---

*Meridian SDK for Python — Platform Team — v2.3.0*

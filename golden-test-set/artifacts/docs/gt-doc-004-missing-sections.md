# Meridian Search API — Specification v1.2

**Service:** Search Service
**API Version:** v2
**Base URL:** `https://api.meridian.internal/api/v2/search`
**Document Status:** Published
**Last Updated:** 2026-01-20

---

## Overview

The Meridian Search API provides full-text and semantic search over indexed document collections. It supports keyword queries, vector similarity search, and hybrid retrieval modes. Results are ranked by relevance and may be filtered by metadata fields.

This API is designed for internal consumers (other Meridian platform services) as well as authorized external integrators.

---

## Endpoints

### 1. Search Documents

```
POST /api/v2/search/query
```

Executes a search query over the specified collection.

#### Request Body

```json
{
  "collection_id": "string",
  "query": "string",
  "mode": "keyword | semantic | hybrid",
  "top_k": 10,
  "filters": {
    "field": "string",
    "operator": "eq | in | gte | lte",
    "value": "string | number | array"
  },
  "include_metadata": true,
  "include_highlights": false
}
```

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `collection_id` | string | Yes | Identifier of the collection to search |
| `query` | string | Yes | The search query string |
| `mode` | enum | No | Retrieval mode. Default: `hybrid` |
| `top_k` | integer | No | Number of results to return. Default: 10, max: 100 |
| `filters` | object | No | Metadata field filter |
| `include_metadata` | boolean | No | Include document metadata in results. Default: `true` |
| `include_highlights` | boolean | No | Include matched text snippets. Default: `false` |

#### Response Body (200 OK)

```json
{
  "query_id": "q_01HXYZ123",
  "collection_id": "my-collection",
  "total_results": 247,
  "results": [
    {
      "doc_id": "doc_abc123",
      "score": 0.921,
      "title": "Introduction to RAG Systems",
      "excerpt": "Retrieval-augmented generation combines...",
      "metadata": {
        "author": "Jane Smith",
        "created_at": "2025-11-14T09:00:00Z",
        "tags": ["AI", "retrieval", "enterprise"]
      }
    }
  ],
  "latency_ms": 47,
  "mode_used": "hybrid"
}
```

---

### 2. Get Collection Info

```
GET /api/v2/search/collections/{collection_id}
```

Returns metadata about a specific collection.

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `collection_id` | string | Yes | Unique identifier for the collection |

#### Response Body (200 OK)

```json
{
  "collection_id": "my-collection",
  "display_name": "Product Documentation",
  "document_count": 14820,
  "index_status": "ready",
  "last_indexed_at": "2026-01-19T22:00:00Z",
  "embedding_model": "text-embedding-3-large",
  "created_at": "2025-06-01T00:00:00Z"
}
```

---

### 3. List Collections

```
GET /api/v2/search/collections
```

Returns all collections accessible to the authenticated caller.

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `page` | integer | No | Page number (1-indexed). Default: 1 |
| `page_size` | integer | No | Results per page. Default: 20, max: 100 |
| `status` | string | No | Filter by index status: `ready`, `indexing`, `error` |

#### Response Body (200 OK)

```json
{
  "collections": [
    {
      "collection_id": "my-collection",
      "display_name": "Product Documentation",
      "document_count": 14820,
      "index_status": "ready"
    }
  ],
  "total": 5,
  "page": 1,
  "page_size": 20
}
```

---

### 4. Suggest (Autocomplete)

```
GET /api/v2/search/suggest
```

Returns autocomplete suggestions based on a partial query string.

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `collection_id` | string | Yes | Collection to generate suggestions from |
| `prefix` | string | Yes | Partial query to complete |
| `max_suggestions` | integer | No | Max suggestions to return. Default: 5, max: 20 |

#### Response Body (200 OK)

```json
{
  "prefix": "retrie",
  "suggestions": [
    "retrieval augmented generation",
    "retrieval pipelines",
    "retrieval benchmarks"
  ]
}
```

---

## Request / Response Headers

### Request Headers

| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes (POST) | Must be `application/json` |
| `Accept` | No | Default: `application/json` |
| `X-Request-ID` | No | Client-supplied idempotency/tracing ID. Echoed in response. |

### Response Headers

| Header | Description |
|--------|-------------|
| `X-Request-ID` | Echoed from request, or generated if absent |
| `X-Trace-ID` | Internal distributed trace ID |
| `X-RateLimit-Limit` | Your rate limit ceiling |
| `X-RateLimit-Remaining` | Remaining requests in current window |
| `X-RateLimit-Reset` | Unix timestamp when limit resets |

---

## Data Types

### SearchMode

| Value | Description |
|-------|-------------|
| `keyword` | BM25 sparse retrieval only |
| `semantic` | Dense vector search only |
| `hybrid` | Reciprocal rank fusion of keyword + semantic results |

### IndexStatus

| Value | Description |
|-------|-------------|
| `ready` | Collection is fully indexed and queryable |
| `indexing` | Index update in progress; queries will use previous index version |
| `error` | Index is in a degraded state; partial results may be returned |

---

## SDK and Integration

The official Python SDK wraps this API:

```python
from meridian_sdk import SearchClient

client = SearchClient(api_key="your-api-key")
results = client.search(
    collection_id="my-collection",
    query="RAG architectures for enterprise",
    mode="hybrid",
    top_k=10
)

for doc in results.documents:
    print(f"{doc.title}: {doc.score:.3f}")
```

The SDK handles authentication, retries with exponential backoff, and response deserialization automatically.

---

## Versioning

The API follows semantic versioning. The current stable version is `v2`. Version `v1` is deprecated and scheduled for removal in Q3 2026.

---

*Meridian Search API Specification — Platform Team — January 2026*

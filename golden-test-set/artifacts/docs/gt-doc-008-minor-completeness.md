# Meridian Indexing API — Reference v1.0

**Service:** Indexing Service
**API Version:** v2
**Base URL:** `https://api.meridian.internal/api/v2/index`
**Status:** Stable
**Last Updated:** 2026-01-30

---

## Overview

The Meridian Indexing API allows you to create and manage document collections, ingest documents for indexing, and monitor indexing progress. Documents ingested through this API become searchable via the Search API.

---

## Authentication

All requests require a valid API key passed in the `X-API-Key` header, or a JWT Bearer token in the `Authorization` header. See the Authentication Guide for details on obtaining credentials.

```
X-API-Key: your-api-key
```

or:

```
Authorization: Bearer <jwt-token>
```

---

## Endpoints

### 1. Create Collection

```
POST /api/v2/index/collections
```

Creates a new document collection. Collections must be created before documents can be ingested.

#### Request Body

```json
{
  "collection_id": "string",
  "display_name": "string",
  "embedding_model": "text-embedding-3-large",
  "chunk_size": 512,
  "chunk_overlap": 102,
  "metadata_schema": {
    "author": "string",
    "created_at": "datetime",
    "tags": "array"
  }
}
```

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `collection_id` | string | Yes | Unique ID for the collection. Lowercase alphanumeric + hyphens, max 64 chars. |
| `display_name` | string | Yes | Human-readable name for the collection. |
| `embedding_model` | string | No | Embedding model to use. Default: `text-embedding-3-large` |
| `chunk_size` | integer | No | Token chunk size for document splitting. Default: 512. Range: 128–2048. |
| `chunk_overlap` | integer | No | Token overlap between chunks. Default: 102 (20% of 512). |
| `metadata_schema` | object | No | Optional schema for document metadata fields. Used for filter validation. |

#### Response Body (201 Created)

```json
{
  "collection_id": "my-new-collection",
  "display_name": "Product Documentation",
  "status": "created",
  "created_at": "2026-01-30T14:00:00Z",
  "embedding_model": "text-embedding-3-large"
}
```

#### Error Responses

| Status | Code | Description |
|--------|------|-------------|
| 400 | `INVALID_COLLECTION_ID` | collection_id contains invalid characters |
| 409 | `COLLECTION_EXISTS` | A collection with this ID already exists |
| 422 | `INVALID_SCHEMA` | metadata_schema contains unsupported field types |

---

### 2. Ingest Documents

```
POST /api/v2/index/collections/{collection_id}/documents
```

Ingests one or more documents into the specified collection. Documents are processed asynchronously; this endpoint returns immediately with a job ID.

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `collection_id` | string | Yes | ID of the target collection |

#### Request Body

```json
{
  "documents": [
    {
      "doc_id": "string",
      "title": "string",
      "content": "string",
      "metadata": {
        "author": "Jane Smith",
        "created_at": "2026-01-15T10:00:00Z",
        "tags": ["AI", "enterprise"]
      }
    }
  ],
  "upsert": true
}
```

#### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `documents` | array | Yes | Array of document objects. Max 100 per request. |
| `documents[].doc_id` | string | Yes | Unique document ID within the collection. |
| `documents[].title` | string | Yes | Document title. Used in search result display. |
| `documents[].content` | string | Yes | Full document text content. Max 1MB per document. |
| `documents[].metadata` | object | No | Key-value metadata. Must conform to collection schema if defined. |
| `upsert` | boolean | No | If true, update existing documents with matching doc_id. Default: `false`. |

#### Response Body (202 Accepted)

```json
{
  "job_id": "job_01HXYZ456",
  "collection_id": "my-new-collection",
  "document_count": 5,
  "status": "queued",
  "estimated_completion_seconds": 30
}
```

---

### 3. Get Ingestion Job Status

```
GET /api/v2/index/jobs/{job_id}
```

Returns the status of an asynchronous ingestion job.

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `job_id` | string | Yes | Job ID returned by the ingest endpoint |

#### Response Body (200 OK)

```json
{
  "job_id": "job_01HXYZ456",
  "collection_id": "my-new-collection",
  "status": "completed",
  "total_documents": 5,
  "indexed_documents": 5,
  "failed_documents": 0,
  "started_at": "2026-01-30T14:00:05Z",
  "completed_at": "2026-01-30T14:00:28Z",
  "errors": []
}
```

Job status values: `queued`, `processing`, `completed`, `failed`, `partial_failure`

---

### 4. Delete Document

```
DELETE /api/v2/index/collections/{collection_id}/documents/{doc_id}
```

Removes a single document from the collection and its index.

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `collection_id` | string | Yes | Collection containing the document |
| `doc_id` | string | Yes | Document to delete |

#### Response Body (200 OK)

```json
{
  "doc_id": "doc_abc123",
  "collection_id": "my-new-collection",
  "status": "deleted"
}
```

#### Error Responses

| Status | Code | Description |
|--------|------|-------------|
| 404 | `DOCUMENT_NOT_FOUND` | No document with this ID in the collection |

---

### 5. Delete Collection

```
DELETE /api/v2/index/collections/{collection_id}
```

Permanently deletes a collection and all its documents. This action is irreversible.

#### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `collection_id` | string | Yes | Collection to delete |

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `confirm` | boolean | Yes | Must be `true` to proceed. Safety guard. |

#### Response Body (200 OK)

```json
{
  "collection_id": "my-old-collection",
  "status": "deleted",
  "documents_removed": 14820
}
```

---

## Rate Limits

| Tier | Ingest Limit | Management Limit |
|------|-------------|-----------------|
| Standard | 100 documents/minute | 60 requests/minute |
| Enterprise | 5,000 documents/minute | 300 requests/minute |

When rate limited, the API returns `HTTP 429` with `Retry-After` header.

---

## Webhooks

Optionally, receive notifications when indexing jobs complete:

```json
{
  "webhook_url": "https://your-service.example.com/webhooks/meridian",
  "events": ["job.completed", "job.failed"]
}
```

Configure webhooks via the Admin API or the Meridian Console.

---

## SDK Example

```python
from meridian_sdk import IndexingClient

client = IndexingClient(api_key="your-api-key")

# Create a collection
collection = client.create_collection(
    collection_id="my-docs",
    display_name="My Documentation"
)

# Ingest documents
job = client.ingest_documents(
    collection_id="my-docs",
    documents=[
        {"doc_id": "doc-001", "title": "Getting Started", "content": "..."},
        {"doc_id": "doc-002", "title": "Configuration", "content": "..."},
    ]
)

# Wait for completion
result = client.wait_for_job(job.job_id, poll_interval_seconds=5)
print(f"Indexed {result.indexed_documents} documents")
```

---

*Meridian Indexing API Reference — Platform Team — January 2026*

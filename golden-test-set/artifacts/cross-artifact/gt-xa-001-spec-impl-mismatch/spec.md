# User Management API — Specification v2.1

**Service:** user-mgmt-svc
**Owner:** platform-eng@company.internal
**Last revised:** 2026-01-20
**Status:** APPROVED — implementation target Q1-2026

---

## Overview

The User Management API provides CRUD operations for user accounts, role assignments,
and administrative actions. All endpoints are served at `/api/v2`.

---

## Authentication

All endpoints require authentication. The authentication scheme varies by security tier:

| Security Tier | Scheme | Header |
|---------------|--------|--------|
| Standard | JWT Bearer token | `Authorization: Bearer <token>` |
| Admin | JWT Bearer token (admin scope required) | `Authorization: Bearer <token>` |

Tokens are issued by the internal IdP at `https://auth.company.internal/token`.
**Admin endpoints MUST validate the `role:admin` claim in the JWT payload.**
Basic authentication is explicitly prohibited on all endpoints.

---

## Endpoints

### 1. GET /api/users

Retrieve a paginated list of users.

**Auth:** JWT (standard)
**Rate limit:** 100 req/min per token
**Query parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `page`    | int  | no       | Page number (default: 1) |
| `limit`   | int  | no       | Results per page (default: 20, max: 100) |
| `filter`  | str  | no       | Substring filter on username |

**Response 200:**
```json
{
  "users": [{ "id": "uuid", "username": "string", "email": "string", "role": "string" }],
  "total": 0,
  "page": 1,
  "limit": 20
}
```

**Response 401:** Token missing or invalid.
**Response 403:** Token lacks required scope.
**Response 429:** Rate limit exceeded.

---

### 2. GET /api/users/{id}

Retrieve a single user by UUID.

**Auth:** JWT (standard)
**Rate limit:** 200 req/min per token

**Path parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id`      | UUID | yes      | User UUID |

**Response 200:**
```json
{ "id": "uuid", "username": "string", "email": "string", "role": "string", "created_at": "ISO8601" }
```

**Response 404:** User not found.
**Response 401:** Token missing or invalid.

---

### 3. POST /api/users

Create a new user account.

**Auth:** JWT (standard)
**Rate limit:** 10 req/min per token

**Request body:**
```json
{ "username": "string", "email": "string", "role": "viewer|editor|admin" }
```

**Response 201:**
```json
{ "id": "uuid", "username": "string", "email": "string", "role": "string", "created_at": "ISO8601" }
```

**Response 400:** Validation error (missing fields, invalid email, invalid role).
**Response 409:** Username or email already exists.

---

### 4. PUT /api/users/{id}

Update an existing user account.

**Auth:** JWT (standard)
**Rate limit:** 20 req/min per token

**Request body:** Partial update — any subset of `username`, `email`, `role`.

**Response 200:** Updated user object (same shape as GET /api/users/{id}).
**Response 404:** User not found.
**Response 409:** Username or email conflict.

---

### 5. DELETE /api/users/{id}

Permanently delete a user account and all associated data.

**Auth:** JWT (admin scope required)
**Rate limit:** 5 req/min per token
**Audit:** All delete operations MUST be logged to the audit service before the delete executes.

**Path parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id`      | UUID | yes      | User UUID of account to delete |

**Response 204:** User deleted. No body.
**Response 403:** Token does not carry `role:admin` claim.
**Response 404:** User not found.
**Response 409:** Cannot delete last admin account.

---

### 6. GET /api/admin/stats

Retrieve aggregate service statistics (user counts, recent activity).

**Auth:** JWT (admin scope required)
**Rate limit:** 10 req/min per token

**Response 200:**
```json
{
  "total_users": 0,
  "active_last_30d": 0,
  "new_last_7d": 0,
  "roles": { "viewer": 0, "editor": 0, "admin": 0 }
}
```

**Response 403:** Token does not carry `role:admin` claim.

---

## Error Envelope

All error responses use the standard envelope:

```json
{ "error": { "code": "string", "message": "string", "request_id": "string" } }
```

---

## Rate Limiting

Limits apply per-token per-endpoint. Exceeded requests receive HTTP 429 with a
`Retry-After` header specifying seconds until the window resets.

---

## Changelog

| Version | Date | Author | Change |
|---------|------|--------|--------|
| 2.1 | 2026-01-20 | platform-eng | Added DELETE /api/users/{id} (audit requirement) |
| 2.0 | 2025-11-10 | platform-eng | JWT-only auth; removed basic auth support |
| 1.3 | 2025-08-02 | platform-eng | Added /api/admin/stats |

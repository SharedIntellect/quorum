# Meridian Gateway — Technical Specification v2.1

**System:** Meridian API Gateway
**Component:** Request routing, rate limiting, and observability layer
**Author:** Platform Architecture Team
**Status:** Draft — Under review
**Version:** 2.1.0
**Last Updated:** 2026-02-14

---

## 1. Overview

Meridian Gateway is the entry point for all client traffic to the Meridian platform. It provides:

- TLS termination and certificate management
- Authentication token validation (JWT + API key)
- Rate limiting per tenant, per endpoint, and globally
- Request routing to upstream microservices
- Distributed tracing and structured logging
- Circuit breaker patterns for downstream service protection

This document specifies the behavioral requirements, performance targets, latency budgets, and deployment topology for Meridian Gateway version 2.1.

---

## 2. Scope

This specification covers:

- The gateway's external API surface (ingress)
- Internal routing rules and upstream target resolution
- Rate limiting semantics and enforcement guarantees
- Latency and throughput requirements
- Operational monitoring and alerting thresholds

This specification does not cover:

- Individual microservice behavior (see service-level specs)
- Client SDK integration
- Infrastructure provisioning (see Terraform module documentation)

---

## 3. Performance Requirements

### 3.1 Latency Budget

All latency figures are measured at the gateway boundary (time from first byte received to last byte sent on the response).

| Percentile | Target | Hard Limit |
|-----------|--------|-----------|
| p50 | ≤ 15ms | 30ms |
| p95 | ≤ 45ms | 80ms |
| p99 | ≤ 100ms | 150ms |
| p99.9 | ≤ 200ms | 300ms |

**Gateway processing overhead** (exclusive of upstream service latency) must not exceed **100ms at p99** under normal operating conditions. This is the budget the gateway itself consumes for authentication, routing, rate-limit enforcement, and logging.

These targets apply to the steady-state load profile (described in §3.3). Burst handling is covered separately in §5.

### 3.2 Throughput

The gateway must sustain **50,000 requests per second (RPS)** per availability zone at the reference hardware configuration (8-core, 32GB RAM, 10Gbps NIC). Horizontal scaling is expected to extend this linearly to a fleet-wide target of 500,000 RPS across 10 AZs.

### 3.3 Reference Load Profile

The reference load profile for performance testing:

- 70% read-only (GET) requests
- 20% write requests (POST/PUT/PATCH)
- 10% large-payload requests (>64KB request body, e.g., batch ingestion)
- Simulated at 50,000 RPS sustained for 30 minutes, followed by 5-minute 3× burst to 150,000 RPS

---

## 4. Architecture

### 4.1 Component Topology

Meridian Gateway is deployed as a fleet of stateless gateway nodes behind a Layer 4 load balancer. Each node runs two processes:

1. **gateway-proxy** — the hot path: TLS termination, JWT validation, routing, and response forwarding
2. **gateway-sidecar** — the cold path: rate-limit state synchronization, certificate rotation, config reload

The gateway-proxy process is written in Rust (tokio async runtime) for predictable latency. The gateway-sidecar is written in Go.

### 4.2 Service Topology

The Meridian Gateway routes traffic to the following upstream services:

1. **Search Service** — handles document retrieval queries
2. **Indexing Service** — handles document ingestion and index updates
3. **Auth Service** — handles OAuth flows and token introspection

Traffic routing is determined by URL path prefix matching. Path prefix assignments:

| Path Prefix | Upstream Service | Notes |
|------------|-----------------|-------|
| `/api/v2/search/*` | Search Service | Read-heavy, latency-sensitive |
| `/api/v2/index/*` | Indexing Service | Write-heavy, throughput-sensitive |
| `/api/v2/auth/*` | Auth Service | Low-volume, security-critical |

### 4.3 Data Flow

```
Client → [TLS Termination] → [JWT Validation] → [Rate Limiter] → [Router] → Upstream Service
                                                                      ↓
                                                              [Response Cache]
                                                              (read-only, 30s TTL)
```

The response cache is in-process, per-node. Cache hit rate target: 25% for the reference load profile.

---

## 5. Rate Limiting

### 5.1 Rate Limit Tiers

Rate limits are enforced at three levels, in evaluation order:

1. **Global** — fleet-wide ceiling, enforced via Redis sliding window
2. **Tenant** — per-tenant ceiling, configurable via Admin API
3. **Endpoint** — per-endpoint ceiling, defined in routing config

### 5.2 Default Limits

| Tier | Default Limit | Window |
|------|--------------|--------|
| Global | 500,000 RPS | 1 second |
| Tenant (Standard) | 1,000 RPS | 1 second |
| Tenant (Enterprise) | 10,000 RPS | 1 second |
| Endpoint | Varies per route | 1 second |

### 5.3 Enforcement Behavior

When a rate limit is exceeded:

- The gateway returns `HTTP 429 Too Many Requests`
- The `Retry-After` header is set to the seconds until the next window
- The request is not forwarded to any upstream service
- The event is logged and counted against the `rate_limit_exceeded` metric

### 5.4 Latency Impact of Rate Limiting

The rate-limit check adds overhead to the gateway processing path. Rate-limit enforcement must not increase p99 gateway latency by more than **150ms above baseline** under normal load conditions. The total gateway processing budget, including rate limiting, is therefore **250ms at p99**.

Note: This budget accounts for all gateway-internal operations: JWT validation, rate-limit Redis round-trip, routing table lookup, request logging, and response buffering. The 250ms figure supersedes the more conservative estimate in §3.1.

---

## 6. Authentication

### 6.1 Supported Mechanisms

The gateway validates two authentication mechanisms:

1. **JWT Bearer tokens** — for human and machine-to-machine clients using the Meridian OAuth2 flow
2. **API keys** — for server-to-server integrations via `X-API-Key` header

### 6.2 JWT Validation

JWT validation is performed in-process (no upstream round-trip for valid tokens). The gateway:

1. Decodes the JWT header to identify the signing key ID (`kid`)
2. Fetches the corresponding public key from the in-memory JWKS cache
3. Verifies the signature using RS256 or ES256 (algorithm allowlisted in config)
4. Validates standard claims: `exp`, `nbf`, `iss`, `aud`
5. Extracts tenant ID and scopes from custom claims

JWKS cache TTL: 300 seconds. Cache is pre-warmed at startup and refreshed in background.

### 6.3 API Key Validation

API keys are validated via a synchronous lookup in the Auth Service's key database, proxied through the gateway-sidecar. Lookup latency is expected to be <10ms at p99 (local network).

---

## 7. Observability

### 7.1 Metrics (Prometheus)

The gateway exposes a `/metrics` endpoint in Prometheus format. Key metrics:

| Metric | Type | Labels |
|--------|------|--------|
| `meridian_gateway_requests_total` | Counter | method, path_prefix, status_code |
| `meridian_gateway_latency_seconds` | Histogram | method, path_prefix, upstream |
| `meridian_gateway_rate_limit_exceeded_total` | Counter | tenant_id, endpoint |
| `meridian_gateway_upstream_errors_total` | Counter | upstream, error_type |
| `meridian_gateway_cache_hits_total` | Counter | path_prefix |
| `meridian_gateway_cache_misses_total` | Counter | path_prefix |

### 7.2 Alerting Thresholds

| Alert | Condition | Severity |
|-------|-----------|----------|
| HighLatency | p99 latency > 200ms (5m window) | Warning |
| CriticalLatency | p99 latency > 400ms (2m window) | Critical |
| HighErrorRate | 5xx rate > 1% (5m window) | Warning |
| UpstreamDown | upstream_errors > 10/s for >30s | Critical |

### 7.3 Distributed Tracing

All requests are tagged with a `trace-id` (W3C TraceContext format). Traces are exported to the internal Tempo cluster via OTLP. Sampling strategy: 100% for errors and slow requests (>500ms), 1% for successful requests.

---

## 8. Security

### 8.1 TLS Configuration

- Minimum TLS version: 1.2 (1.3 preferred)
- Cipher suites: restricted to ECDHE+AESGCM and ECDHE+CHACHA20 families
- HSTS: enabled, max-age=31536000, includeSubDomains
- Certificate rotation: automated via cert-manager (Let's Encrypt or internal CA)

### 8.2 Header Sanitization

The gateway strips the following headers from inbound requests before forwarding upstream:

- `X-Forwarded-For` (re-added with gateway's controlled value)
- `X-Real-IP`
- `X-Internal-*` (all headers with this prefix)

### 8.3 mTLS for Upstream Communication

Communication from the gateway to all upstream services uses mutual TLS. Client certificates are rotated automatically every 24 hours via the gateway-sidecar certificate rotation process.

---

## 9. Configuration Reference

Gateway configuration is managed via a YAML file loaded at startup, with live-reload support (SIGHUP).

```yaml
gateway:
  listen_addr: "0.0.0.0:443"
  tls:
    cert_path: "/etc/meridian/tls/server.crt"
    key_path: "/etc/meridian/tls/server.key"
    min_version: "1.2"

  upstream_timeout_ms: 30000

  rate_limiting:
    backend: redis
    redis_url: "${REDIS_URL}"
    global_rps: 500000

  jwks:
    url: "https://auth.meridian.internal/.well-known/jwks.json"
    cache_ttl_seconds: 300

  routing:
    rules:
      - prefix: "/api/v2/search/"
        upstream: "http://search-service.meridian.internal:8080"
      - prefix: "/api/v2/index/"
        upstream: "http://indexing-service.meridian.internal:8080"
      - prefix: "/api/v2/auth/"
        upstream: "http://auth-service.meridian.internal:8080"
```

---

## 10. Open Issues

| Issue | Priority | Owner |
|-------|----------|-------|
| Redis SPOF: single Redis instance is a rate-limit bottleneck | High | Platform |
| API key lookup latency not yet benchmarked at scale | Medium | Auth team |
| Response cache invalidation on index updates not implemented | High | Platform |

---

*Document maintained by the Platform Architecture Team. Review cycle: quarterly or on major version bump. Contact: platform-arch@meridian.internal*

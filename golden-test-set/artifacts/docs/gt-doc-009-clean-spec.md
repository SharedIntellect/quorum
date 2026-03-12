# Meridian Event Bus — Technical Specification v0.1.0

**System:** Meridian Platform
**Component:** Event Bus (pub/sub backbone)
**Spec Version:** 0.1.0
**Status:** Draft — Accepted for implementation
**Author:** Platform Architecture Team
**Created:** 2026-02-10
**Last Updated:** 2026-02-24
**Review Cycle:** On major version bump or quarterly

---

## Table of Contents

1. [Overview](#1-overview)
2. [Goals and Non-Goals](#2-goals-and-non-goals)
3. [Architecture](#3-architecture)
4. [Event Schema](#4-event-schema)
5. [Topic Design](#5-topic-design)
6. [Producer Specification](#6-producer-specification)
7. [Consumer Specification](#7-consumer-specification)
8. [Delivery Semantics](#8-delivery-semantics)
9. [Performance Requirements](#9-performance-requirements)
10. [Security](#10-security)
11. [Known Limitations](#11-known-limitations)
12. [Open Questions](#12-open-questions)
13. [Revision History](#13-revision-history)

---

## 1. Overview

The Meridian Event Bus provides asynchronous, durable, ordered pub/sub messaging between Meridian platform services. It decouples producers from consumers, enabling services to evolve independently and absorb load spikes without cascading failures.

The Event Bus is built on **Apache Kafka 3.6** (KRaft mode, no ZooKeeper dependency). All producers and consumers use the official Kafka client libraries; the Event Bus does not introduce a proprietary abstraction layer over Kafka primitives.

### 1.1 Scope

This specification covers:

- Event schema and validation
- Topic naming conventions and partition strategy
- Producer and consumer behavioral contracts
- Delivery guarantee semantics
- Performance targets
- Security model (authentication, authorization, encryption)

This specification does not cover:

- Individual service business logic
- Schema evolution policies beyond v0.1.0 scope (deferred to v0.2.0 spec)
- Infrastructure provisioning (see Terraform module `meridian-kafka`)
- Kafka cluster operations (see Runbook: Kafka Operations)

### 1.2 Relationship to Other Components

| Component | Relationship |
|-----------|-------------|
| Indexing Service | Producer of `document.ingested` events |
| Search Service | Consumer of `index.updated` events |
| Gateway | Producer of `request.completed` events (analytics path) |
| Audit Service | Consumer of all security-relevant event topics |

---

## 2. Goals and Non-Goals

### Goals

- **Durability:** Events are retained for a configurable period (default: 7 days). A consumer restart does not lose events.
- **Ordering:** Within a partition, events are strictly ordered by produce time. The spec defines partitioning rules to ensure ordering where it matters.
- **Observability:** All producers and consumers emit standard Prometheus metrics enabling lag monitoring and alerting.
- **Schema enforcement:** All events are validated against a JSON Schema at produce time. Malformed events are rejected with a structured error.
- **Independent deployability:** Services that produce or consume events do not need to coordinate releases.

### Non-Goals

- **Exactly-once across distributed transactions:** The Event Bus guarantees at-least-once delivery. Consumers are responsible for idempotent processing.
- **Sub-millisecond latency:** The Event Bus is designed for throughput, not ultra-low-latency RPC. Use gRPC for synchronous latency-sensitive calls.
- **Cross-cluster replication:** Out of scope for v0.1.0.

---

## 3. Architecture

### 3.1 Cluster Topology

The Meridian Event Bus runs as a dedicated Kafka cluster, separate from any application infrastructure:

- **Brokers:** 3 broker nodes, each on a dedicated VM (8-core, 32GB RAM, 2TB NVMe SSD)
- **Replication factor:** 3 (all topics)
- **Minimum in-sync replicas:** 2 (producers configured with `acks=all`)
- **KRaft controllers:** Co-located with broker nodes (combined mode for v0.1.0; dedicated controller nodes planned for v0.2.0)

### 3.2 Client Connectivity

All services connect via an internal load balancer endpoint: `kafka.meridian.internal:9093` (TLS port). Direct broker connections are not allowed; all traffic routes through the load balancer.

### 3.3 Schema Registry

A Confluent Schema Registry instance is deployed alongside the cluster. All event schemas are registered and versioned in the registry. The registry enforces compatibility modes per topic (see §4.3).

---

## 4. Event Schema

### 4.1 Envelope

All events share a common envelope wrapping the payload:

```json
{
  "event_id": "evt_01JXXXXXXXXX",
  "event_type": "document.ingested",
  "event_version": "1.0",
  "source_service": "indexing-service",
  "timestamp": "2026-02-10T14:30:00.000Z",
  "correlation_id": "req_01JXXXXXXXXX",
  "payload": { ... }
}
```

#### Envelope Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `event_id` | string (ULID) | Yes | Globally unique event identifier |
| `event_type` | string | Yes | Dot-separated event type: `<domain>.<action>` |
| `event_version` | string | Yes | Semantic version of the event payload schema |
| `source_service` | string | Yes | Canonical name of the producing service |
| `timestamp` | string (ISO 8601) | Yes | Producer-assigned event time (UTC) |
| `correlation_id` | string | No | Propagated request ID for distributed tracing |
| `payload` | object | Yes | Event-type-specific payload (validated per event schema) |

### 4.2 Event Types (v0.1.0)

| Event Type | Producer | Consumers | Topic |
|-----------|----------|-----------|-------|
| `document.ingested` | Indexing Service | Search, Audit | `meridian.document.events` |
| `document.deleted` | Indexing Service | Search, Audit | `meridian.document.events` |
| `index.updated` | Indexing Service | Search | `meridian.index.events` |
| `search.query.completed` | Search Service | Analytics, Audit | `meridian.search.events` |
| `auth.token.issued` | Auth Service | Audit | `meridian.auth.events` |
| `auth.token.revoked` | Auth Service | Gateway, Audit | `meridian.auth.events` |

### 4.3 Schema Compatibility

The Schema Registry is configured with **BACKWARD** compatibility mode for all production topics. This means:

- New optional fields may be added (consumers ignoring them remain valid)
- Required fields may not be removed or renamed
- Field types may not be changed

Breaking schema changes require a new `event_version` and a coordinated migration plan.

---

## 5. Topic Design

### 5.1 Naming Convention

```
meridian.<domain>.events
```

Examples: `meridian.document.events`, `meridian.auth.events`

Topics are domain-scoped, not service-scoped. Multiple event types may share a topic if they belong to the same domain and are consumed by the same consumer set.

### 5.2 Partition Strategy

| Topic | Partition Count | Partition Key |
|-------|----------------|--------------|
| `meridian.document.events` | 12 | `collection_id` |
| `meridian.index.events` | 12 | `collection_id` |
| `meridian.search.events` | 24 | `tenant_id` |
| `meridian.auth.events` | 6 | `tenant_id` |

Partitioning by `collection_id` ensures ordered processing of events for the same collection. Partitioning by `tenant_id` on search events enables per-tenant consumer parallelism.

### 5.3 Retention

| Topic | Retention | Rationale |
|-------|-----------|-----------|
| `meridian.document.events` | 7 days | Document operations are idempotent; 7 days allows recovery from downstream outages |
| `meridian.index.events` | 3 days | Short retention; consumers should be near-real-time |
| `meridian.search.events` | 30 days | Retained for analytics backfill use cases |
| `meridian.auth.events` | 90 days | Security audit requirement |

---

## 6. Producer Specification

### 6.1 Required Configuration

All producers must configure:

```
acks=all                    # Wait for all ISR acknowledgment
enable.idempotence=true     # Exactly-once produce semantics within a session
max.in.flight.requests.per.connection=5
retries=2147483647          # Effectively infinite retries (bounded by delivery.timeout.ms)
delivery.timeout.ms=120000  # 2-minute delivery timeout
```

### 6.2 Schema Validation

Producers must validate the event envelope and payload against the registered schema before producing. The Meridian SDK's `EventProducer` class handles this automatically. If using a raw Kafka client, call the Schema Registry validation endpoint before produce.

### 6.3 Error Handling

If schema validation fails: log the validation error, route to the service-level DLQ (`<service>.dlq`), and do not produce to the event topic.

If the Kafka produce call fails after retries: log the error with the full event for manual replay, emit `event_produce_failed_total` metric, and surface as a service health degradation (not a hard failure, unless the event is blocking a synchronous operation).

---

## 7. Consumer Specification

### 7.1 Required Configuration

```
auto.offset.reset=earliest  # On first join, consume from beginning of retention window
enable.auto.commit=false     # Manual offset commit after successful processing
max.poll.interval.ms=300000 # 5 minutes; increase if processing is batch-heavy
```

### 7.2 Idempotent Processing

Because the Event Bus guarantees at-least-once delivery, consumers must process events idempotently. Recommended patterns:

- Check for the `event_id` in a processed-events table before acting
- Use upsert semantics for database writes keyed on `event_id`
- Design state machines that tolerate duplicate transition triggers

### 7.3 Offset Commit

Commit offsets only after successful processing and persistence. Never commit before processing is complete.

### 7.4 Consumer Groups

Consumer group naming: `<service>-<topic-domain>-consumer`. Example: `search-service-document-consumer`.

---

## 8. Delivery Semantics

The Event Bus provides **at-least-once** delivery. This means:

- Every event produced will be delivered to every subscribed consumer at least once
- In failure and retry scenarios, an event may be delivered more than once
- Duplicate delivery is not a bug — consumers must be idempotent (see §7.2)

**Producer side:** `acks=all` + `enable.idempotence=true` provides exactly-once semantics at the Kafka protocol level within a producer session. This eliminates producer-side duplicates but does not prevent consumer-side redelivery after a crash before offset commit.

**Consumer side:** Exactly-once end-to-end (including consumer processing and downstream writes) requires transactional consumers, which are deferred to v0.2.0.

---

## 9. Performance Requirements

### 9.1 Throughput Targets

| Topic | Target Throughput | Burst (10s) |
|-------|-----------------|-------------|
| `meridian.document.events` | 1,000 events/sec | 5,000 events/sec |
| `meridian.search.events` | 10,000 events/sec | 50,000 events/sec |
| `meridian.auth.events` | 500 events/sec | 2,000 events/sec |

### 9.2 Latency Targets

End-to-end produce-to-consume latency (producer acknowledges → consumer receives):

| Percentile | Target |
|-----------|--------|
| p50 | ≤ 50ms |
| p99 | ≤ 200ms |
| p99.9 | ≤ 1,000ms |

These targets assume consumers are running and not lagging. Latency for a lagging consumer is bounded by catch-up throughput, not the per-event latency.

---

## 10. Security

### 10.1 Authentication

All clients authenticate to the Kafka cluster using **mTLS**. Client certificates are issued by the Meridian internal CA and must be rotated every 90 days (automated via cert-manager).

Plaintext and SASL/PLAIN connections are disabled at the broker level.

### 10.2 Authorization

Topic-level ACLs are managed via Kafka's built-in ACL system:

- Producers: `WRITE` permission on their designated topic(s)
- Consumers: `READ` permission on their designated topic(s) + `READ` on their consumer group
- No service has blanket `READ` or `WRITE` on all topics
- ACL changes require a Platform team approval workflow

### 10.3 Encryption

All data in transit is encrypted via TLS 1.2+ (TLS 1.3 preferred). Data at rest is encrypted via the host volume encryption provided by the cloud provider (AES-256).

---

## 11. Known Limitations

This section documents known limitations of the v0.1.0 specification. These are intentional design boundaries, not defects.

- **No cross-cluster replication:** Events are contained within a single region. Geo-redundancy is out of scope for v0.1.0.
- **No exactly-once end-to-end:** Consumer-side exactly-once requires Kafka transactions, deferred to v0.2.0 (see §8).
- **KRaft combined mode:** Controller and broker roles are co-located in v0.1.0. This is acceptable for the initial deployment scale but limits controller isolation. Dedicated controllers are planned for v0.2.0.
- **Schema evolution:** Only BACKWARD compatibility is enforced. FORWARD and FULL compatibility are not required in v0.1.0 but will be evaluated for critical topics in v0.2.0.
- **No dead-letter topic automation:** Producers manually route to their DLQ; there is no Kafka Streams-based DLQ automation in this version.

---

## 12. Open Questions

| # | Question | Owner | Target |
|---|---------|-------|--------|
| 1 | Should search analytics events be sampled before producing to reduce volume? | Analytics Team | v0.2.0 |
| 2 | What is the right retention for `meridian.index.events` — 3 days may be too short if consumers are batch-oriented | Platform | Resolve before GA |
| 3 | Evaluate Kafka Streams vs. Flink for stateful consumer workloads (Audit aggregation use case) | Data Eng | Q3 2026 |

---

## 13. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 0.1.0 | 2026-02-10 | Platform Architecture | Initial draft |
| 0.1.0 | 2026-02-24 | Platform Architecture | Incorporated review feedback: added §11 Known Limitations, expanded §8 Delivery Semantics, clarified ACL workflow in §10.2 |

---

*Meridian Event Bus Technical Specification — Platform Architecture Team*
*Questions: platform-arch@meridian.internal*

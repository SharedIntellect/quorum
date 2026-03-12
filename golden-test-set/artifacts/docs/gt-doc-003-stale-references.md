# Helix Data Pipeline — README

**Project:** Helix
**Component:** Batch data processing pipeline
**Repository:** `internal/helix-pipeline`
**Maintainer:** Data Engineering Team
**Last Updated:** 2024-08-15 *(note: this README has not been updated since initial release)*

---

## Overview

Helix is a batch data processing pipeline that ingests structured event data from Kafka topics, applies configurable transformation rules, and writes outputs to the data warehouse. It is designed for high-throughput, low-latency batch workloads with built-in checkpointing and fault tolerance.

**Key features:**

- Configurable source connectors (Kafka, S3, GCS)
- Rule-based transformation DSL
- Exactly-once delivery semantics via offset tracking
- Prometheus metrics and OpenTelemetry tracing
- Dead-letter queue (DLQ) routing for malformed records

---

## Prerequisites

### System Requirements

- **Operating System:** Linux (Ubuntu 20.04+ or RHEL 8+)
- **CPU:** 4+ cores recommended
- **Memory:** 8GB minimum, 16GB recommended
- **Disk:** 50GB+ for checkpoint storage

### Software Requirements

- **Python 3.8 or higher** — Helix's transformation engine and CLI tooling are written in Python
- **Docker 20.10+** — for containerized deployment
- **Kafka 2.8+** — source connector dependency
- **Redis 6.0+** — offset tracking and DLQ management

> **Note:** Python 3.8 reached end-of-life in October 2024. While Helix runs on Python 3.8, we recommend upgrading your environment before deploying in production.

### Dependencies

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Core Python dependencies (from `requirements.txt`):

```
kafka-python==2.0.2
redis==4.6.0
prometheus-client==0.17.1
opentelemetry-sdk==1.20.0
pydantic==1.10.13
click==8.1.7
```

---

## Installation

### Option 1: pip (recommended for development)

```bash
# Clone the repository
git clone https://internal.git.corp/data-eng/helix-pipeline.git
cd helix-pipeline

# Create virtual environment
python3.8 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify installation
helix --version
```

### Option 2: Docker (recommended for production)

```bash
docker pull registry.internal.corp/data-eng/helix:latest
docker run -v /etc/helix:/config registry.internal.corp/data-eng/helix:latest
```

### Option 3: Helm (Kubernetes)

```bash
helm repo add helix https://charts.internal.corp/helix
helm install helix helix/helix-pipeline --values my-values.yaml
```

---

## Configuration

Helix is configured via a YAML file. By default it looks for `helix.yaml` in the working directory.

```yaml
helix:
  pipeline_name: "my-pipeline"

  source:
    type: kafka
    brokers:
      - "kafka-broker-1.internal:9092"
      - "kafka-broker-2.internal:9092"
    topic: "events.raw"
    consumer_group: "helix-prod"

  transform:
    rules_file: "rules/transformations.yaml"
    error_policy: dlq  # dlq | skip | fail

  sink:
    type: bigquery
    project: "my-gcp-project"
    dataset: "events"
    table: "processed_events"

  checkpointing:
    backend: redis
    redis_url: "redis://redis.internal:6379/0"
    interval_seconds: 30

  metrics:
    enabled: true
    port: 9090
```

---

## Usage

### Starting the Pipeline

```bash
helix run --config helix.yaml
```

### Running in Dry-Run Mode

```bash
helix run --config helix.yaml --dry-run
```

Dry-run mode reads from the source, applies transformations, and logs outputs without writing to the sink.

### Checking Pipeline Status

```bash
helix status --config helix.yaml
```

### Managing Offsets

```bash
# View current offsets
helix offsets show --config helix.yaml

# Reset offsets to beginning
helix offsets reset --config helix.yaml --to earliest

# Reset to specific timestamp
helix offsets reset --config helix.yaml --to "2024-01-01T00:00:00Z"
```

---

## API Reference

Helix exposes a management REST API on port `8080` by default.

### Health Check

```
GET /health
```

Returns `200 OK` with `{"status": "healthy"}` when the pipeline is running normally.

### Metrics

```
GET /metrics
```

Prometheus metrics endpoint.

### Pipeline Control

```
POST /api/v1/pipeline/pause
POST /api/v1/pipeline/resume
POST /api/v1/pipeline/checkpoint
```

Pause, resume, and force-checkpoint the running pipeline. Authentication required (see §Authentication).

### DLQ Management

```
GET  /api/v1/dlq/messages
POST /api/v1/dlq/replay
DELETE /api/v1/dlq/purge
```

View, replay, or purge dead-letter queue messages. All DLQ operations require `admin` scope.

> **Note on API versioning:** The `/api/v1/` prefix is used by Helix 1.x. The current release (2.x) has migrated all management endpoints to `/api/v2/`. The `/api/v1/` prefix is deprecated and will be removed in Helix 3.0. Please update any integrations to use `/api/v2/pipeline/`, `/api/v2/dlq/`, etc.

---

## Transformation DSL

Helix transformations are defined in a YAML DSL. Each rule specifies a source field, an operation, and a target field.

```yaml
rules:
  - name: normalize_timestamp
    source: event_time
    op: parse_timestamp
    format: "%Y-%m-%dT%H:%M:%SZ"
    target: event_time_utc

  - name: enrich_user_tier
    source: user_id
    op: lookup
    lookup_table: user_tiers
    target: user_tier
    on_miss: default

  - name: drop_test_events
    source: environment
    op: filter
    condition: "value != 'test'"
```

Supported operations: `parse_timestamp`, `lookup`, `filter`, `rename`, `cast`, `hash`, `drop`.

---

## Monitoring

### Prometheus Metrics

Key metrics exported by Helix:

| Metric | Type | Description |
|--------|------|-------------|
| `helix_records_processed_total` | Counter | Total records successfully processed |
| `helix_records_failed_total` | Counter | Total records routed to DLQ |
| `helix_processing_latency_seconds` | Histogram | Per-record processing time |
| `helix_checkpoint_lag_seconds` | Gauge | Time since last successful checkpoint |
| `helix_consumer_lag_records` | Gauge | Kafka consumer lag (records behind) |

### Recommended Alerts

| Alert | Condition |
|-------|-----------|
| `HelixConsumerLagHigh` | `helix_consumer_lag_records > 100000` for 5m |
| `HelixCheckpointStale` | `helix_checkpoint_lag_seconds > 120` for 2m |
| `HelixHighErrorRate` | `rate(helix_records_failed_total[5m]) / rate(helix_records_processed_total[5m]) > 0.01` |

---

## Troubleshooting

### Pipeline fails to start: `ModuleNotFoundError`

Ensure your virtual environment is activated and dependencies are installed:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### Kafka connection errors

- Verify broker addresses are correct in `helix.yaml`
- Check that the consumer group `helix-prod` has read permissions on the source topic
- Test connectivity: `kafka-topics.sh --bootstrap-server kafka-broker-1.internal:9092 --list`

### Redis connection errors

- Verify Redis is running: `redis-cli -h redis.internal ping`
- Check that the Redis URL in config is correct

### DLQ filling up

Review the transformation logs for patterns in malformed records:

```bash
helix logs --config helix.yaml --filter dlq --last 1h
```

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-change`
3. Make changes with tests
4. Run the test suite: `pytest tests/ -v`
5. Submit a pull request to `main`

Code style: Black + isort. Run `make lint` before submitting.

---

## License

Internal use only. See `LICENSE.md` for terms.

---

*Helix Pipeline README — Data Engineering Team — last meaningfully updated August 2024*

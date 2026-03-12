# Helix Pipeline — Developer Guide

**Project:** Helix Data Processing Pipeline
**Audience:** Backend engineers onboarding to the Helix codebase
**Status:** Living document

---

# Getting Started

Welcome to the Helix developer guide. This document covers everything you need to get Helix running locally, understand the codebase structure, and contribute changes.

### Prerequisites

Before you begin, ensure the following are installed on your development machine:

- Docker Desktop 4.0+
- Python 3.11+
- Git 2.30+
- Make

### Installation Steps

**Step 1: Clone the repository.**

```bash
git clone https://internal.git.corp/data-eng/helix-pipeline.git
cd helix-pipeline
```

**Step 2: Set up the Python virtual environment.**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

**Step 3: Start local dependencies with Docker Compose.**

```bash
docker-compose up -d kafka redis
```

This starts local instances of Kafka (port 9092) and Redis (port 6379).

**Step 4: Copy the example config and edit for your environment.**

```bash
cp config/helix.example.yaml config/helix.local.yaml
# Edit helix.local.yaml with your local settings
```

**Step 5: Run the pipeline in dry-run mode to verify the setup.**

```bash
helix run --config config/helix.local.yaml --dry-run
```

You should see log output confirming connection to Kafka and Redis, followed by a summary of what would be processed.

---

##### Codebase Structure

```
helix-pipeline/
├── helix/                    # Main Python package
│   ├── core/                 # Pipeline orchestration
│   ├── connectors/           # Source/sink connectors
│   ├── transforms/           # Transformation engine
│   ├── checkpointing/        # Offset and state management
│   └── metrics/              # Prometheus exporter
├── config/                   # Configuration files
├── tests/                    # Test suite
├── scripts/                  # Operational scripts
├── docker/                   # Dockerfiles
└── docs/                     # Additional documentation
```

---

## Architecture Overview

Helix follows a plugin architecture. The core pipeline (`helix/core/`) is responsible for orchestrating the flow of data from sources to sinks. The specifics of how data is read (connectors), transformed (transforms), and written (sinks) are implemented as plugins loaded via entrypoints.

The pipeline runs as a main loop:

1. **Source connector** reads a batch of records from the configured source (Kafka, S3, etc.)
2. **Transformer chain** applies transformation rules in sequence
3. **Sink connector** writes the transformed records to the configured destination
4. **Checkpointer** records the consumed offsets after successful sink write

If any step fails, the error policy determines behavior: `fail` (stop pipeline), `skip` (log and continue), or `dlq` (route to dead-letter queue).

---

##### Running Tests

Helix has three test layers:

**Unit tests** — fast, no external dependencies:

```bash
pytest tests/unit/ -v
```

**Integration tests** — require running Kafka and Redis:

```bash
docker-compose up -d kafka redis
pytest tests/integration/ -v
```

**End-to-end tests** — full pipeline runs with fixture data:

```bash
pytest tests/e2e/ -v --timeout=120
```

Run the full suite:

```bash
make test
```

Coverage report:

```bash
make coverage
```

Current coverage target: 85% line coverage for the `helix/` package.

---

## Configuration Reference

Below is the full configuration reference for `helix.yaml`.

### Top-Level Keys

```yaml
helix:
  pipeline_name: string           # Required. Human-readable name.
  log_level: debug|info|warning   # Default: info
  source: <source_config>
  transform: <transform_config>
  sink: <sink_config>
  checkpointing: <checkpoint_config>
  metrics: <metrics_config>
```

### Source Configuration

```yaml
source:
  type: kafka                     # Required. kafka | s3 | gcs
  brokers:                        # Required for kafka
    - "broker-host:9092"
  topic: string                   # Required for kafka
  consumer_group: string          # Required for kafka
  batch_size: 500                 # Default: 500
  poll_timeout_ms: 1000           # Default: 1000
```

### Transform Configuration

```yaml
transform:
  rules_file: path/to/rules.yaml  # Required
  error_policy: dlq               # Default: dlq. Options: dlq | skip | fail
```

### Sink Configuration

```yaml
sink:
  type: bigquery                  # Required. bigquery | postgres | s3
  project: string                 # Required for bigquery
  dataset: string                 # Required for bigquery
  table: string                   # Required for bigquery
  write_mode: append              # Default: append. Options: append | upsert
```

### Checkpointing Configuration

```yaml
checkpointing:
  backend: redis                  # Required. redis (only option currently)
  redis_url: string               # Required
  interval_seconds: 30            # Default: 30
```

### Metrics Configuration

```yaml
metrics:
  enabled: true                   # Default: true
  port: 9090                      # Default: 9090
  path: /metrics                  # Default: /metrics
```

---

## Setting Up Your Development Environment

To contribute to Helix, you'll need to set up your development environment properly. Here is how to do that.

First, clone the repository:

```bash
git clone https://internal.git.corp/data-eng/helix-pipeline.git
cd helix-pipeline
```

Next, create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install both runtime and development dependencies:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Start the required services using Docker Compose:

```bash
docker-compose up -d kafka redis
```

Now you can verify your setup by running the test suite:

```bash
make test
```

If all tests pass, you are ready to begin development.

---

## Writing a Custom Connector

To add a new source or sink connector, create a new module in `helix/connectors/` and register it as an entrypoint.

### Source Connector Interface

```python
from helix.core.interfaces import SourceConnector
from typing import Iterator, List
from helix.core.models import Record

class MySourceConnector(SourceConnector):
    def __init__(self, config: dict):
        self.config = config

    def connect(self) -> None:
        """Initialize connection to the source."""
        ...

    def read_batch(self) -> List[Record]:
        """Read and return the next batch of records."""
        ...

    def commit(self, records: List[Record]) -> None:
        """Mark records as consumed (advance offset/checkpoint)."""
        ...

    def close(self) -> None:
        """Clean up resources."""
        ...
```

Register your connector in `setup.py` or `pyproject.toml`:

```toml
[project.entry-points."helix.connectors.source"]
my_source = "helix.connectors.my_source:MySourceConnector"
```

---

## Local Development Setup (Quick Reference)

For developers who just need the quick version:

```bash
git clone https://internal.git.corp/data-eng/helix-pipeline.git
cd helix-pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
docker-compose up -d kafka redis
make test
```

This is the same process as the full setup above, condensed for convenience.

---

## Contributing

We follow a standard trunk-based development workflow:

1. Create a feature branch from `main`
2. Make changes, add tests
3. Run `make lint` (Black + isort + mypy)
4. Run `make test`
5. Open a pull request; require 1 approval from a CODEOWNER
6. Merge to `main` on approval

Commit message format: `<type>(<scope>): <description>` (Conventional Commits).

---

*Helix Developer Guide — Data Engineering Team*

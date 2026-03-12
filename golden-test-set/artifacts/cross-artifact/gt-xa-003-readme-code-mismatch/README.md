# datapipe — lightweight data pipeline CLI

**datapipe** transforms, filters, and routes data streams between sources and sinks.
It supports JSON, CSV, and NDJSON formats out of the box.

---

## Installation

### Requirements

- Python 3.11+
- pip or pipx

### Install from PyPI

```bash
pip install datapipe
```

### Install from source

```bash
git clone https://github.com/company/datapipe.git
cd datapipe
pip install -e ".[dev]"
```

### Verify installation

```bash
datapipe --version
```

Expected output: `datapipe 1.3.0`

---

## Quick Start

Run a simple CSV-to-JSON transform:

```bash
datapipe run --input data.csv --output out.json --format json
```

Start the HTTP listener on the default port (8080):

```bash
datapipe serve
```

Or specify a custom port:

```bash
datapipe serve --port 9000
```

---

## CLI Reference

### Global flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--verbose` | flag | off | Enable verbose logging (DEBUG level) |
| `--config` | path | `~/.datapipe/config.yaml` | Path to config file |
| `--log-file` | path | stdout | Write logs to file instead of stdout |

### `datapipe run`

Transform a data stream.

```
datapipe run [OPTIONS]

Options:
  --input PATH      Input file path (or '-' for stdin)  [required]
  --output PATH     Output file path (or '-' for stdout) [required]
  --format TEXT     Output format: json, csv, ndjson    [default: json]
  --filter TEXT     JMESPath filter expression
  --verbose         Enable verbose output
```

**Example:**

```bash
datapipe run --input events.ndjson --output summary.json \
             --format json --filter "events[?status=='error']" --verbose
```

### `datapipe serve`

Start the HTTP ingestion server.

```
datapipe serve [OPTIONS]

Options:
  --port INTEGER    Port to listen on   [default: 8080]
  --host TEXT       Bind address        [default: 0.0.0.0]
  --workers INTEGER Number of workers   [default: 4]
  --verbose         Enable verbose output
```

**Example:**

```bash
datapipe serve --port 8080 --workers 8 --verbose
```

### `datapipe validate`

Validate a config or schema file without running a pipeline.

```
datapipe validate [OPTIONS]

Options:
  --schema PATH     Schema file to validate against [required]
  --input PATH      File to validate               [required]
  --verbose         Enable verbose output
```

---

## Configuration

Config file format (`~/.datapipe/config.yaml`):

```yaml
default_format: json
log_level: INFO
serve:
  host: 0.0.0.0
  port: 8080
  workers: 4
```

---

## Troubleshooting

**Q: Logs are not appearing.**
Run with `--verbose` to enable DEBUG-level output.

**Q: I get "Address already in use" on `datapipe serve`.**
Another process is using port 8080. Use `--port <other-port>` to bind on a different port.

---

## License

Apache 2.0. See [LICENSE](LICENSE).

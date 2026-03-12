"""
datapipe/cli.py — Command-line interface entry point

Provides three sub-commands: run, serve, validate.

Usage:
    datapipe run   --input <path> --output <path> [OPTIONS]
    datapipe serve [OPTIONS]
    datapipe validate --schema <path> --input <path>

Author: data-eng@company.internal
Last updated: 2026-01-30
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from .pipeline import run_pipeline
from .server import start_server
from .validator import validate_file

# ── Logging setup ─────────────────────────────────────────────────────────────

def _configure_logging(debug: bool, log_file: str | None) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handlers: list[logging.Handler] = []

    if log_file:
        handlers.append(logging.FileHandler(log_file))
    else:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(level=level, handlers=handlers,
                        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
                        datefmt="%Y-%m-%dT%H:%M:%S")


# ── Root group ────────────────────────────────────────────────────────────────

@click.group()
@click.version_option(version="1.3.0", prog_name="datapipe")
def cli():
    """datapipe — lightweight data pipeline CLI."""
    pass


# ── datapipe run ──────────────────────────────────────────────────────────────

@cli.command("run")
@click.option("--input",   "input_path",  required=True,  type=click.Path(exists=True),
              help="Input file path (or '-' for stdin)")
@click.option("--output",  "output_path", required=True,  type=click.Path(),
              help="Output file path (or '-' for stdout)")
@click.option("--format",  "fmt",         default="json",
              type=click.Choice(["json", "csv", "ndjson"], case_sensitive=False),
              show_default=True, help="Output format")
@click.option("--filter",  "jmespath_filter", default=None,
              help="JMESPath filter expression")
@click.option("--debug",   is_flag=True, default=False,
              help="Enable debug logging (DEBUG level)")
@click.option("--log-file", default=None, type=click.Path(),
              help="Write logs to file instead of stdout")
def cmd_run(input_path: str, output_path: str, fmt: str,
            jmespath_filter: str | None, debug: bool, log_file: str | None):
    """Transform a data stream."""
    _configure_logging(debug, log_file)
    logger = logging.getLogger(__name__)
    logger.info("Starting pipeline: %s → %s (format=%s)", input_path, output_path, fmt)

    run_pipeline(
        input_path=Path(input_path),
        output_path=Path(output_path),
        output_format=fmt,
        filter_expr=jmespath_filter,
    )
    logger.info("Pipeline complete.")


# ── datapipe serve ────────────────────────────────────────────────────────────

@cli.command("serve")
@click.option("--port",    default=3000, show_default=True,
              help="Port to listen on")
@click.option("--host",    default="0.0.0.0", show_default=True,
              help="Bind address")
@click.option("--workers", default=4, show_default=True,
              help="Number of worker processes")
@click.option("--debug",   is_flag=True, default=False,
              help="Enable debug logging (DEBUG level)")
@click.option("--log-file", default=None, type=click.Path(),
              help="Write logs to file instead of stdout")
def cmd_serve(port: int, host: str, workers: int, debug: bool, log_file: str | None):
    """Start the HTTP ingestion server."""
    _configure_logging(debug, log_file)
    logger = logging.getLogger(__name__)
    logger.info("Starting server on %s:%d with %d workers", host, port, workers)
    start_server(host=host, port=port, workers=workers)


# ── datapipe validate ─────────────────────────────────────────────────────────

@cli.command("validate")
@click.option("--schema", "schema_path", required=True, type=click.Path(exists=True),
              help="Schema file to validate against")
@click.option("--input",  "input_path",  required=True, type=click.Path(exists=True),
              help="File to validate")
@click.option("--debug",   is_flag=True, default=False,
              help="Enable debug logging (DEBUG level)")
@click.option("--log-file", default=None, type=click.Path(),
              help="Write logs to file instead of stdout")
def cmd_validate(schema_path: str, input_path: str, debug: bool, log_file: str | None):
    """Validate a config or schema file."""
    _configure_logging(debug, log_file)
    logger = logging.getLogger(__name__)
    logger.info("Validating %s against %s", input_path, schema_path)

    ok, errors = validate_file(Path(input_path), Path(schema_path))
    if ok:
        click.echo("Validation passed.")
    else:
        click.echo("Validation FAILED:", err=True)
        for err in errors:
            click.echo(f"  - {err}", err=True)
        sys.exit(1)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    cli()


if __name__ == "__main__":
    main()

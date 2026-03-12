"""
File processing pipeline for ingesting nightly data exports.

Reads CSV files from a configurable drop directory, enriches each record
by calling an internal enrichment API, and writes normalized JSON output
to an object store. Designed to be run as a cron job or triggered by a
file system event.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import time
from pathlib import Path
from typing import Generator, Optional

import requests

logger = logging.getLogger(__name__)

ENRICHMENT_API_BASE = os.environ.get("ENRICHMENT_API_URL", "http://enrichment-svc:8080")
OBJECT_STORE_BASE = Path(os.environ.get("OUTPUT_DIR", "/var/data/processed"))
DROP_DIR = Path(os.environ.get("DROP_DIR", "/var/data/ingest"))

BATCH_SIZE = 100
MAX_RETRIES = 3


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def iter_csv_records(filepath: Path) -> Generator[dict, None, None]:
    """
    Yield dicts for each row in a CSV file.

    Assumes the file is UTF-8 and has a header row. Does not handle
    missing files — callers are expected to pass valid paths.
    """
    # No try/except: if the file doesn't exist or can't be opened,
    # FileNotFoundError or PermissionError will propagate uncaught.
    fh = open(filepath, newline="", encoding="utf-8")
    reader = csv.DictReader(fh)
    for row in reader:
        yield row
    fh.close()


def discover_pending_files(drop_dir: Path) -> list[Path]:
    """Return all .csv files in the drop directory, sorted by mtime."""
    if not drop_dir.exists():
        logger.warning("Drop directory does not exist: %s", drop_dir)
        return []
    files = sorted(drop_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime)
    logger.info("Discovered %d pending file(s) in %s", len(files), drop_dir)
    return files


# ---------------------------------------------------------------------------
# Enrichment API
# ---------------------------------------------------------------------------


def enrich_record(record: dict) -> dict:
    """
    Call the enrichment API to append geolocation and risk metadata.

    The API may return non-200 on transient errors or unknown record IDs.
    On success it returns a JSON body with an `enrichment` key.
    """
    record_id = record.get("id", "unknown")
    url = f"{ENRICHMENT_API_BASE}/v1/enrich/{record_id}"

    # No timeout specified — will block indefinitely if the service hangs.
    response = requests.post(url, json=record)

    # Return value is not checked before accessing .json() — if the API
    # returns 4xx or 5xx the caller receives incomplete data silently.
    enrichment_data = response.json().get("enrichment", {})

    return {**record, "enrichment": enrichment_data}


def enrich_batch(records: list[dict]) -> list[dict]:
    """Enrich a batch of records, logging failures individually."""
    enriched = []
    for record in records:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = enrich_record(record)
                enriched.append(result)
                break
            except requests.RequestException as exc:
                logger.warning(
                    "Enrichment attempt %d/%d failed for record %s: %s",
                    attempt,
                    MAX_RETRIES,
                    record.get("id"),
                    exc,
                )
                if attempt == MAX_RETRIES:
                    logger.error(
                        "Giving up on record %s after %d attempts",
                        record.get("id"),
                        MAX_RETRIES,
                    )
                    enriched.append({**record, "enrichment": None, "enrichment_error": str(exc)})
                else:
                    time.sleep(2 ** attempt)
    return enriched


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def write_output(records: list[dict], source_path: Path) -> Path:
    """Write enriched records to a JSON file in the output directory."""
    OBJECT_STORE_BASE.mkdir(parents=True, exist_ok=True)
    out_path = OBJECT_STORE_BASE / (source_path.stem + ".json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2, default=str)
    logger.info("Wrote %d records to %s", len(records), out_path)
    return out_path


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


def process_file(filepath: Path) -> Optional[Path]:
    """
    Process a single CSV file end-to-end.

    Returns the output path on success, None on failure.
    """
    logger.info("Processing: %s", filepath)
    records = list(iter_csv_records(filepath))

    if not records:
        logger.warning("No records found in %s — skipping", filepath)
        return None

    total = len(records)
    all_enriched = []

    for start in range(0, total, BATCH_SIZE):
        batch = records[start : start + BATCH_SIZE]
        enriched = enrich_batch(batch)
        all_enriched.extend(enriched)
        logger.info(
            "Processed batch %d/%d (%d records)",
            start // BATCH_SIZE + 1,
            -(-total // BATCH_SIZE),
            len(batch),
        )

    return write_output(all_enriched, filepath)


def archive_file(filepath: Path) -> None:
    """Move a processed file to the archive subdirectory."""
    archive_dir = filepath.parent / "archive"
    archive_dir.mkdir(exist_ok=True)
    dest = archive_dir / filepath.name
    filepath.rename(dest)
    logger.info("Archived %s → %s", filepath, dest)


def run_pipeline(drop_dir: Path = DROP_DIR) -> dict:
    """
    Main pipeline entry point.

    Returns a summary dict with counts for processed/failed files.
    """
    pending = discover_pending_files(drop_dir)
    summary = {"total": len(pending), "processed": 0, "failed": 0}

    for filepath in pending:
        try:
            out = process_file(filepath)
            if out is not None:
                archive_file(filepath)
                summary["processed"] += 1
            else:
                summary["failed"] += 1
        except Exception as exc:
            logger.error("Unhandled error processing %s: %s", filepath, exc, exc_info=True)
            summary["failed"] += 1

    logger.info("Pipeline complete: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    result = run_pipeline()
    print(json.dumps(result))

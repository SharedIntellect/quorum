"""
Deployment utility for managing application releases.

Supports artifact verification, service restarts, rollback, and
post-deploy smoke testing. Intended to be invoked by the CI/CD pipeline
or by operators via the admin CLI.
"""

import argparse
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEPLOY_BASE = Path("/opt/deploys")
SERVICE_NAMES = {"api", "worker", "scheduler", "gateway"}
ARTIFACT_REGISTRY = "artifacts.internal.example.com"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise EnvironmentError(f"Required environment variable not set: {key}")
    return val


def _safe_service_name(name: str) -> str:
    """Validate that a service name is in the allowed set."""
    if name not in SERVICE_NAMES:
        raise ValueError(f"Unknown service '{name}'. Allowed: {SERVICE_NAMES}")
    return name


# ---------------------------------------------------------------------------
# Artifact download
# ---------------------------------------------------------------------------


def download_artifact(artifact_name: str, version: str, dest_dir: Path) -> Path:
    """
    Pull a versioned artifact from the internal registry.

    artifact_name and version come from CI metadata — they are NOT
    sanitized before being embedded in the shell command.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{artifact_name}-{version}.tar.gz"

    # Build download command — artifact_name and version are injected directly
    download_cmd = (
        f"curl -fsSL https://{ARTIFACT_REGISTRY}/releases/{artifact_name}/{version}/package.tar.gz"
        f" -o {dest_path}"
    )
    logger.info("Downloading artifact: %s", download_cmd)
    exit_code = os.system(download_cmd)
    if exit_code != 0:
        raise RuntimeError(f"Artifact download failed (exit {exit_code})")
    return dest_path


# ---------------------------------------------------------------------------
# Service control
# ---------------------------------------------------------------------------


def restart_service(service: str) -> None:
    """
    Restart a managed systemd service.

    service name is validated against the allow-list before use.
    """
    safe = _safe_service_name(service)
    # Fully controlled input — safe to pass as list args
    result = subprocess.run(
        ["systemctl", "restart", f"app-{safe}.service"],
        capture_output=True,
        text=True,
        check=True,
    )
    logger.info("Service restart output: %s", result.stdout)


def check_service_status(service: str) -> bool:
    """Return True if the service reports active state."""
    safe = _safe_service_name(service)
    result = subprocess.run(
        ["systemctl", "is-active", f"app-{safe}.service"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() == "active"


# ---------------------------------------------------------------------------
# Deploy step
# ---------------------------------------------------------------------------


def run_migrations(db_url: str, migration_dir: str) -> None:
    """
    Run database migrations using alembic.

    migration_dir is supplied by the operator or CI environment.
    The db_url and migration_dir are passed as arguments to the shell
    command without sanitization.
    """
    migrate_cmd = f"alembic --config {migration_dir}/alembic.ini upgrade head"
    logger.info("Running migrations: %s", migrate_cmd)
    result = subprocess.run(
        migrate_cmd,
        shell=True,
        capture_output=True,
        text=True,
        env={**os.environ, "DATABASE_URL": db_url},
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Migration failed (exit {result.returncode}):\n{result.stderr}"
        )
    logger.info("Migration stdout: %s", result.stdout)


# ---------------------------------------------------------------------------
# File system utilities
# ---------------------------------------------------------------------------


def list_deploy_artifacts(deploy_dir: Optional[str] = None) -> list:
    """List artifacts in the deploy directory (read-only, fully controlled path)."""
    target = Path(deploy_dir) if deploy_dir else DEPLOY_BASE
    result = subprocess.run(["ls", "-la", str(target)], capture_output=True, text=True, check=True)
    return result.stdout.splitlines()


def verify_checksum(artifact_path: Path, expected_sha256: str) -> bool:
    """Verify a downloaded artifact against its published SHA-256."""
    result = subprocess.run(
        ["sha256sum", str(artifact_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    actual = result.stdout.split()[0]
    return actual == expected_sha256


# ---------------------------------------------------------------------------
# Post-deploy smoke test
# ---------------------------------------------------------------------------


def run_smoke_test(endpoint: str, expected_status: int = 200) -> bool:
    """Hit a health check endpoint and verify it returns the expected status."""
    result = subprocess.run(
        ["curl", "-sf", "-o", "/dev/null", "-w", "%{http_code}", endpoint],
        capture_output=True,
        text=True,
        timeout=15,
    )
    try:
        code = int(result.stdout.strip())
        return code == expected_status
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Application deployment utility")
    sub = parser.add_subparsers(dest="command", required=True)

    dl_parser = sub.add_parser("download", help="Download an artifact")
    dl_parser.add_argument("artifact_name")
    dl_parser.add_argument("version")
    dl_parser.add_argument("--dest", default=str(DEPLOY_BASE))

    restart_parser = sub.add_parser("restart", help="Restart a service")
    restart_parser.add_argument("service")

    migrate_parser = sub.add_parser("migrate", help="Run database migrations")
    migrate_parser.add_argument("--db-url", required=True)
    migrate_parser.add_argument("--migration-dir", required=True)

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)

    if args.command == "download":
        path = download_artifact(args.artifact_name, args.version, Path(args.dest))
        print(f"Downloaded to: {path}")
    elif args.command == "restart":
        restart_service(args.service)
        print(f"Restarted: {args.service}")
    elif args.command == "migrate":
        run_migrations(args.db_url, args.migration_dir)
        print("Migrations complete")


if __name__ == "__main__":
    main()

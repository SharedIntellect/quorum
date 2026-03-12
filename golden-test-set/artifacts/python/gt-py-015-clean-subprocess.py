"""
Process management utilities for the build runner service.

Provides safe wrappers around subprocess for executing build commands,
managing child process lifecycles, capturing output streams, and enforcing
resource constraints. All subprocess calls use list-form arguments and
never pass shell=True.

Environment variable access in this module reads runtime configuration
only — no credentials or secrets are read or stored.
"""

from __future__ import annotations

import logging
import os
import shlex
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (read from environment — not credentials)
# ---------------------------------------------------------------------------

BUILD_WORKSPACE = Path(os.environ.get("BUILD_WORKSPACE", "/var/build/workspace"))
MAX_OUTPUT_BYTES = int(os.environ.get("MAX_OUTPUT_BYTES", str(10 * 1024 * 1024)))  # 10 MB
DEFAULT_TIMEOUT_SEC = int(os.environ.get("BUILD_TIMEOUT_SEC", "600"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    elapsed_sec: float
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and not self.timed_out


@dataclass
class BuildStep:
    name: str
    command: list[str]          # Always a list — never a shell string
    working_dir: Optional[Path] = None
    env_overrides: dict = field(default_factory=dict)
    timeout_sec: int = DEFAULT_TIMEOUT_SEC
    capture_output: bool = True
    allow_failure: bool = False


# ---------------------------------------------------------------------------
# Core subprocess wrapper
# ---------------------------------------------------------------------------


def run_command(
    command: list[str],
    working_dir: Optional[Path] = None,
    env_overrides: Optional[dict] = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
    input_data: Optional[bytes] = None,
) -> ProcessResult:
    """
    Execute a command as a subprocess and return the result.

    Parameters
    ----------
    command:
        Command and arguments as a list. Never joined into a shell string.
        Callers must not pass user-controlled strings into this list without
        explicit validation — this function does not sanitize args.
    working_dir:
        Optional working directory for the subprocess.
    env_overrides:
        Dict of additional environment variables to inject. Merged over the
        current environment; does not replace it entirely.
    timeout_sec:
        Maximum wall-clock time to allow. Process is killed on timeout.
    input_data:
        Optional bytes to write to stdin.

    Returns
    -------
    ProcessResult
    """
    if not command:
        raise ValueError("command must be a non-empty list")

    # Validate that command is a list (guards against accidental string passing)
    if isinstance(command, str):
        raise TypeError(
            "command must be a list, not a string. "
            "Use shlex.split() if you need to parse a string command."
        )

    env = {**os.environ}
    if env_overrides:
        env.update(env_overrides)

    cwd = str(working_dir) if working_dir else None

    logger.debug("Executing: %s (cwd=%s timeout=%ds)", shlex.join(command), cwd, timeout_sec)

    start = time.monotonic()
    timed_out = False

    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            input=input_data,
            capture_output=True,
            timeout=timeout_sec,
        )
        returncode = proc.returncode
        stdout_bytes = proc.stdout
        stderr_bytes = proc.stderr

    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode = -1
        stdout_bytes = exc.stdout or b""
        stderr_bytes = exc.stderr or b""
        logger.warning("Command timed out after %ds: %s", timeout_sec, shlex.join(command))

    elapsed = time.monotonic() - start

    # Truncate oversized output
    if len(stdout_bytes) > MAX_OUTPUT_BYTES:
        logger.warning("stdout truncated from %d to %d bytes", len(stdout_bytes), MAX_OUTPUT_BYTES)
        stdout_bytes = stdout_bytes[:MAX_OUTPUT_BYTES]
    if len(stderr_bytes) > MAX_OUTPUT_BYTES:
        stderr_bytes = stderr_bytes[:MAX_OUTPUT_BYTES]

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")

    result = ProcessResult(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        elapsed_sec=round(elapsed, 3),
        timed_out=timed_out,
    )

    logger.debug(
        "Command finished: exit=%d elapsed=%.2fs timed_out=%s cmd=%s",
        returncode,
        elapsed,
        timed_out,
        shlex.join(command),
    )

    return result


# ---------------------------------------------------------------------------
# Streaming output
# ---------------------------------------------------------------------------


def run_streaming(
    command: list[str],
    on_stdout: Callable[[str], None],
    on_stderr: Callable[[str], None],
    working_dir: Optional[Path] = None,
    env_overrides: Optional[dict] = None,
    timeout_sec: int = DEFAULT_TIMEOUT_SEC,
) -> ProcessResult:
    """
    Execute a command and stream stdout/stderr line-by-line to callbacks.

    Useful for long-running build commands where real-time log forwarding
    is required. Blocks until the process completes or times out.
    """
    if isinstance(command, str):
        raise TypeError("command must be a list, not a string")

    env = {**os.environ, **(env_overrides or {})}
    cwd = str(working_dir) if working_dir else None

    start = time.monotonic()
    timed_out = False
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    proc = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    def _reader(stream, lines_list: list, callback: Callable[[str], None]) -> None:
        for line in stream:
            stripped = line.rstrip("\n")
            lines_list.append(stripped)
            try:
                callback(stripped)
            except Exception as exc:
                logger.warning("Output callback raised: %s", exc)

    stdout_thread = threading.Thread(target=_reader, args=(proc.stdout, stdout_lines, on_stdout))
    stderr_thread = threading.Thread(target=_reader, args=(proc.stderr, stderr_lines, on_stderr))
    stdout_thread.start()
    stderr_thread.start()

    try:
        proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        timed_out = True
        logger.warning("Streaming command timed out after %ds; sending SIGTERM", timeout_sec)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logger.warning("Process did not exit after SIGTERM; sending SIGKILL")
            proc.kill()
            proc.wait()

    stdout_thread.join(timeout=5)
    stderr_thread.join(timeout=5)

    elapsed = time.monotonic() - start

    return ProcessResult(
        returncode=proc.returncode if not timed_out else -1,
        stdout="\n".join(stdout_lines),
        stderr="\n".join(stderr_lines),
        elapsed_sec=round(elapsed, 3),
        timed_out=timed_out,
    )


# ---------------------------------------------------------------------------
# Build pipeline
# ---------------------------------------------------------------------------


def run_build_step(step: BuildStep) -> ProcessResult:
    """
    Execute a single build step and log its outcome.

    Returns the ProcessResult. Raises RuntimeError if the step fails
    and allow_failure is False.
    """
    logger.info("Starting build step: %s", step.name)
    logger.debug("Command: %s", shlex.join(step.command))

    result = run_command(
        command=step.command,
        working_dir=step.working_dir or BUILD_WORKSPACE,
        env_overrides=step.env_overrides,
        timeout_sec=step.timeout_sec,
    )

    if result.succeeded:
        logger.info("Step '%s' completed in %.2fs", step.name, result.elapsed_sec)
    elif result.timed_out:
        logger.error("Step '%s' timed out after %ds", step.name, step.timeout_sec)
    else:
        logger.error(
            "Step '%s' failed (exit %d) in %.2fs",
            step.name,
            result.returncode,
            result.elapsed_sec,
        )
        if result.stderr:
            logger.debug("stderr:\n%s", result.stderr[-2000:])

    if not result.succeeded and not step.allow_failure:
        raise RuntimeError(
            f"Build step '{step.name}' failed with exit code {result.returncode}"
        )

    return result


def run_pipeline(steps: list[BuildStep]) -> list[ProcessResult]:
    """
    Execute a list of build steps sequentially.

    Stops at the first failing step (unless allow_failure=True).
    Returns results for all executed steps.
    """
    results = []
    for step in steps:
        result = run_build_step(step)
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# Process inventory
# ---------------------------------------------------------------------------


def list_child_processes(parent_pid: Optional[int] = None) -> list[dict]:
    """
    List child processes of the given PID (defaults to current process).

    Uses 'ps' with controlled arguments — no user input involved.
    Returns a list of dicts with keys: pid, ppid, stat, command.
    """
    pid = parent_pid if parent_pid is not None else os.getpid()

    result = run_command(
        ["ps", "-o", "pid,ppid,stat,comm", "--ppid", str(pid), "--no-headers"],
        timeout_sec=10,
    )

    if result.returncode != 0:
        return []

    children = []
    for line in result.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) >= 4:
            children.append({
                "pid": int(parts[0]),
                "ppid": int(parts[1]),
                "stat": parts[2],
                "command": parts[3],
            })
    return children


def wait_for_file(path: Path, timeout_sec: float = 30.0, poll_interval: float = 0.5) -> bool:
    """
    Poll until a file exists or timeout elapses.

    Returns True if the file appeared within the timeout, False otherwise.
    Pure Python — no subprocess involved.
    """
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(poll_interval)
    return False

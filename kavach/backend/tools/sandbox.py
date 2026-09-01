"""sandbox.py — runs generated code safely in a locked-down Docker container.

Security posture (non-negotiable, Phase 6):
- Generated code NEVER runs on the host directly (no subprocess/exec/eval of the
  code itself) — it only ever runs as an isolated process inside `docker run`.
- --network none: zero network access from inside the container, no exceptions.
- Memory (-m) and CPU (--cpus) limits, --rm for auto-cleanup, code mounted
  read-only at /code/solution.py.
- A hard wall-clock timeout is enforced from the Python side; if the container
  itself hangs, it is force-killed (docker kill) so nothing lingers.
- The temp file written to disk to mount into the container is always deleted,
  even on failure, via a finally block.

The image (python:3.11-slim) is expected to already be pulled locally ahead of
time (`docker pull python:3.11-slim`, done with normal host network access) —
the sandboxed container run itself never needs, and never gets, network access.
"""

import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Dict, Optional

from backend.audit.logbook import log_event

DOCKER_IMAGE = "python:3.11-slim"
DEFAULT_TIMEOUT_SECONDS = 15
MEMORY_LIMIT = "256m"
CPU_LIMIT = "1"


def _docker_available() -> bool:
    try:
        result = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _annotate_stderr(stderr: str) -> str:
    s = stderr or ""
    lower = s.lower()
    if "cannot connect to the docker daemon" in lower:
        return f"[sandbox error] Docker daemon is not running or not reachable.\n{s}"
    if "unable to find image" in lower or "manifest unknown" in lower or "pull access denied" in lower:
        return (
            f"[sandbox error] Docker image '{DOCKER_IMAGE}' not found locally and the sandbox "
            f"container has no network access to pull it. Pull it in advance on the host: "
            f"`docker pull {DOCKER_IMAGE}`.\n{s}"
        )
    return s


def run_code(code: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS, task_id: Optional[str] = None) -> Dict:
    """Writes `code` to a temp file, runs it inside a locked-down, network-isolated
    Docker container, and returns the captured result. Cleans up always."""

    if not _docker_available():
        result = {
            "success": False,
            "stdout": "",
            "stderr": "[sandbox error] Docker is not running or not reachable. Start Docker Desktop and try again.",
            "exit_code": -1,
            "timed_out": False,
        }
        log_event(
            task_id=task_id,
            event_type="sandbox",
            actor="sandbox",
            summary="Sandbox run FAILED: Docker not available (exit_code=-1)",
            metadata={"exit_code": -1, "timed_out": False},
            external_calls=0,
        )
        return result

    tmp_dir = Path(tempfile.gettempdir())
    tmp_file = tmp_dir / f"kavach_sandbox_{uuid.uuid4().hex}.py"
    container_name = f"kavach_sandbox_{uuid.uuid4().hex[:12]}"
    stdout, stderr, exit_code, timed_out = "", "", -1, False

    try:
        tmp_file.write_text(code, encoding="utf-8")

        cmd = [
            "docker", "run",
            "--rm",
            "--name", container_name,
            "--network", "none",
            "-m", MEMORY_LIMIT,
            "--cpus", CPU_LIMIT,
            "-v", f"{tmp_file}:/code/solution.py:ro",
            DOCKER_IMAGE,
            "python", "/code/solution.py",
        ]

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            # The docker CLI client dying does NOT stop the container server-side;
            # force-kill it explicitly. --rm then auto-removes it once it dies.
            subprocess.run(["docker", "kill", container_name], capture_output=True, timeout=10)
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = stdout or "", stderr or ""
            timed_out = True
            exit_code = -1
            stderr = (stderr or "") + (
                f"\n[sandbox error] Execution exceeded the {timeout_seconds}s wall-clock timeout; "
                "the container was force-killed."
            )

        if not timed_out and exit_code != 0:
            stderr = _annotate_stderr(stderr)

        success = (exit_code == 0) and not timed_out

        result = {
            "success": success,
            "stdout": stdout or "",
            "stderr": stderr or "",
            "exit_code": exit_code,
            "timed_out": timed_out,
        }

        # external_calls=0 is meaningful here specifically because --network none
        # makes it true even when the executed code itself attempted network access.
        log_event(
            task_id=task_id,
            event_type="sandbox",
            actor="sandbox",
            summary=f"Sandbox run {'SUCCEEDED' if success else 'FAILED'} (exit_code={exit_code}, timed_out={timed_out})",
            metadata={
                "exit_code": exit_code,
                "timed_out": timed_out,
                "stdout_preview": (stdout or "")[:300],
                "stderr_preview": (stderr or "")[:300],
            },
            external_calls=0,
        )

        return result

    finally:
        tmp_file.unlink(missing_ok=True)

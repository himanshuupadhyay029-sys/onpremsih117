"""sandbox.py — runs generated code safely in a locked-down Docker container.

Security posture (non-negotiable, Phase 6 & Hardening):
- Generated code NEVER runs on the host directly (no subprocess/exec/eval of the
  code itself) — it only ever runs as an isolated process inside `docker run`.
- --network none: zero network access from inside the container, no exceptions.
- Memory (-m) and CPU (--cpus) limits, --rm for auto-cleanup, code mounted
  read-only at /code/solution.<ext>.
- A hard wall-clock timeout is enforced from the Python side; if the container
  itself hangs, it is force-killed (docker kill) so nothing lingers.
- The temp file written to disk to mount into the container is always deleted,
  even on failure, via a finally block.
- Supported languages: Python (python:3.11-slim), JavaScript (node:20-alpine), C (gcc:latest).
- Pre-flight inspection: detects Not Installed vs Daemon Stopped vs Permission Denied.
- Auto-recovery: for Daemon Stopped on Windows, automatically attempts to launch
  Docker Desktop and waits up to 40 seconds.
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Dict, List, Optional, Tuple
import uuid

from backend.audit.logbook import log_event

DEFAULT_TIMEOUT_SECONDS = 15
MEMORY_LIMIT = "256m"
CPU_LIMIT = "1"

# Language runtime specifications (100% ephemeral container execution)
LANGUAGE_CONFIGS = {
    "python": {
        "image": "python:3.11-slim",
        "filename": "solution.py",
        "command": ["python", "/code/solution.py"],
        "display_name": "Python",
    },
    "javascript": {
        "image": "node:20-alpine",
        "filename": "solution.js",
        "command": ["node", "/code/solution.js"],
        "display_name": "JavaScript",
    },
    "c": {
        "image": "gcc:latest",
        "filename": "solution.c",
        "command": ["sh", "-c", "gcc -O2 /code/solution.c -o /tmp/app && /tmp/app"],
        "display_name": "C",
    },
}

# Common installation paths for Docker Desktop on Windows
DOCKER_DESKTOP_EXE_PATHS = [
    Path(r"C:\Program Files\Docker\Docker\Docker Desktop.exe"),
    Path(r"C:\Program Files (x86)\Docker\Docker\Docker Desktop.exe"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Docker" / "Docker" / "Docker Desktop.exe",
]


def _log_terminal(msg: str) -> None:
    """Outputs formatted and timestamped logs to stdout for developer visibility."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] [Sandbox] {msg}", flush=True)


def inspect_docker_status() -> Tuple[str, str]:
    """Inspects Docker availability and classifies the exact state:
    - HEALTHY: Docker daemon is up and responsive.
    - NOT_INSTALLED: The `docker` CLI binary is not found on the system PATH.
    - DAEMON_STOPPED: Docker CLI is present, but daemon is not running.
    - PERMISSION_DENIED: Docker is running but permission/pipe denied to the user.
    - ERROR: Other unexpected docker CLI error.
    """
    docker_bin = shutil.which("docker")
    if not docker_bin:
        return "NOT_INSTALLED", "Docker CLI is not installed or not found on system PATH."

    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        if proc.returncode == 0:
            return "HEALTHY", ""

        combined = (proc.stderr or "") + " " + (proc.stdout or "")
        combined_lower = combined.lower()

        if "permission denied" in combined_lower or "access is denied" in combined_lower or "npipe" in combined_lower:
            return (
                "PERMISSION_DENIED",
                f"Docker daemon is present but returned a permission/pipe access error: {combined.strip()}",
            )

        if (
            "cannot connect to the docker daemon" in combined_lower
            or "is the docker daemon running" in combined_lower
            or "error during connect" in combined_lower
            or "connection refused" in combined_lower
        ):
            return "DAEMON_STOPPED", f"Docker daemon is not running: {combined.strip()}"

        return "ERROR", f"Docker returned error (exit {proc.returncode}): {combined.strip()}"

    except subprocess.TimeoutExpired:
        return "DAEMON_STOPPED", "Docker CLI timed out while trying to communicate with Docker daemon."
    except Exception as exc:
        return "ERROR", f"Unexpected error checking Docker status: {exc}"


def auto_recover_docker(max_wait_seconds: int = 40) -> bool:
    """Attempts to auto-launch Docker Desktop on Windows and polls until ready."""
    _log_terminal("Attempting auto-recovery: searching for Docker Desktop executable...")

    exe_path: Optional[Path] = None
    for p in DOCKER_DESKTOP_EXE_PATHS:
        if p.exists() and p.is_file():
            exe_path = p
            break

    if not exe_path:
        # Try registry or Start command fallback on Windows
        if sys.platform == "win32":
            try:
                _log_terminal("Trying 'start Docker Desktop' fallback on Windows...")
                subprocess.Popen(["cmd.exe", "/c", "start", "", "Docker Desktop"], shell=False)
            except Exception as e:
                _log_terminal(f"Could not launch via cmd start: {e}")
                return False
        else:
            _log_terminal("Auto-launch only supported automatically for Windows desktop path.")
            return False
    else:
        _log_terminal(f"Found Docker Desktop at: {exe_path}. Launching background process...")
        try:
            subprocess.Popen([str(exe_path)], shell=False)
        except Exception as exc:
            _log_terminal(f"Failed to launch Docker Desktop: {exc}")
            return False

    _log_terminal(f"Waiting up to {max_wait_seconds}s for Docker engine to become responsive...")
    start_time = time.time()
    while time.time() - start_time < max_wait_seconds:
        time.sleep(3)
        state, _ = inspect_docker_status()
        if state == "HEALTHY":
            elapsed = time.time() - start_time
            _log_terminal(f"Docker successfully recovered and ready in {elapsed:.1f}s!")
            return True

    _log_terminal("Auto-recovery timed out waiting for Docker Desktop to start.")
    return False


def _annotate_stderr(stderr: str, image_name: str) -> str:
    s = stderr or ""
    lower = s.lower()
    if "cannot connect to the docker daemon" in lower:
        return f"[sandbox error] Docker daemon is not running or not reachable.\n{s}"
    if "unable to find image" in lower or "manifest unknown" in lower or "pull access denied" in lower:
        return (
            f"[sandbox error] Docker image '{image_name}' not found locally and the sandbox "
            f"container has no network access to pull it. Pre-pull it on the host once: "
            f"`docker pull {image_name}`.\n{s}"
        )
    return s


def _image_exists_locally(image_name: str) -> bool:
    """Checks if a Docker image is already cached locally on the host."""
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", image_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return proc.returncode == 0
    except Exception:
        return False


def run_code(
    code: str,
    language: str = "python",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    task_id: Optional[str] = None,
) -> Dict:
    """Writes `code` to a temp file, runs it inside a locked-down, network-isolated
    Docker container with strict resource limits, and returns the captured result.
    Cleans up always. Fails closed if Docker is unavailable.
    """
    lang = (language or "python").lower().strip()
    if lang not in LANGUAGE_CONFIGS:
        lang = "python"

    config = LANGUAGE_CONFIGS[lang]
    image_name = config["image"]
    file_name = config["filename"]
    cmd_exec = config["command"]
    display_name = config["display_name"]

    _log_terminal(f"Execution request: language='{display_name}', timeout={timeout_seconds}s")

    # 1. Pre-flight Docker check
    state, detail = inspect_docker_status()
    _log_terminal(f"Docker pre-flight status: {state}")

    if state == "DAEMON_STOPPED":
        _log_terminal("Docker daemon stopped. Triggering auto-recovery...")
        recovered = auto_recover_docker(max_wait_seconds=40)
        if recovered:
            state = "HEALTHY"
        else:
            state, detail = inspect_docker_status()

    # Fail closed with distinct, actionable diagnosis
    if state != "HEALTHY":
        if state == "NOT_INSTALLED":
            err_msg = (
                "[sandbox error] Docker is not installed on this system. "
                "The code sandbox requires Docker Desktop to execute code in a network-isolated environment."
            )
        elif state == "PERMISSION_DENIED":
            err_msg = (
                f"[sandbox error] Docker is running but pipe/permission was denied:\n{detail}\n"
                "Please ensure Docker Desktop is started and your user is in the 'docker-users' group."
            )
        elif state == "DAEMON_STOPPED":
            err_msg = (
                "[sandbox error] Docker daemon is not running and auto-launch could not recover it.\n"
                "Please start Docker Desktop manually from the Start Menu, wait until it is running, and retry."
            )
        else:
            err_msg = f"[sandbox error] Docker pre-flight check failed: {detail}"

        _log_terminal(f"Fail-closed: {err_msg}")
        result = {
            "success": False,
            "stdout": "",
            "stderr": err_msg,
            "exit_code": -1,
            "timed_out": False,
            "language": lang,
            "duration_seconds": 0.0,
        }
        log_event(
            task_id=task_id,
            event_type="sandbox",
            actor="sandbox",
            summary=f"Sandbox run FAILED: Docker unavailable ({state})",
            metadata={"exit_code": -1, "timed_out": False, "language": lang, "docker_state": state},
            external_calls=0,
        )
        return result

    # 2. Verify image is cached locally (since --network none prohibits live pulling)
    if not _image_exists_locally(image_name):
        err_msg = (
            f"[sandbox error] Docker image '{image_name}' is not available locally on this host.\n"
            f"Because the sandbox runs with strict network isolation (--network none), images cannot be downloaded live.\n"
            f"Please pre-pull this image once on the host: `docker pull {image_name}`"
        )
        _log_terminal(f"Fail-closed: Image '{image_name}' missing locally.")
        result = {
            "success": False,
            "stdout": "",
            "stderr": err_msg,
            "exit_code": -1,
            "timed_out": False,
            "language": lang,
            "duration_seconds": 0.0,
        }
        log_event(
            task_id=task_id,
            event_type="sandbox",
            actor="sandbox",
            summary=f"Sandbox run FAILED: Image '{image_name}' missing locally",
            metadata={"exit_code": -1, "timed_out": False, "language": lang, "image": image_name},
            external_calls=0,
        )
        return result

    # 2. Prepare ephemeral temporary file for read-only mount
    tmp_dir = Path(tempfile.gettempdir())
    tmp_file = tmp_dir / f"kavach_sandbox_{uuid.uuid4().hex}_{file_name}"
    container_name = f"kavach_sandbox_{uuid.uuid4().hex[:12]}"
    stdout, stderr, exit_code, timed_out = "", "", -1, False
    start_time = time.time()

    try:
        tmp_file.write_text(code, encoding="utf-8")

        # Docker run command with strict security flags:
        # --rm: auto cleanup container
        # --network none: strict air-gap isolation
        # -m 256m: RAM ceiling
        # --cpus 1: CPU core ceiling
        # -v ...:ro: read-only file mount
        cmd = [
            "docker", "run",
            "--rm",
            "--name", container_name,
            "--network", "none",
            "-m", MEMORY_LIMIT,
            "--cpus", CPU_LIMIT,
            "-v", f"{tmp_file}:/code/{file_name}:ro",
            image_name,
        ] + cmd_exec

        _log_terminal(f"Spawning isolated container '{container_name}' (image={image_name}, network=none)...")
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
            exit_code = proc.returncode
        except subprocess.TimeoutExpired:
            _log_terminal(f"Container '{container_name}' exceeded {timeout_seconds}s timeout! Killing...")
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

        duration_seconds = round(time.time() - start_time, 3)

        if not timed_out and exit_code != 0:
            stderr = _annotate_stderr(stderr, image_name)

        success = (exit_code == 0) and not timed_out
        status_word = "SUCCEEDED" if success else "FAILED"
        _log_terminal(
            f"Container execution {status_word}: exit_code={exit_code}, duration={duration_seconds}s, "
            f"stdout={len(stdout)} chars, stderr={len(stderr)} chars"
        )

        result = {
            "success": success,
            "stdout": stdout or "",
            "stderr": stderr or "",
            "exit_code": exit_code,
            "timed_out": timed_out,
            "language": lang,
            "duration_seconds": duration_seconds,
        }

        log_event(
            task_id=task_id,
            event_type="sandbox",
            actor="sandbox",
            summary=f"Sandbox run ({display_name}) {status_word} (exit_code={exit_code}, {duration_seconds}s)",
            metadata={
                "language": lang,
                "image": image_name,
                "exit_code": exit_code,
                "duration_seconds": duration_seconds,
                "timed_out": timed_out,
                "stdout_preview": (stdout or "")[:300],
                "stderr_preview": (stderr or "")[:300],
            },
            external_calls=0,
        )

        return result

    finally:
        tmp_file.unlink(missing_ok=True)
        _log_terminal("Temporary mount cleaned up.")

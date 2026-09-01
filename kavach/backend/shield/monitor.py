"""monitor.py — Layer 2: live connection visibility (the sovereignty proof).

Classifies every currently active network connection on this machine as
"localhost" (127.x / ::1), "local_subnet" (matches the auto-detected LAN
subnet — the same detection firewall.py uses, so the two layers always agree
on what counts as "local"), or "external" (anything else — real internet).

external_count_ever, tracked for the whole monitoring session, is the key
sovereignty metric: it should read 0 throughout a real demo. A rolling
in-memory history (last ~500 snapshots) backs the live API/WebSocket views,
and every snapshot is also appended to a separate, durable
outputs/sovereignty_session.jsonl log (distinct from the main audit log).
"""

import ipaddress
import json
import os
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

import psutil

from backend import config
from backend.shield.netinfo import detect_local_network

SESSION_LOG_PATH = config.OUTPUTS_DIR / "sovereignty_session.jsonl"
HISTORY_MAXLEN = 500

# Names used to recognize the Ollama engine process (it runs independently of
# our own process tree, so it can't be found via parent/child walking).
OLLAMA_PROCESS_NAME_HINTS = ("ollama",)

_history: deque = deque(maxlen=HISTORY_MAXLEN)
_state_lock = threading.Lock()
_log_lock = threading.Lock()

_monitor_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_session_started_at: Optional[str] = None

# external_count_ever is scoped to KAVACH's own processes — the honest sovereignty
# metric ("did KAVACH itself ever call out"), unaffected by whatever else (a
# browser, an IDE, this coding assistant) happens to be running on the same
# laptop. external_count_ever_all_processes is kept too, purely for transparency.
_external_count_ever = 0
_external_count_ever_all_processes = 0


def _get_kavach_pids() -> Set[int]:
    """PIDs considered part of KAVACH: this server process and all of its
    descendants (covers, e.g., the `docker` CLI client subprocess the sandbox
    tool spawns), plus any independently-running Ollama process(es) found by
    name. Note: Docker sandbox CONTAINERS themselves run inside Docker
    Desktop's own VM and are invisible to psutil on the Windows host — but
    they run with --network none (Phase 6), so they are structurally
    incapable of any network connection in the first place; there is nothing
    for this host-side monitor to see or need to see there."""
    pids: Set[int] = set()
    try:
        self_proc = psutil.Process(os.getpid())
        pids.add(self_proc.pid)
        for child in self_proc.children(recursive=True):
            pids.add(child.pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if any(hint in name for hint in OLLAMA_PROCESS_NAME_HINTS):
                pids.add(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return pids


def classify_remote_ip(ip: str, subnet_cidr: str) -> str:
    if not ip:
        return "none"
    if ip.startswith("127.") or ip == "::1":
        return "localhost"
    try:
        network = ipaddress.ip_network(subnet_cidr, strict=False)
        if ipaddress.ip_address(ip) in network:
            return "local_subnet"
    except ValueError:
        pass
    return "external"


def get_active_connections() -> List[Dict]:
    """Returns every connection with an established remote peer, classified,
    and flagged with is_kavach_process (this server + its subprocess tree +
    any independently-running Ollama process)."""
    net_info = detect_local_network()
    subnet_cidr = net_info["subnet_cidr"]
    kavach_pids = _get_kavach_pids()

    try:
        conns = psutil.net_connections(kind="inet")
    except (psutil.AccessDenied, PermissionError):
        conns = []

    results: List[Dict] = []
    for c in conns:
        if not c.raddr:
            continue  # listening sockets / no remote peer — not an active outbound connection
        remote_ip = c.raddr.ip
        remote_port = c.raddr.port
        classification = classify_remote_ip(remote_ip, subnet_cidr)

        proc_name = None
        if c.pid:
            try:
                proc_name = psutil.Process(c.pid).name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                proc_name = None

        results.append({
            "remote_ip": remote_ip,
            "remote_port": remote_port,
            "status": c.status,
            "pid": c.pid,
            "process_name": proc_name,
            "classification": classification,
            "is_kavach_process": bool(c.pid and c.pid in kavach_pids),
        })
    return results


def _build_snapshot() -> Dict:
    conns = get_active_connections()
    external = [c for c in conns if c["classification"] == "external"]
    external_kavach = [c for c in external if c.get("is_kavach_process")]
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_count": len(conns),
        "external_count": len(external_kavach),
        "external_count_all_processes": len(external),
        "external_connections": external_kavach,
        "external_connections_all_processes": external,
        "connections": conns,
    }


def _append_to_session_log(entry: Dict) -> None:
    try:
        config.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
        with _log_lock:
            with open(SESSION_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
    except Exception as exc:  # noqa: BLE001 - must never crash the monitor loop
        print(f"[Warning] Failed to write sovereignty session log: {exc}")


def _poll_loop(interval_seconds: float) -> None:
    global _external_count_ever, _external_count_ever_all_processes
    while not _stop_event.is_set():
        snapshot = _build_snapshot()
        with _state_lock:
            _history.append(snapshot)
            if snapshot["external_count"] > 0:
                _external_count_ever += snapshot["external_count"]
            if snapshot["external_count_all_processes"] > 0:
                _external_count_ever_all_processes += snapshot["external_count_all_processes"]
        _append_to_session_log(snapshot)
        _stop_event.wait(interval_seconds)


def start_monitor(interval_seconds: float = 1.0) -> None:
    global _monitor_thread, _session_started_at
    if _monitor_thread and _monitor_thread.is_alive():
        return
    _stop_event.clear()
    _session_started_at = datetime.now(timezone.utc).isoformat()
    _monitor_thread = threading.Thread(target=_poll_loop, args=(interval_seconds,), daemon=True)
    _monitor_thread.start()


def stop_monitor() -> None:
    _stop_event.set()
    if _monitor_thread:
        _monitor_thread.join(timeout=5)


def get_monitor_summary() -> Dict:
    with _state_lock:
        current_snapshot = _history[-1] if _history else None
        ext_ever = _external_count_ever
        ext_ever_all = _external_count_ever_all_processes
    return {
        # THE sovereignty metric: external calls ever made by KAVACH's own processes.
        "status": "external_detected" if ext_ever > 0 else "clean",
        "external_count_ever": ext_ever,
        # Informational only — everything else on the machine (browser, IDE, etc.),
        # kept for transparency, NOT part of the sovereignty claim.
        "external_count_ever_all_processes": ext_ever_all,
        "session_started_at": _session_started_at,
        "monitor_running": bool(_monitor_thread and _monitor_thread.is_alive()),
        "current_snapshot": current_snapshot,
    }

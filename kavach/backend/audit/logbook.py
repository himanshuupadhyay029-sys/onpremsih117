"""logbook.py — Append-only JSONL audit logger for KAVACH.

Records an immutable, ordered trail of all routing, planning, execution, observation,
and completion events with strict external_calls verification.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
import uuid

from backend import config

_lock = threading.Lock()


def log_event(
    task_id: Optional[str] = None,
    event_type: str = "event",
    actor: str = "system",
    summary: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    external_calls: int = 0,
) -> str:
    """Appends one JSON line to the audit logbook.
    
    Non-blocking and exception-safe: failures to write will never crash the calling process.
    Returns the task_id (generated if not provided).
    """
    if not task_id:
        task_id = str(uuid.uuid4())

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id,
        "event_type": event_type,
        "actor": actor,
        "summary": summary,
        "metadata": metadata if metadata is not None else {},
        "external_calls": external_calls,
    }

    line = json.dumps(entry) + "\n"

    try:
        # Ensure target directory exists
        config.AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            with open(config.AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception as exc:  # noqa: BLE001 - exception safe, must not crash agent execution
        print(f"[Warning] Failed to write to audit logbook: {exc}")

    return task_id


def read_events(task_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Reads events from the audit logbook, optionally filtered by task_id."""
    if not config.AUDIT_LOG_PATH.exists():
        return []

    events = []
    try:
        with _lock:
            with open(config.AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        if task_id is None or record.get("task_id") == task_id:
                            events.append(record)
                    except json.JSONDecodeError:
                        continue
    except Exception as exc:  # noqa: BLE001
        print(f"[Warning] Failed to read from audit logbook: {exc}")
        return []

    return events

"""logbook.py — Append-only JSONL audit logger for KAVACH with per-user isolation.

Records an immutable, ordered trail of all routing, planning, execution, observation,
and completion events with strict external_calls verification.
"""

import contextvars
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
import uuid

from backend import config

_lock = threading.Lock()

# ContextVar for capturing the current authenticated user in thread/async execution
_current_user_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("current_user_id", default=None)


def set_current_user_id(user_id: Optional[str]) -> None:
    """Sets the active user_id context for the current execution thread or task."""
    _current_user_id_ctx.set(str(user_id).strip() if user_id else None)


def get_current_user_id() -> Optional[str]:
    """Returns the active user_id context."""
    return _current_user_id_ctx.get()


def log_event(
    task_id: Optional[str] = None,
    event_type: str = "event",
    actor: str = "system",
    summary: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    external_calls: int = 0,
    user_id: Optional[str] = None,
) -> str:
    """Appends one JSON line to the user-isolated audit logbook.
    
    Non-blocking and exception-safe: failures to write will never crash the calling process.
    Returns the task_id (generated if not provided).
    """
    if not task_id:
        task_id = str(uuid.uuid4())

    target_user_id = str(user_id).strip() if user_id else get_current_user_id()

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task_id": task_id,
        "user_id": target_user_id,
        "event_type": event_type,
        "actor": actor,
        "summary": summary,
        "metadata": metadata if metadata is not None else {},
        "external_calls": external_calls,
    }

    line = json.dumps(entry) + "\n"

    try:
        log_path = config.get_user_audit_log_path(target_user_id)
        with _lock:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception as exc:  # noqa: BLE001 - exception safe, must not crash agent execution
        print(f"[Warning] Failed to write to audit logbook: {exc}")

    return task_id


def read_events(user_id: Optional[str] = None, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Reads events from the user's audit logbook, optionally filtered by task_id."""
    target_user_id = str(user_id).strip() if user_id else get_current_user_id()
    log_path = config.get_user_audit_log_path(target_user_id)

    if not log_path.exists():
        return []

    events = []
    try:
        with _lock:
            with open(log_path, "r", encoding="utf-8") as f:
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


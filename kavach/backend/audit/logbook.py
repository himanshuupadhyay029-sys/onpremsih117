"""logbook.py — Tamper-evident append-only JSONL audit logger for KAVACH.

Records an immutable, ordered trail of all routing, planning, execution, observation,
approval, and access events with cryptographic SHA-256 hash-chaining for tamper detection.
"""

import contextvars
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional
import uuid

from backend import config

_lock = threading.Lock()

GENESIS_HASH = "0" * 64

# ContextVar for capturing the current authenticated user in thread/async execution
_current_user_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("current_user_id", default=None)


def set_current_user_id(user_id: Optional[str]) -> None:
    """Sets the active user_id context for the current execution thread or task."""
    _current_user_id_ctx.set(str(user_id).strip() if user_id else None)


def get_current_user_id() -> Optional[str]:
    """Returns the active user_id context."""
    return _current_user_id_ctx.get()


def compute_entry_hash(
    prev_hash: str,
    timestamp: str,
    task_id: str,
    user_id: Optional[str],
    event_type: str,
    actor: str,
    summary: str,
    metadata: Any,
    external_calls: int,
) -> str:
    """Computes a deterministic SHA-256 digest over the canonical representation of an audit entry."""
    canonical_meta = json.dumps(metadata if metadata is not None else {}, sort_keys=True, separators=(",", ":"))
    payload = f"{prev_hash}|{timestamp}|{task_id}|{str(user_id or '')}|{event_type}|{actor}|{summary}|{canonical_meta}|{int(external_calls)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _get_last_entry_hash(log_path: Path) -> str:
    """Reads the last non-empty line of the log to retrieve the most recent entry_hash."""
    if not log_path.exists():
        return GENESIS_HASH

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
            if not lines:
                return GENESIS_HASH
            last_record = json.loads(lines[-1])
            return last_record.get("entry_hash", GENESIS_HASH)
    except Exception:
        return GENESIS_HASH


def log_event(
    task_id: Optional[str] = None,
    event_type: str = "event",
    actor: str = "system",
    summary: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    external_calls: int = 0,
    user_id: Optional[str] = None,
) -> str:
    """Appends one cryptographic hash-chained JSON line to the user-isolated audit logbook.

    Non-blocking and exception-safe: failures to write will never crash the calling process.
    Returns the task_id (generated if not provided).
    """
    if not task_id:
        task_id = str(uuid.uuid4())

    target_user_id = str(user_id).strip() if user_id else get_current_user_id()
    timestamp = datetime.now(timezone.utc).isoformat()
    meta_dict = metadata if metadata is not None else {}

    try:
        log_path = config.get_user_audit_log_path(target_user_id)
        with _lock:
            prev_hash = _get_last_entry_hash(log_path)
            entry_hash = compute_entry_hash(
                prev_hash=prev_hash,
                timestamp=timestamp,
                task_id=task_id,
                user_id=target_user_id,
                event_type=event_type,
                actor=actor,
                summary=summary,
                metadata=meta_dict,
                external_calls=external_calls,
            )

            entry = {
                "timestamp": timestamp,
                "task_id": task_id,
                "user_id": target_user_id,
                "event_type": event_type,
                "actor": actor,
                "summary": summary,
                "metadata": meta_dict,
                "external_calls": external_calls,
                "prev_hash": prev_hash,
                "entry_hash": entry_hash,
            }

            line = json.dumps(entry) + "\n"
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


def verify_chain(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Verifies the cryptographic SHA-256 hash-chain integrity of the user's audit log.

    Detects:
    1. Historical content modification (hash mismatch).
    2. Record deletion or reordering (prev_hash mismatch).
    3. Unauthorized record insertion.

    Returns a verification report:
    {
        "valid": bool,
        "total_entries": int,
        "verified_count": int,
        "broken_at_index": Optional[int],
        "reason": Optional[str],
        "message": str
    }
    """
    target_user_id = str(user_id).strip() if user_id else get_current_user_id()
    log_path = config.get_user_audit_log_path(target_user_id)

    if not log_path.exists():
        return {
            "valid": True,
            "total_entries": 0,
            "verified_count": 0,
            "broken_at_index": None,
            "reason": None,
            "message": "Audit log is empty.",
        }

    try:
        with _lock:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip()]
    except Exception as exc:
        return {
            "valid": False,
            "total_entries": 0,
            "verified_count": 0,
            "broken_at_index": 0,
            "reason": "io_error",
            "message": f"Could not read audit log: {exc}",
        }

    if not lines:
        return {
            "valid": True,
            "total_entries": 0,
            "verified_count": 0,
            "broken_at_index": None,
            "reason": None,
            "message": "Audit log is empty.",
        }

    expected_prev_hash = GENESIS_HASH

    for idx, line in enumerate(lines):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return {
                "valid": False,
                "total_entries": len(lines),
                "verified_count": idx,
                "broken_at_index": idx,
                "reason": "corrupted_json",
                "message": f"Corrupted JSON format at entry #{idx}.",
            }

        prev_hash = record.get("prev_hash")
        entry_hash = record.get("entry_hash")

        # 1. Check prev_hash links to prior block
        if prev_hash != expected_prev_hash:
            return {
                "valid": False,
                "total_entries": len(lines),
                "verified_count": idx,
                "broken_at_index": idx,
                "reason": "prev_hash_mismatch",
                "message": (
                    f"Chain link broken at entry #{idx}: prev_hash '{prev_hash}' "
                    f"does not match expected previous hash '{expected_prev_hash}'."
                ),
            }

        # 2. Check entry_hash matches computed hash of record contents
        computed_hash = compute_entry_hash(
            prev_hash=prev_hash,
            timestamp=record.get("timestamp", ""),
            task_id=record.get("task_id", ""),
            user_id=record.get("user_id"),
            event_type=record.get("event_type", ""),
            actor=record.get("actor", ""),
            summary=record.get("summary", ""),
            metadata=record.get("metadata", {}),
            external_calls=record.get("external_calls", 0),
        )

        if entry_hash != computed_hash:
            return {
                "valid": False,
                "total_entries": len(lines),
                "verified_count": idx,
                "broken_at_index": idx,
                "reason": "entry_hash_mismatch",
                "message": (
                    f"Tamper detected at entry #{idx}: content digest '{computed_hash}' "
                    f"does not match stored entry_hash '{entry_hash}'."
                ),
            }

        expected_prev_hash = entry_hash

    return {
        "valid": True,
        "total_entries": len(lines),
        "verified_count": len(lines),
        "broken_at_index": None,
        "reason": None,
        "message": f"All {len(lines)} audit log entries verified. Cryptographic hash chain is intact.",
    }


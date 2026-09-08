"""event_bus.py — thread-safe asynchronous event streaming bus for KAVACH agent.

Allows LangGraph nodes (executing synchronously in worker threads) to push
live progress, thoughts, decisions, and outputs to async SSE consumers without blocking.
"""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("kavach.event_bus")

# Holds per-task async queues and their associated event loops
_TASK_QUEUES: Dict[str, asyncio.Queue] = {}
_TASK_LOOPS: Dict[str, asyncio.AbstractEventLoop] = {}


def register_task(task_id: str, loop: Optional[asyncio.AbstractEventLoop] = None) -> asyncio.Queue:
    """Registers an event queue for a given task_id."""
    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.get_event_loop()

    queue: asyncio.Queue = asyncio.Queue()
    _TASK_QUEUES[task_id] = queue
    _TASK_LOOPS[task_id] = loop
    return queue


def unregister_task(task_id: str) -> None:
    """Cleans up the queue for a given task_id."""
    _TASK_QUEUES.pop(task_id, None)
    _TASK_LOOPS.pop(task_id, None)


def emit_sync(task_id: Optional[str], event_type: str, data: Dict[str, Any]) -> None:
    """Thread-safe synchronous emitter to push events from LangGraph worker threads into the async queue."""
    if not task_id or task_id not in _TASK_QUEUES:
        return

    queue = _TASK_QUEUES[task_id]
    loop = _TASK_LOOPS.get(task_id)
    if not loop or loop.is_closed():
        return

    payload = {
        "event": event_type,
        "data": data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        loop.call_soon_threadsafe(queue.put_nowait, payload)
    except Exception as exc:
        logger.debug(f"[EVENT_BUS] Failed to emit event '{event_type}' for {task_id}: {exc}")

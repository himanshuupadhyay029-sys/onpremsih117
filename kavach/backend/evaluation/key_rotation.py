"""key_rotation.py — Centralized, thread-safe API-key rotation for every evaluation model call.

Evaluators never see or choose a key: they hand a callable to `APIKeyManager.execute`,
which leases a key (round-robin, least-in-flight first), classifies failures, puts
rate-limited keys into cooldown, blacklists rejected keys and retries on another key.

With no configured keys the manager holds a single keyless slot, which is how the
default local Ollama deployment is addressed.
"""

import enum
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, TypeVar

import httpx

from backend import config

T = TypeVar("T")


class KeyRotationError(RuntimeError):
    pass


class NoKeysAvailableError(KeyRotationError):
    """Every configured key has been blacklisted."""


class KeysCoolingDownError(KeyRotationError):
    """All usable keys stayed in cooldown longer than the allowed wait."""


class ErrorKind(enum.Enum):
    RATE_LIMIT = "rate_limit"
    INVALID_KEY = "invalid_key"
    TRANSIENT = "transient"
    FATAL = "fatal"


def _status_code_of(exc: BaseException) -> Optional[int]:
    code = getattr(exc, "status_code", None)
    if code is None and isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
    return int(code) if code is not None else None


def classify_error(exc: BaseException) -> ErrorKind:
    code = _status_code_of(exc)
    if code == 429:
        return ErrorKind.RATE_LIMIT
    if code in (401, 403):
        return ErrorKind.INVALID_KEY
    if code is None:
        if isinstance(exc, (ValueError, TypeError, KeyError)):
            return ErrorKind.FATAL
        # Connection resets, timeouts and empty generations carry no status code.
        return ErrorKind.TRANSIENT
    if code == 408 or code >= 500:
        return ErrorKind.TRANSIENT
    return ErrorKind.FATAL


@dataclass
class _KeyState:
    index: int
    key: Optional[str]
    requests: int = 0
    successes: int = 0
    failures: int = 0
    rate_limited: int = 0
    in_flight: int = 0
    cooldown_until: float = 0.0
    blacklisted: bool = False

    @property
    def label(self) -> str:
        return "local" if self.key is None else f"key-{self.index + 1}"


class APIKeyManager:
    def __init__(
        self,
        keys: Sequence[str] = (),
        cooldown_seconds: float = 30.0,
        max_retries: int = 3,
        max_wait_seconds: float = 120.0,
        transient_backoff_seconds: float = 0.5,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        cleaned = [k for k in (str(k).strip() for k in keys) if k]
        self._states: List[_KeyState] = (
            [_KeyState(index=i, key=k) for i, k in enumerate(cleaned)] if cleaned else [_KeyState(index=0, key=None)]
        )
        self._cooldown_seconds = cooldown_seconds
        self._max_retries = max(0, int(max_retries))
        self._max_wait_seconds = max_wait_seconds
        self._transient_backoff = transient_backoff_seconds
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()
        self._cursor = 0

    @property
    def capacity(self) -> int:
        """Number of keys that are not blacklisted (upper bound for useful parallelism)."""
        with self._lock:
            return max(1, sum(1 for s in self._states if not s.blacklisted))

    def _acquire(self) -> _KeyState:
        waited = 0.0
        while True:
            with self._lock:
                usable = [s for s in self._states if not s.blacklisted]
                if not usable:
                    raise NoKeysAvailableError("All evaluation API keys have been rejected and blacklisted.")
                now = self._clock()
                ready = {s.index for s in usable if s.cooldown_until <= now}
                if ready:
                    n = len(self._states)
                    order = [self._states[(self._cursor + i) % n] for i in range(n)]
                    candidates = [s for s in order if s.index in ready]
                    chosen = min(candidates, key=lambda s: s.in_flight)
                    self._cursor = (chosen.index + 1) % n
                    chosen.in_flight += 1
                    chosen.requests += 1
                    return chosen
                wait_for = min(s.cooldown_until for s in usable) - now
            if waited + wait_for > self._max_wait_seconds:
                raise KeysCoolingDownError(
                    f"All evaluation API keys are cooling down (next available in {wait_for:.1f}s)."
                )
            self._sleep(max(wait_for, 0.0))
            waited += max(wait_for, 0.0)

    def _release(self, state: _KeyState, outcome: Optional[ErrorKind]) -> None:
        with self._lock:
            state.in_flight = max(0, state.in_flight - 1)
            if outcome is None:
                state.successes += 1
                return
            state.failures += 1
            if outcome is ErrorKind.RATE_LIMIT:
                state.rate_limited += 1
                state.cooldown_until = self._clock() + self._cooldown_seconds
            elif outcome is ErrorKind.INVALID_KEY:
                state.blacklisted = True

    def execute(self, call: Callable[[Optional[str]], T]) -> T:
        """Runs `call(api_key)` with rotation, cooldown, blacklisting and retries."""
        last_exc: Optional[BaseException] = None
        for attempt in range(self._max_retries + 1):
            state = self._acquire()
            try:
                result = call(state.key)
            except Exception as exc:
                kind = classify_error(exc)
                self._release(state, kind)
                if kind is ErrorKind.FATAL:
                    raise
                last_exc = exc
                if kind is ErrorKind.TRANSIENT and attempt < self._max_retries:
                    self._sleep(self._transient_backoff * (2 ** attempt))
                continue
            self._release(state, None)
            return result
        assert last_exc is not None
        raise last_exc

    def stats(self) -> List[Dict[str, Any]]:
        """Per-key counters with masked labels; raw keys are never exposed."""
        with self._lock:
            now = self._clock()
            return [
                {
                    "key": s.label,
                    "requests": s.requests,
                    "successes": s.successes,
                    "failures": s.failures,
                    "rate_limited": s.rate_limited,
                    "in_flight": s.in_flight,
                    "cooling_down": s.cooldown_until > now,
                    "blacklisted": s.blacklisted,
                }
                for s in self._states
            ]


_manager: Optional[APIKeyManager] = None
_manager_lock = threading.Lock()


def get_key_manager() -> APIKeyManager:
    """Process-wide manager shared by every evaluator and embedding call."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = APIKeyManager(
                keys=config.EVALUATION_API_KEYS,
                cooldown_seconds=config.EVALUATION_KEY_COOLDOWN_SECONDS,
                max_retries=config.EVALUATION_MAX_RETRIES,
            )
        return _manager


def reset_key_manager() -> None:
    global _manager
    with _manager_lock:
        _manager = None

import threading

import pytest

from backend.engine.ollama import OllamaError
from backend.evaluation.key_rotation import (
    APIKeyManager,
    ErrorKind,
    KeysCoolingDownError,
    NoKeysAvailableError,
    classify_error,
)
from backend.evaluation.llm import EvaluationLLM


class FakeClock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def make_manager(keys, clock=None, **kwargs):
    clock = clock or FakeClock()
    kwargs.setdefault("transient_backoff_seconds", 0.0)
    return APIKeyManager(keys=keys, clock=clock.time, sleep=clock.sleep, **kwargs), clock


def test_classify_error():
    assert classify_error(OllamaError("x", status_code=429)) is ErrorKind.RATE_LIMIT
    assert classify_error(OllamaError("x", status_code=401)) is ErrorKind.INVALID_KEY
    assert classify_error(OllamaError("x", status_code=403)) is ErrorKind.INVALID_KEY
    assert classify_error(OllamaError("x", status_code=503)) is ErrorKind.TRANSIENT
    assert classify_error(OllamaError("connection refused")) is ErrorKind.TRANSIENT
    assert classify_error(OllamaError("bad request", status_code=400)) is ErrorKind.FATAL


def test_round_robin_allocation():
    manager, _ = make_manager(["k1", "k2", "k3"])
    used = [manager.execute(lambda key: key) for _ in range(4)]
    assert used == ["k1", "k2", "k3", "k1"]


def test_keyless_mode_passes_no_key():
    manager, _ = make_manager([])
    assert manager.execute(lambda key: key) is None
    assert manager.capacity == 1
    assert manager.stats()[0]["key"] == "local"


def test_concurrent_calls_use_different_keys():
    manager, _ = make_manager(["k1", "k2", "k3"])
    barrier = threading.Barrier(3, timeout=5)
    used, errors = [], []
    lock = threading.Lock()

    def call(key):
        barrier.wait()  # all three leases are held at the same time
        with lock:
            used.append(key)
        return key

    def worker():
        try:
            manager.execute(call)
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert sorted(used) == ["k1", "k2", "k3"]
    assert all(s["in_flight"] == 0 for s in manager.stats())


def test_rate_limit_retries_on_another_key_and_cools_down():
    manager, _ = make_manager(["k1", "k2"], cooldown_seconds=30)
    attempts = []

    def call(key):
        attempts.append(key)
        if key == "k1":
            raise OllamaError("slow down", status_code=429)
        return "ok"

    assert manager.execute(call) == "ok"
    assert attempts == ["k1", "k2"]
    stats = {s["key"]: s for s in manager.stats()}
    assert stats["key-1"]["rate_limited"] == 1 and stats["key-1"]["cooling_down"]
    # While k1 cools down every call goes to k2.
    assert [manager.execute(lambda key: key) for _ in range(3)] == ["k2", "k2", "k2"]


def test_invalid_key_is_blacklisted():
    manager, _ = make_manager(["bad", "good"])

    def call(key):
        if key == "bad":
            raise OllamaError("unauthorized", status_code=401)
        return key

    assert manager.execute(call) == "good"
    assert manager.capacity == 1
    assert [manager.execute(lambda key: key) for _ in range(3)] == ["good"] * 3
    assert {s["key"]: s["blacklisted"] for s in manager.stats()} == {"key-1": True, "key-2": False}


def test_cooldown_waits_then_recovers():
    manager, clock = make_manager(["only"], cooldown_seconds=20)
    calls = {"n": 0}

    def call(key):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OllamaError("rate limited", status_code=429)
        return "recovered"

    assert manager.execute(call) == "recovered"
    assert calls["n"] == 2
    assert clock.sleeps == [pytest.approx(20.0)]


def test_all_keys_blacklisted_raises():
    manager, _ = make_manager(["a", "b"])
    with pytest.raises(NoKeysAvailableError):
        manager.execute(lambda key: (_ for _ in ()).throw(OllamaError("denied", status_code=403)))


def test_all_keys_cooling_down_beyond_max_wait_raises():
    manager, clock = make_manager(["a", "b"], cooldown_seconds=300, max_wait_seconds=10, max_retries=5)

    def call(key):
        raise OllamaError("rate limited", status_code=429)

    with pytest.raises(KeysCoolingDownError):
        manager.execute(call)
    assert sum(s["rate_limited"] for s in manager.stats()) == 2
    assert clock.sleeps == []


def test_transient_errors_retry_then_surface_last_error():
    manager, _ = make_manager(["a"], max_retries=2)
    attempts = []

    def call(key):
        attempts.append(key)
        raise OllamaError("connection reset")

    with pytest.raises(OllamaError, match="connection reset"):
        manager.execute(call)
    assert len(attempts) == 3


def test_fatal_errors_are_not_retried():
    manager, _ = make_manager(["a", "b"])
    attempts = []

    def call(key):
        attempts.append(key)
        raise OllamaError("bad request", status_code=400)

    with pytest.raises(OllamaError):
        manager.execute(call)
    assert attempts == ["a"]


def test_stats_never_expose_raw_keys():
    manager, _ = make_manager(["super-secret-1", "super-secret-2"])
    manager.execute(lambda key: key)
    assert "super-secret" not in repr(manager.stats())


def test_evaluation_llm_routes_generation_and_embeddings_through_rotation(monkeypatch):
    from backend.engine import ollama

    seen = []

    def fake_generate(model, prompt, system=None, *, options=None, response_format=None, headers=None):
        seen.append(("generate", headers["Authorization"], options["temperature"], response_format))
        return '{"ok": true}'

    def fake_embed_batch(model, texts, *, headers=None):
        seen.append(("embed", headers["Authorization"], None, None))
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(ollama, "generate", fake_generate)
    monkeypatch.setattr(ollama, "embed_batch", fake_embed_batch)

    manager, _ = make_manager(["k1", "k2"])
    llm = EvaluationLLM(key_manager=manager, generation_model="gen", embedding_model="emb")
    assert llm.generate_json("p", "s") == {"ok": True}
    assert llm.embed(["a", "b"]).shape == (2, 2)
    assert llm.generate("p", "s") == '{"ok": true}'
    assert seen == [
        ("generate", "Bearer k1", 0, "json"),
        ("embed", "Bearer k2", None, None),
        ("generate", "Bearer k1", 0, None),
    ]

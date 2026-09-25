import copy
import json

import numpy as np
import pytest

from backend import config
from backend.evaluation import evaluation_service, llm as llm_module
from backend.evaluation.schemas import METRIC_NAMES

from conftest import FakeLLM
from test_evaluation_service import full_handlers, make_agent_result, SOURCE_TEXT

main = pytest.importorskip("backend.main")
from fastapi.testclient import TestClient  # noqa: E402

from backend.db.session import get_db  # noqa: E402


class _NoDatabase:
    def query(self, *args, **kwargs):
        raise RuntimeError("database not available in tests")

    def add(self, *args, **kwargs):
        pass

    def commit(self):
        pass

    def close(self):
        pass


@pytest.fixture
def client(monkeypatch, knowledge_dir):
    agent_result = make_agent_result()
    monkeypatch.setattr(main, "run_agent", lambda *args, **kwargs: copy.deepcopy(agent_result))
    monkeypatch.setattr(main, "SessionLocal", _NoDatabase)
    monkeypatch.setattr(evaluation_service, "log_event", lambda **kwargs: None)
    main.app.dependency_overrides[get_db] = lambda: _NoDatabase()
    try:
        yield TestClient(main.app), agent_result
    finally:
        main.app.dependency_overrides.pop(get_db, None)


def read_sse(response):
    events, name = [], None
    for line in response.iter_lines():
        if line.startswith("event: "):
            name = line[len("event: "):]
        elif line.startswith("data: "):
            events.append((name, json.loads(line[len("data: "):])))
    return events


def test_stream_disabled_ends_after_answer_with_disabled_state(client, monkeypatch, no_model_calls):
    http, agent_result = client
    monkeypatch.setattr(config, "ENABLE_EVALUATION", False)
    with http.stream("GET", "/run/stream", params={"task": "q", "task_id": "t-disabled"}) as response:
        events = read_sse(response)

    assert [name for name, _ in events] == ["done_stream"]
    done = events[0][1]
    assert done["evaluation"] == {"enabled": False, "status": "disabled"}
    assert done["result"] == agent_result["result"]


def test_stream_enabled_delivers_answer_then_incremental_metrics(client, monkeypatch):
    http, agent_result = client
    monkeypatch.setattr(config, "ENABLE_EVALUATION", True)
    from backend.vault.source_store import save_source_text

    save_source_text("backup.md", SOURCE_TEXT, user_id=None)
    fake = FakeLLM(full_handlers(), embed_fn=lambda texts: np.array([[1.0, 0.0] for _ in texts]))
    monkeypatch.setattr(llm_module, "EvaluationLLM", lambda: fake)

    with http.stream("GET", "/run/stream", params={"task": "q", "task_id": "t-enabled"}) as response:
        events = read_sse(response)
    names = [name for name, _ in events]

    assert names[0] == "done_stream"
    assert events[0][1]["result"] == agent_result["result"]
    assert events[0][1]["evaluation"]["status"] == "running"
    assert names[1:3] == ["evaluation_stage", "evaluation_stage"]
    assert sorted(p["metric"] for n, p in events if n == "evaluation_metric") == sorted(METRIC_NAMES)
    assert names[-1] == "evaluation_done"
    final = events[-1][1]
    assert final["status"] == "completed"
    assert all(isinstance(final["metrics"][m], float) for m in METRIC_NAMES)


def test_run_endpoint_returns_unchanged_answer_plus_disabled_evaluation(client, monkeypatch, no_model_calls):
    http, agent_result = client
    monkeypatch.setattr(config, "ENABLE_EVALUATION", False)
    body = http.post("/run", json={"task": "q"}).json()
    assert body["evaluation"] == {"enabled": False, "status": "disabled"}
    for key in ("result", "sources", "step_outputs", "status"):
        assert body[key] == agent_result[key]

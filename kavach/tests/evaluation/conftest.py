import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend import config  # noqa: E402
from backend.evaluation import (  # noqa: E402
    answer_relevancy,
    context_precision_reference,
    context_recall,
    faithfulness,
    ground_truth,
)


def classify_call(system: str, prompt: str) -> str:
    if system == ground_truth.GROUND_TRUTH_SYSTEM_PROMPT:
        return "ground_truth"
    if system == faithfulness.SYSTEM_PROMPT:
        return "verify_claims" if "CLAIMS:" in prompt else "extract_claims"
    if system == answer_relevancy.SYSTEM_PROMPT:
        return "reverse_questions"
    if system == context_recall.SYSTEM_PROMPT:
        return "recall"
    if system == context_precision_reference.SYSTEM_PROMPT:
        return "precision"
    raise AssertionError(f"Unexpected evaluator system prompt: {system[:60]}")


class FakeLLM:
    """Stand-in for EvaluationLLM that routes each call to a scripted handler and records it."""

    def __init__(
        self,
        handlers: Optional[Dict[str, Callable[[str], Any]]] = None,
        embed_fn: Optional[Callable[[List[str]], np.ndarray]] = None,
        parallelism: int = 2,
    ):
        self.handlers = dict(handlers or {})
        self.embed_fn = embed_fn
        self.parallelism = parallelism
        self.calls: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def _record(self, kind: str, payload: Any) -> None:
        with self._lock:
            self.calls.append({"kind": kind, "payload": payload})

    def kinds(self) -> List[str]:
        return [c["kind"] for c in self.calls]

    def prompts(self, kind: str) -> List[str]:
        return [c["payload"] for c in self.calls if c["kind"] == kind]

    def _dispatch(self, prompt: str, system: str) -> Any:
        kind = classify_call(system, prompt)
        self._record(kind, prompt)
        if kind not in self.handlers:
            raise AssertionError(f"No handler scripted for evaluator call '{kind}'")
        return self.handlers[kind](prompt)

    def generate(self, prompt: str, system: str, json_mode: bool = False) -> str:
        return self._dispatch(prompt, system)

    def generate_json(self, prompt: str, system: str) -> Dict[str, Any]:
        return self._dispatch(prompt, system)

    def embed(self, texts: List[str]) -> np.ndarray:
        self._record("embed", list(texts))
        if self.embed_fn is None:
            raise AssertionError("No embedding function scripted")
        return np.asarray(self.embed_fn(list(texts)), dtype=np.float64)


@pytest.fixture
def knowledge_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "KNOWLEDGE_DIR", tmp_path / "knowledge")
    return tmp_path / "knowledge"


@pytest.fixture
def no_model_calls(monkeypatch):
    """Fails the test if anything reaches the model engine."""
    from backend.engine import ollama

    def _forbidden(*args, **kwargs):
        raise AssertionError("A model call was made")

    for name in ("generate", "chat", "embed", "embed_batch"):
        monkeypatch.setattr(ollama, name, _forbidden)

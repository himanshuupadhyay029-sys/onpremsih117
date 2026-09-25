"""llm.py — Evaluator-side access to KAVACH's local model engine.

All evaluation generations and embeddings go through `backend.engine.ollama` and the
shared `APIKeyManager`; evaluators only ever talk to an `EvaluationLLM`.
"""

import json
import re
import threading
from typing import Any, Dict, List, Optional

import numpy as np

from backend import config
from backend.engine import ollama, registry
from backend.evaluation.key_rotation import APIKeyManager, get_key_manager


class EvaluationParseError(ValueError):
    """The evaluator model returned output that could not be parsed as the expected JSON."""


def parse_json_object(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        brace = re.search(r"(\{.*\})", text, re.DOTALL)
        if brace:
            text = brace.group(1)
    try:
        data = json.loads(text)
    except Exception as exc:
        raise EvaluationParseError(f"Evaluator returned non-JSON output: {raw[:200]!r}") from exc
    if not isinstance(data, dict):
        raise EvaluationParseError("Evaluator JSON output was not an object")
    return data


def as_verdict(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    return str(value).strip().lower() in {"true", "yes", "1", "supported", "attributed", "relevant"}


def parse_indexed_verdicts(data: Dict[str, Any], field: str, count: int) -> List[bool]:
    """Maps {"verdicts": [{"index": i, field: ...}]} onto items 1..count.

    An item the judge did not rule on counts as False (unsupported/unattributed).
    """
    verdicts = data.get("verdicts")
    if not isinstance(verdicts, list):
        raise EvaluationParseError("Evaluator output is missing a 'verdicts' list")
    by_index: Dict[int, bool] = {}
    for position, v in enumerate(verdicts, start=1):
        if not isinstance(v, dict):
            continue
        try:
            idx = int(v.get("index", position))
        except (TypeError, ValueError):
            idx = position
        by_index[idx] = as_verdict(v.get(field))
    return [by_index.get(i, False) for i in range(1, count + 1)]


def _auth_headers(api_key: Optional[str]) -> Optional[Dict[str, str]]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else None


class EvaluationLLM:
    def __init__(
        self,
        key_manager: Optional[APIKeyManager] = None,
        generation_model: Optional[str] = None,
        embedding_model: Optional[str] = None,
    ):
        self.key_manager = key_manager or get_key_manager()
        self._generation_model = generation_model
        self._embedding_model = embedding_model
        self._model_lock = threading.Lock()

    @property
    def parallelism(self) -> int:
        return self.key_manager.capacity

    @property
    def generation_model(self) -> str:
        with self._model_lock:
            if self._generation_model is None:
                self._generation_model = registry.get_model("reasoning")
            return self._generation_model

    @property
    def embedding_model(self) -> str:
        with self._model_lock:
            if self._embedding_model is None:
                self._embedding_model = registry.get_model("embedding")
            return self._embedding_model

    def generate(self, prompt: str, system: str, json_mode: bool = False) -> str:
        model = self.generation_model
        options = {"temperature": 0, "seed": 7, "num_ctx": config.EVALUATION_NUM_CTX}
        return self.key_manager.execute(
            lambda key: ollama.generate(
                model,
                prompt,
                system=system,
                options=options,
                response_format="json" if json_mode else None,
                headers=_auth_headers(key),
            )
        )

    def generate_json(self, prompt: str, system: str) -> Dict[str, Any]:
        return parse_json_object(self.generate(prompt, system, json_mode=True))

    def embed(self, texts: List[str]) -> np.ndarray:
        model = self.embedding_model
        vectors = self.key_manager.execute(
            lambda key: ollama.embed_batch(model, list(texts), headers=_auth_headers(key))
        )
        if len(vectors) != len(texts) or any(not v for v in vectors):
            raise ValueError("Embedding model returned an incomplete set of vectors")
        return np.asarray(vectors, dtype=np.float64)

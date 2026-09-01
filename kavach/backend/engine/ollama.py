"""ollama.py — Thin synchronous client communicating strictly with local Ollama daemon."""

import base64
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import httpx

from backend import config


class OllamaError(RuntimeError):
    """Raised when Ollama is unreachable or returns an error."""
    pass


def _get_client(timeout: float = 120.0) -> httpx.Client:
    return httpx.Client(base_url=config.OLLAMA_BASE_URL, timeout=timeout)


def generate(model: str, prompt: str, system: Optional[str] = None) -> str:
    """Generates completion text from a local Ollama model without streaming."""
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        payload["system"] = system

    try:
        with _get_client(timeout=120.0) as client:
            resp = client.post("/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")
    except httpx.ConnectError as exc:
        raise OllamaError(
            f"Cannot connect to local Ollama at {config.OLLAMA_BASE_URL}. "
            "Please ensure Ollama is running (`ollama serve`)."
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise OllamaError(f"Ollama returned HTTP error: {exc.response.status_code} - {exc.response.text}") from exc
    except Exception as exc:
        raise OllamaError(f"Ollama generation failed: {exc}") from exc


def embed(model: str, text: str) -> List[float]:
    """Generates vector embeddings for a given text using a local embedding model."""
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": text,
    }
    try:
        with _get_client(timeout=30.0) as client:
            resp = client.post("/api/embeddings", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("embedding", [])
    except httpx.ConnectError as exc:
        raise OllamaError(
            f"Cannot connect to local Ollama at {config.OLLAMA_BASE_URL}. "
            "Please ensure Ollama is running (`ollama serve`)."
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise OllamaError(f"Ollama returned HTTP error: {exc.response.status_code} - {exc.response.text}") from exc
    except Exception as exc:
        raise OllamaError(f"Ollama embedding failed: {exc}") from exc


def vision(model: str, prompt: str, image_path: Union[str, Path]) -> str:
    """Performs multimodal visual analysis on an image file using a local vision model."""
    img_p = Path(image_path)
    if not img_p.exists():
        raise FileNotFoundError(f"Image not found at path: {image_path}")

    with open(img_p, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False,
    }
    try:
        with _get_client(timeout=180.0) as client:
            resp = client.post("/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")
    except httpx.ConnectError as exc:
        raise OllamaError(
            f"Cannot connect to local Ollama at {config.OLLAMA_BASE_URL}. "
            "Please ensure Ollama is running (`ollama serve`)."
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise OllamaError(f"Ollama returned HTTP error: {exc.response.status_code} - {exc.response.text}") from exc
    except Exception as exc:
        raise OllamaError(f"Ollama vision call failed: {exc}") from exc


def list_models() -> List[str]:
    """Returns a list of all model tags currently installed in local Ollama."""
    try:
        with _get_client(timeout=10.0) as client:
            resp = client.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
            models = data.get("models", [])
            return [m.get("name", m.get("model", "")) for m in models]
    except httpx.ConnectError as exc:
        raise OllamaError(
            f"Cannot connect to local Ollama at {config.OLLAMA_BASE_URL}. "
            "Please ensure Ollama is running (`ollama serve`)."
        ) from exc
    except Exception as exc:
        raise OllamaError(f"Failed to list local Ollama models: {exc}") from exc

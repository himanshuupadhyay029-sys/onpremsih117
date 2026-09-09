import asyncio
import base64
import json
from pathlib import Path
import re
from typing import Any, AsyncGenerator, Dict, List, Optional, Union
import httpx

from backend import config


class OllamaError(RuntimeError):
    """Raised when Ollama is unreachable or returns an error."""
    pass


# Global tracking of active pulls: model_name -> httpx.AsyncClient
active_pulls: Dict[str, httpx.AsyncClient] = {}



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
            text = data.get("response", "").strip()
            if not text:
                raise OllamaError(
                    f"Ollama model '{model}' returned an empty response. "
                    "The model may have run out of context, be overloaded, or encountered a generation error."
                )
            return text
    except OllamaError:
        raise
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
        with _get_client(timeout=120.0) as client:
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


def embed_batch(model: str, texts: List[str]) -> List[List[float]]:
    """Generates vector embeddings for multiple texts.
    Attempts modern Ollama /api/embed batch endpoint first, falling back to sequential /api/embeddings.
    """
    if not texts:
        return []

    # Modern Ollama batch API endpoint: /api/embed with input: [list of strings]
    batch_payload: Dict[str, Any] = {
        "model": model,
        "input": texts,
    }
    try:
        with _get_client(timeout=180.0) as client:
            resp = client.post("/api/embed", json=batch_payload)
            if resp.status_code == 200:
                data = resp.json()
                embeddings = data.get("embeddings")
                if embeddings and len(embeddings) == len(texts):
                    return embeddings
    except httpx.ConnectError as exc:
        raise OllamaError(
            f"Cannot connect to local Ollama at {config.OLLAMA_BASE_URL}. "
            "Please ensure Ollama is running (`ollama serve`)."
        ) from exc
    except Exception:
        # Fallback to single-chunk embedding if /api/embed fails or endpoint not present
        pass

    return [embed(model, t) for t in texts]



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


def pull_model(model: str) -> bool:
    """Pulls a model from the Ollama registry."""
    payload: Dict[str, Any] = {"name": model, "stream": False}
    try:
        with _get_client(timeout=3600.0) as client:
            resp = client.post("/api/pull", json=payload)
            resp.raise_for_status()
            return True
    except httpx.ConnectError as exc:
        raise OllamaError(
            f"Cannot connect to local Ollama at {config.OLLAMA_BASE_URL}. "
            "Please ensure Ollama is running (`ollama serve`)."
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise OllamaError(f"Ollama returned HTTP error: {exc.response.status_code} - {exc.response.text}") from exc
    except Exception as exc:
        raise OllamaError(f"Ollama pull failed: {exc}") from exc


def delete_model(model: str) -> bool:
    """Deletes a model from the local Ollama registry."""
    payload: Dict[str, Any] = {"name": model}
    try:
        with _get_client(timeout=60.0) as client:
            resp = client.request("DELETE", "/api/delete", json=payload)
            resp.raise_for_status()
            return True
    except httpx.ConnectError as exc:
        raise OllamaError(
            f"Cannot connect to local Ollama at {config.OLLAMA_BASE_URL}. "
            "Please ensure Ollama is running (`ollama serve`)."
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise OllamaError(f"Ollama returned HTTP error: {exc.response.status_code} - {exc.response.text}") from exc
    except Exception as exc:
        raise OllamaError(f"Ollama delete failed: {exc}") from exc


def get_model_tags_and_quants(model_name: str) -> Dict[str, Any]:
    """Queries official Ollama library registry for available model tags, sizes, and quantizations."""
    model_clean = model_name.strip().lower()
    if not model_clean:
        return {"available": False, "error": "Model name cannot be empty", "tags": []}

    base_name = model_clean.split(":")[0]
    url = f"https://ollama.com/library/{base_name}/tags"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as web_client:
            r = web_client.get(url, headers=headers)
            if r.status_code == 404:
                return {
                    "available": False,
                    "base_name": base_name,
                    "error": f"Model '{base_name}' was not found in the Ollama library.",
                    "tags": [],
                }
            if r.status_code != 200:
                return {
                    "available": False,
                    "base_name": base_name,
                    "error": f"Ollama registry returned HTTP {r.status_code}",
                    "tags": [],
                }

            pattern = re.compile(
                rf'<a href="/library/{re.escape(base_name)}:([^"]+)"[^>]*>\s*([^\s<]+)\s*</a>\s*(?:<input[^>]*>)?\s*(?:<button[\s\S]*?</button>)?\s*</span>\s*<p class="[^"]*">([^<]+)</p>'
            )
            matches = pattern.findall(r.text)

            tags_list = []
            seen = set()
            for tag_slug, tag_name, size in matches:
                if tag_slug in seen:
                    continue
                seen.add(tag_slug)

                quant = "Default"
                quant_match = re.search(r'(q[0-9]_[a-z0-9_]+|fp16|f16|fp32|f32|bf16)', tag_slug, re.IGNORECASE)
                if quant_match:
                    quant = quant_match.group(1).upper()
                elif "fp16" in tag_slug.lower() or "f16" in tag_slug.lower():
                    quant = "FP16"

                param_match = re.search(r'([0-9]+(?:\.[0-9]+)?b)', tag_slug, re.IGNORECASE)
                param_size = param_match.group(1).lower() if param_match else ""

                tags_list.append({
                    "tag": tag_slug,
                    "full_name": f"{base_name}:{tag_slug}",
                    "size": size.strip(),
                    "quantization": quant,
                    "param_size": param_size,
                })

            return {
                "available": True,
                "base_name": base_name,
                "total_tags": len(tags_list),
                "tags": tags_list,
            }
    except httpx.ConnectError:
        return {
            "available": False,
            "base_name": base_name,
            "error": "Could not connect to ollama.com. Please check your internet connection.",
            "tags": [],
        }
    except Exception as e:
        return {
            "available": False,
            "base_name": base_name,
            "error": str(e),
            "tags": [],
        }


async def stream_pull_model(model: str) -> AsyncGenerator[str, None]:
    """Streams pull progress directly from Ollama as Server-Sent Events (SSE)."""
    client = httpx.AsyncClient(
        base_url=config.OLLAMA_BASE_URL,
        timeout=httpx.Timeout(3600.0, connect=15.0),
    )
    active_pulls[model] = client
    try:
        async with client.stream("POST", "/api/pull", json={"name": model, "stream": True}) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    total = data.get("total", 0)
                    completed = data.get("completed", 0)
                    percentage = 0.0
                    if total > 0:
                        percentage = round((completed / total) * 100, 1)

                    event_data = {
                        "status": data.get("status", ""),
                        "digest": data.get("digest", ""),
                        "total": total,
                        "completed": completed,
                        "percentage": percentage,
                    }
                    yield f"data: {json.dumps(event_data)}\n\n"
                except Exception:
                    continue
    except asyncio.CancelledError:
        yield f"data: {json.dumps({'status': 'cancelled', 'error': 'Pull was stopped by user'})}\n\n"
        raise
    except httpx.RequestError as exc:
        yield f"data: {json.dumps({'status': 'error', 'error': str(exc)})}\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'status': 'error', 'error': str(exc)})}\n\n"
    finally:
        active_pulls.pop(model, None)
        await client.aclose()


async def cancel_pull_model(model: str) -> bool:
    """Terminates an active pull connection to Ollama immediately."""
    client = active_pulls.get(model)
    if client:
        try:
            await client.aclose()
        finally:
            active_pulls.pop(model, None)
        return True
    return False


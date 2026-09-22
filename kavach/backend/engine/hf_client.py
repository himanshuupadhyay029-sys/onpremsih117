"""hf_client.py — Hugging Face Serverless Inference API adapter for KAVACH.

Exports identical function signatures to ollama.py so all call sites work
without modification when routed through the active_llm dispatch.

Limitations:
  - No streaming: stream parameter is ignored; full response returned after generation
  - Cold starts: 20-60s on first call; handled by 503 wait-and-retry logic
  - Rate limits: ~100-200 req/hour per token; rotates through primary/fallback keys
  - Gated models (Granite, Qwen2-VL): require per-account ToS acceptance on HF
  - Vision response time: 30-90s for image understanding tasks
"""

import base64
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import httpx

from backend import config

logger = logging.getLogger("kavach.hf_client")

HF_API_BASE = "https://api-inference.huggingface.co/models"
_DEFAULT_TIMEOUT = 120.0  # seconds — HF can be slow, don't time out early


class HFClientError(RuntimeError):
    """Raised when all token slots for a role are exhausted or a fatal HF error occurs."""
    pass


def _role_from_model(model_id: str) -> str:
    """Reverse-lookup: given a HF model ID, return which role it serves."""
    for role, mid in config.HF_MODELS.items():
        if mid == model_id:
            return role
    return "reasoning"  # safe default


def _call_with_rotation(model_id: str, payload: dict) -> Union[dict, list]:
    """POST to HF Serverless API with token rotation.

    Rotation logic:
      - Try PRIMARY key first.
      - 429 Too Many Requests -> rotate to next key.
      - 503 Model Loading -> wait estimated_time (max 60s) -> retry same key once -> then rotate.
      - 403 Forbidden -> raise immediately (ToS not accepted).
      - All keys exhausted -> raise HFClientError.
    """
    role = _role_from_model(model_id)
    keys = config.HF_KEYS.get(role, [])

    if not keys:
        raise HFClientError(
            f"No HF API keys configured for role '{role}'. "
            f"Set HF_{role.upper()}_API_KEY_PRIMARY in environment variables."
        )

    url = f"{HF_API_BASE}/{model_id}"
    last_error = "unknown"

    for i, key in enumerate(keys):
        slot = "PRIMARY" if i == 0 else f"FALLBACK_{i}"
        try:
            logger.debug(f"[HF] {role}/{slot} -> {url}")
            resp = httpx.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {key}"},
                timeout=_DEFAULT_TIMEOUT,
            )

            if resp.status_code == 200:
                return resp.json()

            elif resp.status_code == 429:
                logger.warning(f"[HF] {role}/{slot} -> 429 rate limited, rotating to next key")
                last_error = f"Rate limited on {slot}"
                continue

            elif resp.status_code == 503:
                body = resp.json() if resp.content else {}
                wait_sec = min(float(body.get("estimated_time", 20)), 60)
                logger.info(f"[HF] {role}/{slot} -> 503 model loading, waiting {wait_sec:.0f}s")
                time.sleep(wait_sec)
                # One retry on same key after the wait
                resp2 = httpx.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=_DEFAULT_TIMEOUT,
                )
                if resp2.status_code == 200:
                    return resp2.json()
                logger.warning(f"[HF] {role}/{slot} still failing after wait, rotating")
                last_error = f"503 model loading on {slot} (waited {wait_sec:.0f}s)"
                continue

            elif resp.status_code == 403:
                raise HFClientError(
                    f"HF 403 Forbidden for model '{model_id}' using {slot} key. "
                    "The HF account associated with this token has NOT accepted this model's Terms of Service. "
                    f"Fix: log into that HF account -> visit https://huggingface.co/{model_id} -> click 'Agree and access repository'."
                )

            else:
                raise HFClientError(
                    f"HF API error {resp.status_code} for role '{role}' ({slot}): {resp.text[:300]}"
                )

        except httpx.TimeoutException:
            logger.warning(f"[HF] {role}/{slot} -> timed out after {_DEFAULT_TIMEOUT}s, rotating")
            last_error = f"Timeout on {slot}"
            continue

    raise HFClientError(
        f"All HF keys exhausted for role '{role}' (tried {len(keys)} slot(s)). Last: {last_error}"
    )


def _extract_text(result: Union[dict, list], prompt: str = "") -> str:
    """Extract assistant text from HF response — handles multiple response formats."""
    if isinstance(result, list) and result:
        raw = result[0].get("generated_text", "")
        if isinstance(raw, list):
            # Messages API: [{role, content}, ...] — get last assistant message
            for msg in reversed(raw):
                if isinstance(msg, dict) and msg.get("role") == "assistant":
                    return msg.get("content", "").strip()
            return ""
        # Text-generation format returns prompt + completion — strip prompt prefix
        if prompt and isinstance(raw, str) and raw.startswith(prompt):
            return raw[len(prompt):].strip()
        return raw.strip() if isinstance(raw, str) else str(raw)

    if isinstance(result, dict):
        if "choices" in result and result["choices"]:
            # OpenAI-compatible chat completions format
            return result["choices"][0]["message"]["content"].strip()
        if "generated_text" in result:
            return result["generated_text"].strip()

    return str(result)


# ─────────────────────────────────────────────────────────────────────────────
# Public API — identical signatures to ollama.py
# ─────────────────────────────────────────────────────────────────────────────

def generate(model: str, prompt: str, system: Optional[str] = None) -> str:
    """Generate a completion. 'model' is a HF model ID from config.HF_MODELS.
    Streaming is not supported on HF Serverless free tier — full response returned at once.
    """
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "messages": messages,
        "max_new_tokens": 1024,
        "temperature": 0.7,
    }
    result = _call_with_rotation(model, payload)
    return _extract_text(result, prompt)


def chat(model: str, messages: List[Dict[str, str]]) -> str:
    """Multi-turn chat with a list of {role, content} message dicts."""
    payload = {
        "messages": messages,
        "max_new_tokens": 1024,
        "temperature": 0.7,
    }
    result = _call_with_rotation(model, payload)
    return _extract_text(result)


def embed(model: str, text: str) -> List[float]:
    """Single text embedding. HF feature-extraction returns [[float, ...]] — one level unwrapped."""
    result = _call_with_rotation(model, {"inputs": text})
    if isinstance(result, list) and result:
        inner = result[0]
        # feature-extraction endpoint returns [[vec]] — unwrap outer list
        if isinstance(inner, list):
            return inner
        return result
    raise HFClientError(f"Unexpected embed response format: {type(result)}")


def embed_batch(model: str, texts: List[str]) -> List[List[float]]:
    """Batch embeddings. HF returns [[vec1], [vec2]] or [[f,f,...],[f,f,...]]."""
    if not texts:
        return []
    result = _call_with_rotation(model, {"inputs": texts})
    if isinstance(result, list) and result:
        # If doubly-nested [[vec]] per text, unwrap
        if isinstance(result[0], list) and result[0] and isinstance(result[0][0], list):
            return [r[0] for r in result]
        return result
    raise HFClientError(f"Unexpected embed_batch response: {type(result)}")


def vision(model: str, prompt: str, image_path: Union[str, Path], system: Optional[str] = None) -> str:
    """Vision inference. Image is base64-encoded and sent in payload.
    Response time on HF free tier is 30-90s.
    """
    img_bytes = Path(image_path).read_bytes()
    b64 = base64.b64encode(img_bytes).decode("utf-8")
    ext = Path(image_path).suffix.lower().lstrip(".")
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/jpeg")

    payload = {
        "inputs": {
            "image": f"data:{mime};base64,{b64}",
            "question": prompt,
        }
    }
    result = _call_with_rotation(model, payload)
    return _extract_text(result, prompt)


def list_models() -> List[str]:
    """Returns configured HF model IDs. Satisfies registry.py's validation call
    without hitting Ollama. Used by get_model() in cloud mode.
    """
    return list(config.HF_MODELS.values())

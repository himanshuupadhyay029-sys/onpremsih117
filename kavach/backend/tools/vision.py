import base64
import logging
from pathlib import Path
import re
from typing import Any, Dict, Optional, Union

from backend import config
from backend.audit.logbook import log_event
from backend.engine import ollama, registry

logger = logging.getLogger("kavach.vision")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

DEFAULT_PROMPT = """Analyze this image and provide a concise, structured technical description:
1. Primary subject and overall identification
2. Any visible text, numbers, readings, or status labels
3. Layout, components, and notable visual features

Strict Rule: If any detail is ambiguous, partially obscured, or uncertain, state clearly that you are 'uncertain' rather than guessing.
"""

QUESTION_PROMPT_TEMPLATE = """Analyze this technical image and answer the specific question below:

Question: {question}

Strict Rule: Answer truthfully and concisely. If the detail requested is ambiguous, unreadable, or not visible in the image, state plainly that you are 'uncertain' rather than guessing.
"""


def _resolve_image_path(raw_path: Union[str, Path]) -> Path:
    """Cleans and resolves the image path across possible root / upload folders."""
    cleaned = str(raw_path).strip().strip("'\"`")
    # If wrapped in "Attached file: <path>", extract the path
    match = re.search(r"(?:Attached file:\s*)([^\r\n]+)", cleaned, re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip().strip("'\"`")

    p = Path(cleaned)
    if p.exists():
        return p.resolve()

    # Search in common project locations
    candidates = [
        config.PROJECT_ROOT / cleaned,
        config.PROJECT_ROOT / "knowledge" / "uploads" / p.name,
        config.PROJECT_ROOT / "testdata" / "scans" / p.name,
        config.PROJECT_ROOT / "testdata" / p.name,
    ]
    for cand in candidates:
        if cand.exists():
            return cand.resolve()

    raise FileNotFoundError(f"Image not found at: {raw_path}")


def describe_image(
    image_path: Union[str, Path],
    question: Optional[str] = None,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Analyzes an image using the local vision specialist model."""
    logger.info(f"[VISION] Stage 1 - Resolving path: {image_path}")
    try:
        p = _resolve_image_path(image_path)
        logger.info(f"[VISION] Stage 1 OK - Resolved path: {p} (size: {p.stat().st_size} bytes)")
    except Exception as exc:
        logger.error(f"[VISION] Stage 1 FAILED - file not found: {image_path} ({exc})")
        raise

    vision_model = registry.get_model("vision")

    if question:
        prompt = QUESTION_PROMPT_TEMPLATE.format(question=question)
    else:
        prompt = DEFAULT_PROMPT

    logger.info("[VISION] Stage 2 - Reading + base64 encoding image")
    with open(p, "rb") as f:
        img_bytes = f.read()
    img_b64 = base64.b64encode(img_bytes).decode("utf-8")
    logger.info(f"[VISION] Stage 2 OK - base64 length: {len(img_b64)} chars")

    logger.info(f"[VISION] Stage 3 - Calling Ollama model={vision_model}")
    payload_preview = {
        "model": vision_model,
        "images_attached": True,
        "images_count": 1,
        "prompt_len": len(prompt),
    }
    logger.info(f"[VISION] Stage 3 payload check: {payload_preview}")

    try:
        response_text = ollama.vision(vision_model, prompt, p)
        logger.info(f"[VISION] Stage 4 - Response received: {str(response_text)[:200]}")
    except Exception as exc:
        logger.error(f"[VISION] Stage 4 FAILED - Ollama error: {exc}")
        response_text = f"[error] Vision model analysis failed: {exc}"

    summary_text = f"Vision analysis on '{p.name}'"
    if question:
        summary_text += f": '{question[:50]}'"

    log_event(
        task_id=task_id,
        event_type="vision",
        actor=vision_model,
        summary=summary_text,
        metadata={
            "image_path": str(p),
            "filename": p.name,
            "question": question,
            "model": vision_model,
            "response_preview": response_text[:200],
        },
        external_calls=0,
    )

    return {
        "description": response_text,
        "image_path": str(p),
        "filename": p.name,
        "model": vision_model,
        "question": question,
    }


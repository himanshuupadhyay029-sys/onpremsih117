"""vision.py — Visual analysis tool using local multimodal vision model (qwen2.5vl:3b).

Assisted understanding with strict honesty guidelines: if details or readings
are ambiguous or low-resolution, the model explicitly states 'uncertain' rather
than guessing confidently.
"""

from pathlib import Path
from typing import Any, Dict, Optional, Union

from backend.audit.logbook import log_event
from backend.engine import ollama, registry

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


def describe_image(
    image_path: Union[str, Path],
    question: Optional[str] = None,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Analyzes an image using the local vision specialist model."""
    p = Path(image_path)
    if not p.exists():
        raise FileNotFoundError(f"Image not found at: {image_path}")

    vision_model = registry.get_model("vision")

    if question:
        prompt = QUESTION_PROMPT_TEMPLATE.format(question=question)
    else:
        prompt = DEFAULT_PROMPT

    try:
        response_text = ollama.vision(vision_model, prompt, p)
    except Exception as exc:
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

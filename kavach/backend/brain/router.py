"""router.py — rule-based task router.

Decides, in well under 50ms, which task_type and model role a task should use.
No LLM call is made unless the rule-based scoring is genuinely ambiguous (a tie,
or no keyword signal at all) — in that case exactly ONE cheap single-word
classification call is made to the reasoning model.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel

from backend.engine import ollama, registry

TaskType = Literal["document", "code", "calc", "search", "vision"]

VALID_TASK_TYPES: List[str] = ["document", "code", "calc", "search", "vision"]

# task_type -> which model role in models.json should handle it
MODEL_ROLE_BY_TASK_TYPE = {
    "document": "reasoning",
    "search": "reasoning",
    "calc": "reasoning",
    "code": "code",
    "vision": "vision",
}

# task_type -> stub tools this kind of task is expected to need (Phase 2: stubs only)
TOOLS_BY_TASK_TYPE = {
    "document": [],
    "search": ["search_stub"],
    "calc": ["calc_stub"],
    "code": [],
    "vision": ["vision_stub"],
}

# Keyword banks used for pure rule-based scoring. Deliberately simple/cheap.
_KEYWORDS = {
    "code": [
        "code", "python", "function", "script", "program", "debug", "bug",
        "class ", "def ", "algorithm", "javascript", "typescript", "java ",
        "c++", "sql", "regex", "compile", "syntax", "refactor", "programming",
        "write a function", "implement a",
    ],
    "calc": [
        "calculate", "compute", "sum of", "average", "mean of", "median",
        "percentage", "how much is", "math problem", "equation", "solve for",
        "arithmetic", "multiply", "divide", "add up", "square root",
    ],
    "search": [
        "search for", "look up", "find information", "find out", "retrieve",
        "how do i", "how to", "steps to", "steps for", "step-by-step",
        "procedure", "procedure for", "sop", "standard operating procedure",
        "protocol", "protocol for", "checklist", "guideline", "guidelines",
        "instructions for", "workflow for", "rules for",
        "specification", "specifications", "tolerance", "tolerances",
        "limit", "limits", "threshold", "thresholds", "maximum", "minimum",
        "rated", "rating", "nominal", "setpoint", "operating range",
        "pressure limit", "temperature limit", "flow rate",
        "inspection", "inspection procedure", "maintenance schedule",
        "preventive maintenance", "shutdown", "startup", "emergency shutdown",
        "safety procedure", "safety protocol", "safety guideline", "safety rules",
        "safety standards", "safety requirement", "safety checklist",
        "hazard control", "hazard response", "hazardous material",
        "lockout", "tagout", "loto", "isolation procedure", "isolation protocol",
        "spill response", "alarm response", "mitigation steps", "incident response",
        "ppe requirement", "ppe standard", "compliance requirement", "regulatory requirement",
        "what is the procedure", "what are the steps", "what is the limit",
        "what is the tolerance", "what are the requirements", "what is the policy",
    ],
    "document": [
        "draft a", "draft an", "draft the", "write a report", "generate a report",
        "create a report", "formal report", "safety report", "incident report",
        "inspection report", "compliance report", "audit report", "technical note",
        "briefing document", "executive summary", "prepare a document",
        "draft documentation", "write documentation", "draft procedure",
        "formal document", "generate docx", "export document",
        "summarize", "summarise", "summary of", "detailed summary",
        "explain in detail", "describe the process", "report on",
        "essay", "write about", "analyze the document", "outline the",
        "what is the role of", "define ",
    ],
    "vision": [
        "image", "photo", "picture", "screenshot", "diagram shown",
        "this image", "in the picture",
    ],
}

_ERROR_MARGIN_ZERO = 0


class RoutingDecision(BaseModel):
    task_type: TaskType
    model_role: str
    tools_needed: List[str]
    reason: str


def _score_task(task_lower: str) -> dict:
    scores = {cat: 0 for cat in _KEYWORDS}
    for cat, keywords in _KEYWORDS.items():
        for kw in keywords:
            if kw in task_lower:
                scores[cat] += 1
    return scores


def _llm_classify(task: str) -> str:
    """Single cheap fallback classification call. Only used when rules are ambiguous."""
    model = registry.get_model("reasoning")
    prompt = (
        "Classify the user's task into exactly one category word from this list: "
        "document, code, calc, search, vision.\n"
        "Respond with ONLY that single lowercase word — no punctuation, no explanation.\n\n"
        f"Task: {task}"
    )
    try:
        raw = ollama.generate(model, prompt).strip().lower()
    except Exception:
        return "document"
    for cat in VALID_TASK_TYPES:
        if cat in raw:
            return cat
    return "document"


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp")


def route(task: str, attachment_type: Optional[str] = None) -> RoutingDecision:
    """Rule-based router. Returns a RoutingDecision with an explainable reason."""
    task_lower = (task or "").lower()

    # Strong structural signal: an image attachment or image filename means vision, no ambiguity.
    has_image_ext = any(ext in task_lower for ext in IMAGE_EXTENSIONS)
    is_image_attachment = bool(attachment_type and attachment_type.lower() in ("image", "photo", "picture"))

    if is_image_attachment or has_image_ext:
        task_type = "vision"
        reason_detail = f"attachment_type='{attachment_type}'" if is_image_attachment else "image file extension detected in task"
        return RoutingDecision(
            task_type=task_type,
            model_role=MODEL_ROLE_BY_TASK_TYPE[task_type],
            tools_needed=TOOLS_BY_TASK_TYPE[task_type],
            reason=f"{reason_detail} deterministically routes to vision",
        )

    scores = _score_task(task_lower)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best_cat, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else _ERROR_MARGIN_ZERO

    if best_score > 0 and best_score > second_score:
        task_type = best_cat
        reason = f"rule-based keyword match: '{best_cat}' scored {best_score} (next best {second_score})"
    else:
        # Either no keywords matched at all, or there's a genuine tie -> ambiguous.
        task_type = _llm_classify(task)
        if task_type not in VALID_TASK_TYPES:
            task_type = "document"
        reason = (
            f"ambiguous rule-based scores {scores} -> single fallback LLM "
            f"classification call returned '{task_type}'"
        )

    return RoutingDecision(
        task_type=task_type,
        model_role=MODEL_ROLE_BY_TASK_TYPE[task_type],
        tools_needed=TOOLS_BY_TASK_TYPE[task_type],
        reason=reason,
    )

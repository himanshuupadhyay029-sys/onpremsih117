"""router.py — rule-based task router.

Decides, in well under 50ms, which task_type and model role a task should use.
No LLM call is made unless the rule-based scoring is genuinely ambiguous (a tie,
or no keyword signal at all) — in that case exactly ONE cheap single-word
classification call is made to the reasoning model.
"""

import json
import logging
from pathlib import Path
import re
from typing import List, Literal, Optional

from pydantic import BaseModel

from backend.engine import ollama, registry
from backend.terminal_logger import log_terminal

logger = logging.getLogger("kavach.router")

TaskType = Literal["document", "code", "calc", "search", "vision", "ocr", "llm"]

VALID_TASK_TYPES: List[str] = ["document", "code", "calc", "search", "vision", "ocr", "llm"]

# task_type -> which model role in models.json should handle it
MODEL_ROLE_BY_TASK_TYPE = {
    "document": "reasoning",
    "search": "reasoning",
    "calc": "reasoning",
    "code": "code",
    "vision": "vision",
    "ocr": "reasoning",
    "llm": "reasoning",
}

# task_type -> tools this kind of task is expected to need
TOOLS_BY_TASK_TYPE = {
    "document": ["document"],
    "search": ["search"],
    "calc": ["calc"],
    "code": ["code"],
    "vision": ["vision"],
    "ocr": ["ocr"],
    "llm": ["llm"],
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
        "calculate", "calc ", "calculation", "compute", "sum of", "average", "mean of", "median",
        "percentage", "how much is", "math problem", "math", "equation", "solve for", "solve ",
        "arithmetic", "multiply", "divide", "add up", "square root",
        "distance", "speed", "velocity", "mph", "km/h", "kmh", "miles", "total distance",
        "verify if", "verify whether", "is this correct", "check if this is correct", "verify step-by-step",
        "formula", "corrosion rate", "remaining life", "wall thickness",
        "plus", "minus", "times", "divided by", "convert minutes", "convert hours",
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
        "knowledge vault", "uploaded document", "uploaded file", "context document",
        "manual", "handbook", "datasheet", "system context",
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
        "this image", "in the picture", "schematic", "gauge", "inspect drawing",
    ],
    "ocr": [
        "ocr", "scan", "scanned", "scanned document", "extract text from image",
        "read text from", "read scan", "transcribe image", "inspection sheet",
    ],
    "llm": [
        "explain", "what is", "why is", "how does", "tell me about", "chat",
        "conversation", "general question", "who is", "help me understand",
    ],
}

_ERROR_MARGIN_ZERO = 0


def _get_vault_doc_names() -> List[str]:
    """Dynamically reads the list of all currently indexed documents in the vault."""
    try:
        from backend.vault.ingest import METADATA_PATH
        if not METADATA_PATH.exists():
            return []
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)
        return sorted({entry.get("source_filename") for entry in meta if entry.get("source_filename")})
    except Exception:
        return []


def _matches_vault_document(task_lower: str, doc_names: Optional[List[str]] = None) -> bool:
    """Dynamically checks if the query references any active document in the Knowledge Vault."""
    docs = doc_names if doc_names is not None else _get_vault_doc_names()
    if not docs:
        return False

    task_words = set(re.findall(r"[a-z0-9]+", task_lower))

    for doc in docs:
        doc_lower = doc.lower()
        stem = Path(doc).stem.lower()

        # 1. Direct substring match of full filename or stem
        if (len(doc_lower) > 3 and doc_lower in task_lower) or (len(stem) > 3 and stem in task_lower):
            return True

        # 2. Normalized stem (e.g. 'kavach_context' -> 'kavach context')
        norm_stem = re.sub(r"[_\-.\(\)\[\]0-9]+", " ", stem).strip()
        if len(norm_stem) > 3 and norm_stem in task_lower:
            return True

        # 3. Token match: check if significant stem words appear in the task
        stem_tokens = [w for w in re.findall(r"[a-z0-9]+", stem) if len(w) >= 3 and not w.isdigit()]
        if stem_tokens:
            matched_tokens = [w for w in stem_tokens if w in task_words or w in task_lower]
            if len(stem_tokens) == 1 and len(matched_tokens) == 1:
                return True
            elif len(stem_tokens) > 1 and len(matched_tokens) >= max(2, len(stem_tokens) // 2):
                return True

    return False


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
    if _matches_vault_document(task_lower):
        scores["search"] += 3  # Strong signal for vault document queries
    return scores


def _llm_classify(task: str) -> str:
    """Single cheap fallback classification call. Only used when rules are ambiguous."""
    model = registry.get_model("reasoning")
    prompt = (
        "Classify the user's task into exactly one category word from this list: "
        "document, code, calc, search, vision, ocr, llm.\n\n"
        "Guidelines:\n"
        "- 'calc': arithmetic, formulas, math verification, numerical word problems (speed, distance, conversions).\n"
        "- 'code': writing or executing Python/JS/C programming scripts.\n"
        "- 'document': drafting formal reports or Word documents.\n"
        "- 'search': looking up SOPs or procedures in the Knowledge Vault.\n"
        "- 'vision': analyzing an image.\n"
        "- 'ocr': extracting text from scanned images.\n"
        "- 'llm': general knowledge chat.\n\n"
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


def route(
    task: str,
    attachment_type: Optional[str] = None,
    hint: Optional[str] = None,
    context: Optional[str] = None,
) -> RoutingDecision:
    """Rule-based router with optional planner hint support. Returns a RoutingDecision."""
    task_lower = (task or "").lower()

    # If planner explicitly hinted a valid specialized tool, respect the planner's architecture
    normalized_hint = (hint or "").strip().lower()
    if normalized_hint in VALID_TASK_TYPES and normalized_hint != "llm":
        return RoutingDecision(
            task_type=normalized_hint,  # type: ignore[arg-type]
            model_role=MODEL_ROLE_BY_TASK_TYPE[normalized_hint],
            tools_needed=TOOLS_BY_TASK_TYPE[normalized_hint],
            reason=f"planner designated tool '{normalized_hint}' directly assigned",
        )

    # OCR detection takes priority over generic vision for text reading
    if any(w in task_lower for w in ["ocr", "scan", "scanned document", "read text from image"]):
        task_type = "ocr"
        return RoutingDecision(
            task_type=task_type,
            model_role=MODEL_ROLE_BY_TASK_TYPE[task_type],
            tools_needed=TOOLS_BY_TASK_TYPE[task_type],
            reason="explicit OCR / scanning keywords detected",
        )

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
        # If hint was provided, use it over generic LLM classification fallback
        if normalized_hint in VALID_TASK_TYPES:
            task_type = normalized_hint
            reason = f"ambiguous scores -> resolved to planner hint '{normalized_hint}'"
        else:
            # Either no keywords matched at all, or there's a genuine tie -> ambiguous.
            task_type = _llm_classify(task)
            if task_type not in VALID_TASK_TYPES:
                task_type = "document"
            reason = (
                f"ambiguous rule-based scores {scores} -> single fallback LLM "
                f"classification call returned '{task_type}'"
            )

    decision = RoutingDecision(
        task_type=task_type,  # type: ignore[arg-type]
        model_role=MODEL_ROLE_BY_TASK_TYPE[task_type],
        tools_needed=TOOLS_BY_TASK_TYPE[task_type],
        reason=reason,
    )
    log_terminal("Router", f"Evaluated sub-task -> intent '{decision.task_type}' (role '{decision.model_role}') | {decision.reason}")
    return decision

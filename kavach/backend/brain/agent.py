"""agent.py — the agent loop: PLAN -> EXECUTE -> OBSERVE, wired as a cyclic
LangGraph StateGraph (not a straight line).

Phase 2: agent loop with self-correction and router.
Phase 3: append-only audit logbook integration.
Phase 4: Knowledge Vault FAISS RAG search tool.
Phase 5: Word Document (.docx) writer with anti-hallucination guard.
Phase 6: network-isolated Docker sandbox for code execution with error-feedback self-correction.
Phase 7: OCR (reading scanned/image documents) + Vision (multimodal image/drawing analysis).
Phase 8: Deterministic engineering math calculator (calc.py) showing real arithmetic steps.
Phase 11: Human approval gate for high-stakes document outputs (approve.py).
"""

from datetime import datetime
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import uuid

from langgraph.graph import END, StateGraph

from backend.audit.logbook import log_event
from backend.brain.event_bus import emit_sync
from backend.brain.router import route
from backend.brain.state import AgentState
from backend.brain.tools_dispatch import dispatch_tool
from backend.engine import ollama, registry
from backend.guard.approve import assess_risk, request_approval
from backend.tools.calc import calculate as calc_tool
from backend.tools.code import write_and_run as code_tool_run
from backend.tools.ocr import extract_text as ocr_tool_extract
from backend.tools.search import search as search_tool
from backend.tools.vision import describe_image as vision_tool_describe
from backend.tools.writer import draft_document, render_docx, write_document as writer_tool

import time
from backend.terminal_logger import (
    log_terminal as _log_terminal,
    log_graph_start,
    log_graph_complete,
    log_node_enter,
    log_node_exit,
    log_plan,
    log_route,
    log_observe,
    log_guard,
    log_fact_update,
)

logger = logging.getLogger("kavach.agent")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


MAX_TOTAL_STEPS = 8
MAX_REVISIONS = 2
ERROR_TRIGGER = "simulate_error"
CODE_TIMEOUT_SECONDS = 15
MAX_HISTORY_TURNS = 12
MAX_HISTORY_CHARS_PER_MSG = 1200


def _get_vault_document_names() -> List[str]:
    """Dynamically reads the list of all currently indexed documents in the vault."""
    from backend.vault.ingest import METADATA_PATH
    if not METADATA_PATH.exists():
        return []
    try:
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)
        return sorted({entry.get("source_filename") for entry in meta if entry.get("source_filename")})
    except Exception:
        return []


def _matches_vault_document(task_lower: str, doc_names: Optional[List[str]] = None) -> bool:
    """Dynamically checks if the query references any active document in the Knowledge Vault."""
    docs = doc_names if doc_names is not None else _get_vault_document_names()
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


VALID_TOOLS = {"llm", "search", "calc", "vision", "document", "code", "ocr"}

MASTER_PLAN_PROMPT_TEMPLATE = """You are the master task planner for KAVACH, an autonomous on-premises industrial operations assistant.
Break down the user's request into the minimum necessary number of ordered sub-tasks (1 to 8 steps).

{vault_section}
CRITICAL RULES:
1. MINIMALITY: If the request is a single action, simple question, search, code request, or calculation, output EXACTLY 1 step.
2. DYNAMIC KNOWLEDGE VAULT RETRIEVAL:
   - Check the "Available Knowledge Vault Documents" list above.
   - If the user's request asks about, references, or requires information from ANY of the available documents in the Knowledge Vault (or asks about specifications, procedures, policies, guidelines, architecture, or domain context that might be contained in them), you MUST plan a 'search' step to retrieve the source excerpts from the Knowledge Vault!
3. COMPOUND & MULTIMODAL REQUESTS: If the user's request combines multiple distinct capabilities:
   - Multimodal Compound: If an image is attached or referenced AND the user asks to write code, do a calculation, write a document, or generate creative writing/poems, you MUST separate them into multiple distinct steps!
     Step 1 'vision' to inspect and describe the image.
     Step 2 'llm' to write the poem or analysis based on the image description.
     Step 3 'code' to generate and execute the requested Python script in the Docker sandbox.
     CRITICAL: NEVER put coding, calculations, poems, or document drafting into a 'vision' step! The 'vision' tool CAN ONLY inspect and describe images.
   - Code + Document: Step 1 'code' to run script in sandbox, Step 2 'document' to create Word report.
   - Search + Calc / Code / Document: Step 1 'search', Step 2 'calc' or 'code' or 'document'.
4. ATOMIC TOOL STEPS: Never split the execution of a single capability into multiple steps (e.g. do NOT create separate 'write code', 'run code', 'verify code' steps — a coding task is ONE step with tool 'code').
5. Each step must be a concrete, actionable sub-task with:
   - "step_num": integer (1, 2, 3, ...)
   - "tool": one of ["search", "calc", "code", "document", "ocr", "vision", "llm"]
   - "input": clear specific instruction for that step

Capabilities:
- "search": Look up information, SOPs, incident procedures, equipment specs, architecture, or uploaded documents in the Knowledge Vault.
- "calc": Numerical arithmetic, formulas, remaining life, corrosion rates, or unit conversions.
- "code": Generate and run Python/JS/C scripts in the secure Docker container sandbox.
- "document": Draft formal corporate Word (.docx) documents, reports, or SOPs.
- "ocr": Read and extract text from scanned images or inspection sheets.
- "vision": Inspect diagrams, schematics, photos, or gauges.
- "llm": Direct answering, general explanation, or conversational reasoning for generic topics not in the vault.

Examples:
Request: "Search the SOPs for who must be notified during a Severity 1 incident."
Output:
[
  {{"step_num": 1, "tool": "search", "input": "Search the SOPs for who must be notified during a Severity 1 incident."}}
]

Request: "Write and run a python script that prints 'KAVACH_SANDBOX_ONLINE' and the value of 14 * 7"
Output:
[
  {{"step_num": 1, "tool": "code", "input": "Write and run a python script that prints 'KAVACH_SANDBOX_ONLINE' and the value of 14 * 7"}}
]

Request: "Write a python code for basic calculation like plus, minus, divide, and multiply to execute 50*10 and then create a document for this code"
Output:
[
  {{"step_num": 1, "tool": "code", "input": "Write and execute python code to perform basic calculations and execute 50*10"}},
  {{"step_num": 2, "tool": "document", "input": "Create a formal document documenting the calculation code and execution results"}}
]

Request: "Analyse this image, and then create a poem on it and then write a python code to print Dogs are most loyal animal"
Output:
[
  {{"step_num": 1, "tool": "vision", "input": "Analyze the attached image in detail."}},
  {{"step_num": 2, "tool": "llm", "input": "Create a poem inspired by the image analysis."}},
  {{"step_num": 3, "tool": "code", "input": "Write and run a python script to print 'Dogs are most loyal animal'"}}
]

Request: "Draft an emergency containment procedure document for pipeline Bravo."
Output:
[
  {{"step_num": 1, "tool": "document", "input": "Draft an emergency containment procedure document for pipeline Bravo."}}
]

Request: "Find the corrosion rate limit for Tank-4, then calculate remaining life if thickness is 8mm, and draft an inspection report"
Output:
[
  {{"step_num": 1, "tool": "search", "input": "Search Knowledge Vault for Tank-4 corrosion rate limit"}},
  {{"step_num": 2, "tool": "calc", "input": "Calculate remaining life of Tank-4 with thickness 8mm using retrieved corrosion rate"}},
  {{"step_num": 3, "tool": "document", "input": "Draft formal inspection report on Tank-4 remaining lifespan"}}
]

Request: "A car travels at 60 mph for 45 minutes and then 40 mph for 30 minutes. The total distance covered is 65 miles. Verify if this is correct step-by-step and create a summary."
Output:
[
  {{"step_num": 1, "tool": "calc", "input": "Calculate distance for leg 1: speed 60 mph for 45 minutes (45/60 hours)"}},
  {{"step_num": 2, "tool": "calc", "input": "Calculate distance for leg 2: speed 40 mph for 30 minutes (30/60 hours)"}},
  {{"step_num": 3, "tool": "calc", "input": "Calculate total distance: leg1_distance + leg2_distance and verify against 65 miles"}}
]

{history_section}User Request: {task}
{attachment_info}

Respond with ONLY a raw JSON array of step objects. No markdown formatting, no other text:
"""


OBSERVE_PROMPT_TEMPLATE = """You are the autonomous reasoning controller for KAVACH, an on-premises industrial operations assistant.
Your job is to analyze the execution output of the sub-task step just completed, compare it against the overall user request, and decide the next action.

Original User Task:
{task}

Master Plan:
{plan_overview}

Current Step #{step_num} of {total_steps} [{tool}]:
Input: {step_input}
Execution Status: {status_str}
Execution Output:
{output_preview}

Accumulated Key Facts from Workflow:
{key_facts_json}

CRITICAL RULES FOR DECIDING ACTION:
1. IF NOT THE LAST STEP (Step #{step_num} < {total_steps}):
   - You MUST NOT choose "done"! The Master Plan still has pending steps that must be executed.
   - If the current step succeeded or made acceptable progress, choose "continue" to proceed to the next step.
   - If the step failed with an error, choose "retry" (with retry_instruction) or "replan".
2. IF THIS IS THE LAST STEP (Step #{step_num} of {total_steps}):
   - NEVER choose "continue"! ("continue" is only valid if another step already exists in the Master Plan).
   - If ALL parts of the Original User Task have been satisfied, select "done".
   - If ANY part of the Original User Task remains unfulfilled (such as writing code, running a script, drafting a document, or explaining/computing values), you MUST select "replan" and provide the uncompleted task(s) in "new_steps"!
3. IF STEP ENCOUNTERED AN ERROR: Choose "retry" and provide a refined instruction in "retry_instruction".
   - For calculation errors: retry using 'calc' with pure arithmetic formulas. NEVER switch to 'code' scripts unless the user specifically asked for code.

Available Actions:
- "continue": ONLY VALID IF #{step_num} < {total_steps}. The current step succeeded and more steps remain in the Master Plan.
- "replan": Unfulfilled user goals remain missing from the plan, or execution output revealed new requirements. Provide remaining steps in "new_steps".
- "retry": The step encountered a fixable failure or error. Provide refined instruction in "retry_instruction".
- "done": ONLY VALID ON THE LAST STEP (#{total_steps} of {total_steps}) when all planned steps have completed and the user's request is satisfied.
- "clarify": Crucial ambiguity prevents completing the task, requiring user input. Provide the specific question in "clarify_question".

Respond with ONLY a valid JSON object matching this schema. No markdown formatting, no other text:
{{
  "action": "continue" | "replan" | "retry" | "done" | "clarify",
  "reasoning": "1-2 sentence justification for this decision",
  "new_steps": [
    {{"tool": "search|calc|code|document|ocr|vision|llm", "input": "concrete instruction"}}
  ],
  "retry_instruction": "refined instruction if retry",
  "clarify_question": "question to ask user if clarify"
}}
"""



def _format_history(history: Optional[List[dict]]) -> str:
    """Formats the last N conversation turns into a bounded context string for 3B LLM prompts."""
    if not history:
        return ""
    recent = history[-MAX_HISTORY_TURNS:]
    lines = []
    for msg in recent:
        role = (msg.get("role") or "user").capitalize()
        content = (msg.get("content") or "").strip()
        if len(content) > MAX_HISTORY_CHARS_PER_MSG:
            content = content[:MAX_HISTORY_CHARS_PER_MSG - 3] + "..."
        if content:
            lines.append(f"{role}: {content}")
    if not lines:
        return ""
    return "Prior Conversation Context:\n" + "\n".join(lines) + "\n"



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_tool(name: str) -> str:
    n = (name or "").strip().lower()
    if n in VALID_TOOLS:
        return n
    if "calc" in n or "math" in n or "compute" in n or "formula" in n:
        return "calc"
    if "ocr" in n or "scan" in n:
        return "ocr"
    if "vision" in n or "image" in n or "photo" in n or "diagram" in n or "drawing" in n:
        return "vision"
    if "code" in n or "python" in n or "script" in n or "execute" in n or "sandbox" in n:
        return "code"
    if "search" in n or "web" in n or "browse" in n or "vault" in n:
        return "search"
    if "doc" in n or "write" in n or "word" in n:
        return "document"
    return "llm"


def _parse_master_plan(
    raw: str,
    original_task: str,
    attachment_type: Optional[str] = None,
) -> List[dict]:
    """Robustly parses the master planner's JSON output into ordered PlanSteps."""
    text = (raw or "").strip()
    fence_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        bracket_match = re.search(r"(\[.*\])", text, re.DOTALL)
        if bracket_match:
            text = bracket_match.group(1)

    parsed_steps: List[dict] = []
    try:
        data = json.loads(text)
        if isinstance(data, list):
            for i, item in enumerate(data[:3]):
                if isinstance(item, dict):
                    tool = _normalize_tool(item.get("tool") or item.get("tool_hint", "llm"))
                    step_input = str(item.get("input") or item.get("description") or original_task).strip()
                    parsed_steps.append({
                        "step_num": i + 1,
                        "tool": tool,
                        "input": step_input,
                        "status": "pending",
                    })
        # 1. Collapse multiple redundant consecutive 'code' steps into one code step
        filtered_steps = []
        has_code_step = False
        for s in parsed_steps:
            if s.get("tool") == "code":
                if not has_code_step:
                    filtered_steps.append(s)
                    has_code_step = True
            else:
                filtered_steps.append(s)
        parsed_steps = filtered_steps

        # 2. Compound intent preservation across multimodal, code, creative writing, and documentation:
        task_lower = original_task.lower()
        has_img_intent = any(ext in task_lower for ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp")) or bool(
            attachment_type and attachment_type.lower() in ("image", "photo", "picture", "file")
        ) or "analyse this image" in task_lower or "analyze this image" in task_lower or "attached file" in task_lower

        has_code_intent = any(w in task_lower for w in ["python", "script", "print ", "write a code", "write python", "execute code", "sandbox"])
        has_poem_intent = any(w in task_lower for w in ["poem", "poetry", "rhyme", "verse", "song"])
        has_doc_intent = any(kw in task_lower for kw in [
            "create a document", "create document", "draft a document", "draft document",
            "make a document", "generate document", "generate a document", "generate docx",
            "write a report", "draft a report", "create a report", "document for this", "document this"
        ])

        # If vision tool was planned alongside other intents, make sure Step 1 input is clean
        has_vision_step = any(s.get("tool") == "vision" for s in parsed_steps)
        if has_vision_step:
            for s in parsed_steps:
                if s.get("tool") == "vision":
                    if has_code_intent or has_poem_intent or has_doc_intent:
                        s["input"] = "Inspect and analyze the attached image in detail."

        # Ensure poem step exists if requested
        has_poem_step = any(s.get("tool") == "llm" for s in parsed_steps)
        if has_poem_intent and not has_poem_step and len(parsed_steps) < MAX_TOTAL_STEPS:
            parsed_steps.append({
                "step_num": len(parsed_steps) + 1,
                "tool": "llm",
                "input": "Create a poem inspired by the image analysis.",
                "status": "pending",
            })

        # Ensure code step exists if requested
        has_code_step = any(s.get("tool") == "code" for s in parsed_steps)
        if has_code_intent and not has_code_step and len(parsed_steps) < MAX_TOTAL_STEPS:
            m = re.search(r"write (?:a )?python code to (.*)", original_task, re.IGNORECASE)
            c_input = f"Write and run a Python script to {m.group(1).strip()}" if m else f"Write and execute Python script as requested in: {original_task}"
            parsed_steps.append({
                "step_num": len(parsed_steps) + 1,
                "tool": "code",
                "input": c_input,
                "status": "pending",
            })

        # Ensure document step exists if requested
        has_doc_step = any(s.get("tool") == "document" for s in parsed_steps)
        if has_doc_intent and not has_doc_step and len(parsed_steps) < MAX_TOTAL_STEPS:
            parsed_steps.append({
                "step_num": len(parsed_steps) + 1,
                "tool": "document",
                "input": f"Draft formal document for: {original_task}",
                "status": "pending",
            })

        for i, s in enumerate(parsed_steps):
            s["step_num"] = i + 1
    except Exception:
        parsed_steps = []

    if not parsed_steps:
        # High confidence fallback based on keywords and attachments
        task_lower = original_task.lower()
        has_img_intent = any(ext in task_lower for ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp")) or bool(
            attachment_type and attachment_type.lower() in ("image", "photo", "picture", "file")
        ) or "analyse this image" in task_lower or "analyze this image" in task_lower or "attached file" in task_lower
        has_doc_intent = any(kw in task_lower for kw in [
            "create a document", "create document", "draft a document", "draft document",
            "make a document", "generate document", "generate a document", "generate docx",
            "write a report", "draft a report", "create a report", "document for this", "document this"
        ])
        has_code_intent = any(w in task_lower for w in ["python", "script", "code", "program", "compile", "sandbox", "print "])
        has_poem_intent = any(w in task_lower for w in ["poem", "poetry", "rhyme", "verse", "song"])

        if has_img_intent and (has_poem_intent or has_code_intent or has_doc_intent):
            parsed_steps = [
                {"step_num": 1, "tool": "vision", "input": "Analyze the attached image in detail.", "status": "pending"}
            ]
            if has_poem_intent:
                parsed_steps.append({
                    "step_num": len(parsed_steps) + 1,
                    "tool": "llm",
                    "input": "Create a poem inspired by the image analysis.",
                    "status": "pending",
                })
            if has_code_intent:
                m = re.search(r"write (?:a )?python code to (.*)", original_task, re.IGNORECASE)
                c_input = f"Write and run a Python script to {m.group(1).strip()}" if m else f"Write and execute Python script as requested in: {original_task}"
                parsed_steps.append({
                    "step_num": len(parsed_steps) + 1,
                    "tool": "code",
                    "input": c_input,
                    "status": "pending",
                })
            if has_doc_intent:
                parsed_steps.append({
                    "step_num": len(parsed_steps) + 1,
                    "tool": "document",
                    "input": f"Draft formal document for: {original_task}",
                    "status": "pending",
                })
        elif has_code_intent and has_doc_intent:
            parsed_steps = [
                {"step_num": 1, "tool": "code", "input": original_task, "status": "pending"},
                {"step_num": 2, "tool": "document", "input": f"Draft formal document for: {original_task}", "status": "pending"},
            ]
        elif any(w in task_lower for w in ["ocr", "scan", "scanned"]):
            fallback_tool = "ocr"
            parsed_steps = [{"step_num": 1, "tool": fallback_tool, "input": original_task, "status": "pending"}]
        elif has_img_intent:
            fallback_tool = "vision"
            parsed_steps = [{"step_num": 1, "tool": fallback_tool, "input": original_task, "status": "pending"}]
        elif has_code_intent:
            fallback_tool = "code"
            parsed_steps = [{"step_num": 1, "tool": fallback_tool, "input": original_task, "status": "pending"}]
        elif any(w in task_lower for w in ["calculate", "calc", "compute", "arithmetic", "sum of", "solve for", "mph", "miles", "distance", "speed", "total distance", "verify if"]):
            fallback_tool = "calc"
            parsed_steps = [{"step_num": 1, "tool": fallback_tool, "input": original_task, "status": "pending"}]
        elif has_doc_intent:
            fallback_tool = "document"
            parsed_steps = [{"step_num": 1, "tool": fallback_tool, "input": original_task, "status": "pending"}]
        # Dynamic check: Does the request mention any active document indexed in the Knowledge Vault?
        if _matches_vault_document(task_lower) or any(w in task_lower for w in [
            "search", "sop", "procedure", "guideline", "standard operating procedure",
            "knowledge vault", "uploaded document", "uploaded file", "context document",
            "policy document", "manual", "handbook", "datasheet", "specification",
            "specs", "thresholds", "guidelines",
        ]):
            fallback_tool = "search"
            parsed_steps = [{"step_num": 1, "tool": fallback_tool, "input": original_task, "status": "pending"}]
        else:
            fallback_tool = "llm"
            parsed_steps = [{"step_num": 1, "tool": fallback_tool, "input": original_task, "status": "pending"}]

    return parsed_steps


def _run_stub_tool(tool: str, input_str: str, original_task: str, revise_count: int) -> Tuple[str, bool]:
    trigger_present = ERROR_TRIGGER in original_task.lower().replace(" ", "_")
    if trigger_present and revise_count == 0:
        return (
            f"[error] stub '{tool}' tool failed (simulated transient failure, for the self-correction demo).",
            True,
        )
    return f"[stub {tool} result] Pretend output for input: {input_str!r}", False


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def master_plan_node(state: AgentState) -> dict:
    """Master Planner Layer: Decomposes the user request into ordered sub-tasks before routing."""
    t_start = time.perf_counter()
    # Fast-path for resumed execution (e.g. operator clarification reply or approval continuation)
    if state.get("resumed") and state.get("plan"):
        current_idx = state.get("current_step", 0)
        updated_plan = list(state["plan"])
        reply = state.get("operator_reply")
        if reply and current_idx < len(updated_plan):
            orig_inp = updated_plan[current_idx]["input"]
            if reply not in orig_inp:
                updated_plan[current_idx]["input"] = f"{orig_inp}\n\n[Operator Clarification]: {reply}"
            updated_plan[current_idx]["status"] = "pending"

        log_plan(state.get("task_id", ""), updated_plan, is_resume=True, current_step=current_idx + 1)
        thought = {
            "role": "thought",
            "content": f"Resuming execution of existing plan from Step {current_idx + 1} with operator clarification.",
        }
        return {
            "plan": updated_plan,
            "status": "executing",
            "clarify_question": None,
            "trace": [thought],
        }

    reasoning_model = registry.get_model("reasoning")
    log_node_enter("planner", state.get("task_id"), f"Decomposing task with model '{reasoning_model}'")
    history_section = ""
    if state.get("history_context"):
        history_section = f"{state['history_context']}\n"

    attachment_info = ""
    if state.get("attachment_type"):
        attachment_info = f"Attachment present (type: {state['attachment_type']})\n"

    vault_docs = _get_vault_document_names()
    if vault_docs:
        docs_list_str = "\n".join(f"- {d}" for d in vault_docs)
        vault_section = f"Available Knowledge Vault Documents (Live Index):\n{docs_list_str}\n"
    else:
        vault_section = "Available Knowledge Vault Documents: (None currently indexed in vault)\n"

    prompt = MASTER_PLAN_PROMPT_TEMPLATE.format(
        vault_section=vault_section,
        history_section=history_section,
        task=state["original_task"],
        attachment_info=attachment_info,
    )

    thought = {
        "role": "thought",
        "content": "Master Planner: Analyzing user request and decomposing into ordered sub-tasks.",
    }

    try:
        raw = ollama.generate(reasoning_model, prompt)
        if not raw.strip():
            _log_terminal("Planner", f"[WARN] Reasoning model '{reasoning_model}' returned empty plan. Using keyword fallback.")
    except Exception as exc:  # noqa: BLE001
        raw = ""
        _log_terminal("Planner", f"[ERROR] Master Planner LLM call failed: {exc}. Using keyword fallback.")
        thought = {"role": "thought", "content": f"Master Planner LLM call error ({exc}); using fallback single-step plan."}

    steps = _parse_master_plan(
        raw,
        original_task=state["original_task"],
        attachment_type=state.get("attachment_type"),
    )

    elapsed = time.perf_counter() - t_start
    log_plan(state.get("task_id", ""), steps, is_resume=False)
    log_node_exit("planner", state.get("task_id"), status="OK", elapsed_s=elapsed)

    action = {"role": "action", "content": f"Master Plan established ({len(steps)} sub-task(s)): {json.dumps(steps)}"}

    log_event(
        task_id=state.get("task_id"),
        event_type="plan",
        actor=reasoning_model,
        summary=f"Master Planner decomposed request into {len(steps)} sub-task(s)",
        metadata={
            "task": state.get("original_task"),
            "model": reasoning_model,
            "steps": steps,
            "step_count": len(steps),
        },
        external_calls=0,
    )

    emit_sync(
        state.get("task_id"),
        "plan",
        {
            "task_id": state.get("task_id"),
            "steps": steps,
            "step_count": len(steps),
            "model": reasoning_model,
        },
    )

    return {
        "plan": steps,
        "current_step": 0,
        "status": "executing",
        "shared_memory": "",
        "trace": [thought, action],
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": raw},
        ],
    }


def route_subtask_node(state: AgentState) -> dict:
    """Per-Subtask Intent Routing: Evaluates the active subtask and selects the model role and tool."""
    idx = state["current_step"]
    step = state["plan"][idx]

    # Intent routing for this specific sub-task
    routing_dec = route(
        task=step["input"],
        attachment_type=state.get("attachment_type"),
        hint=step.get("tool"),
        context=state.get("shared_memory"),
    )

    # Align subtask tool with the routed intent
    step["tool"] = routing_dec.task_type
    step["status"] = "executing"
    model_tag = registry.get_model(routing_dec.model_role)
    step["model"] = model_tag
    step["model_role"] = routing_dec.model_role

    log_route(step["step_num"], len(state["plan"]), routing_dec.task_type, routing_dec.model_role, model_tag, routing_dec.reason)

    thought = {
        "role": "thought",
        "content": (
            f"Sub-Task {step['step_num']}/{len(state['plan'])}: "
            f"Routed to intent '{routing_dec.task_type}' (Model: {routing_dec.model_role} -> {model_tag}). "
            f"Reason: {routing_dec.reason}"
        ),
    }

    log_event(
        task_id=state.get("task_id"),
        event_type="route",
        actor="router",
        summary=f"Sub-Task {step['step_num']} routed to '{routing_dec.task_type}' ({routing_dec.model_role})",
        metadata={
            "step_num": step["step_num"],
            "subtask_input": step["input"],
            "task_type": routing_dec.task_type,
            "model_role": routing_dec.model_role,
            "model_tag": model_tag,
            "tools_needed": routing_dec.tools_needed,
            "reason": routing_dec.reason,
        },
        external_calls=0,
    )

    emit_sync(
        state.get("task_id"),
        "step_start",
        {
            "task_id": state.get("task_id"),
            "step_num": step["step_num"],
            "total_steps": len(state["plan"]),
            "tool": routing_dec.task_type,
            "model": model_tag,
            "model_role": routing_dec.model_role,
            "input": step["input"],
        },
    )

    return {
        "routing_decision": routing_dec.model_dump(),
        "plan": state["plan"],
        "trace": [thought],
    }



def execute_node(state: AgentState) -> dict:
    idx = state["current_step"]
    step = state["plan"][idx]
    tool = step["tool"]
    step_input = step["input"]
    t0 = time.perf_counter()

    log_node_enter("executor", state.get("task_id"), f"Step {step['step_num']}/{len(state['plan'])} [{tool}] with model '{step.get('model', 'specialist')}'")

    thought = {"role": "thought", "content": f"Executing step {step['step_num']}: tool='{tool}', input={step_input!r}"}
    action = {"role": "action", "content": f"CALL {tool}({step_input!r})"}

    dispatch_res = dispatch_tool(tool, step_input, state)

    output = dispatch_res["output"]
    is_error = dispatch_res["is_error"]
    actor = dispatch_res["actor"]
    sources = dispatch_res["sources"]
    is_grounded_flag = dispatch_res["is_grounded"]
    doc_meta = dispatch_res["doc_meta"]
    code_meta = dispatch_res["code_meta"]
    extra_meta = dispatch_res["extra_meta"]
    messages_update = dispatch_res["messages_update"]
    new_facts = dispatch_res.get("key_facts", {})

    accumulated_key_facts = dict(state.get("key_facts") or {})
    accumulated_key_facts.update(new_facts)

    elapsed = time.perf_counter() - t0
    log_node_exit("executor", state.get("task_id"), status="ERROR" if is_error else "OK", elapsed_s=elapsed, summary=f"Step {step['step_num']} [{tool}] via '{actor}'")
    if new_facts:
        log_fact_update(new_facts)

    step_output = {
        "step_num": step["step_num"],
        "tool": tool,
        "model": actor,
        "model_role": step.get("model_role", "reasoning"),
        "input": step_input,
        "output": output,
        "error": is_error,
        "grounded": is_grounded_flag,
    }
    if sources:
        step_output["sources"] = sources
    if doc_meta:
        step_output.update(doc_meta)
    if code_meta:
        step_output.update(code_meta)
    if extra_meta:
        step_output.update(extra_meta)

    step["status"] = "failed" if is_error else "done"
    step["model"] = actor
    step["output"] = output

    output_summary = f"[Sub-Task {step['step_num']} ({tool}) Result]:\n{output}"
    current_mem = state.get("shared_memory", "")
    new_shared_mem = f"{current_mem}\n\n{output_summary}".strip() if current_mem else output_summary

    observation = {"role": "observation", "content": f"Result: {output[:300]}"}

    log_event(
        task_id=state.get("task_id"),
        event_type="step",
        actor=actor,
        summary=f"Sub-Task {step['step_num']} ({tool}): {'ERROR' if is_error else 'OK'} - {output[:100]}",
        metadata={
            "task": state.get("original_task"),
            "step_num": step["step_num"],
            "tool": tool,
            "model": actor,
            "model_role": step.get("model_role"),
            "input": step_input,
            "output_preview": output[:300],
            "error": is_error,
            "grounded": is_grounded_flag,
            **doc_meta,
            **code_meta,
            **extra_meta,
        },
        external_calls=0,
    )

    emit_sync(
        state.get("task_id"),
        "tool_done",
        {
            "task_id": state.get("task_id"),
            "step_num": step["step_num"],
            "tool": tool,
            "output_preview": output[:300],
            "error": is_error,
            "key_facts": accumulated_key_facts,
        },
    )

    return {
        "step_outputs": [step_output],
        "shared_memory": new_shared_mem,
        "key_facts": accumulated_key_facts,
        "trace": [thought, action, observation],
        "messages": messages_update,
    }


def observe_node(state: AgentState) -> dict:
    """Evaluates the execution output using the LLM controller to determine next dynamic action."""
    last_output = state["step_outputs"][-1]
    is_error = last_output.get("error", False)
    is_ungrounded_search = (last_output.get("tool") == "search") and not last_output.get("sources")
    revise_count = state.get("revise_count", 0)
    replan_count = state.get("replan_count", 0)

    trace_entries = [
        {
            "role": "observation",
            "content": f"Sub-Task {last_output['step_num']} ({last_output['tool']}) -> "
            f"{'ERROR' if is_error else ('UNGROUNDED' if is_ungrounded_search else 'OK')}: {last_output['output'][:200]}",
        }
    ]

    # Human approval gate pause takes immediate precedence
    if last_output.get("tool") == "document" and last_output.get("awaiting_approval"):
        trace_entries.append(
            {
                "role": "thought",
                "content": f"Document draft '{last_output.get('title')}' requires human approval ({last_output.get('risk')} risk). Pausing agent.",
            }
        )
        log_event(
            task_id=state.get("task_id"),
            event_type="observe",
            actor="agent_loop",
            summary=f"Document '{last_output.get('title')}' paused for human approval (Risk: {last_output.get('risk')}).",
            metadata={"decision": "awaiting_approval", "risk": last_output.get("risk")},
            external_calls=0,
        )
        emit_sync(
            state.get("task_id"),
            "observe",
            {
                "task_id": state.get("task_id"),
                "action": "awaiting_approval",
                "reasoning": f"Document '{last_output.get('title')}' paused for human approval",
                "status": "awaiting_approval",
            },
        )
        return {"trace": trace_entries, "status": "awaiting_approval"}

    # Autonomous LLM Reasoning Controller: Ask LLM to evaluate status and decide action
    reasoning_model = registry.get_model("reasoning")
    plan_overview = "\n".join(
        f"- Step {s['step_num']} [{s['tool']}]: {s['input']} (Status: {s.get('status', 'pending')})"
        for s in state["plan"]
    )
    status_str = "FAILED" if is_error else ("UNGROUNDED_SEARCH" if is_ungrounded_search else "SUCCESS")
    key_facts_json = json.dumps(state.get("key_facts", {}), indent=2)
    total_steps = len(state["plan"])

    step_input_val = str(last_output.get("input") or "")
    output_text = str(last_output.get("output") or "")

    # Check for missing parameters that require human clarification on current step
    needs_clarification = bool(
        last_output.get("needs_clarification")
        or (is_error and ("missing required input" in output_text.lower() or "missing required parameter" in output_text.lower()))
    )

    action = "continue"
    reasoning = "Sub-task executed successfully."
    new_steps: List[dict] = []
    retry_instruction = ""
    clarify_question = ""

    if needs_clarification:
        clar_q = (
            last_output.get("clarify_question")
            or state.get("key_facts", {}).get("clarify_question")
            or (output_text.replace("[error]", "").strip() if "missing required" in output_text.lower() else None)
            or "Required parameters are missing to complete this step. Could you please provide the missing values?"
        )
        action = "clarify"
        clarify_question = clar_q
        reasoning = f"Step requires operator clarification: {clar_q}"
    else:
        # Clear stale clarification state from key_facts if present
        if "key_facts" in state and isinstance(state["key_facts"], dict):
            state["key_facts"].pop("needs_clarification", None)
            state["key_facts"].pop("clarify_question", None)

        prompt = OBSERVE_PROMPT_TEMPLATE.format(
            task=state["original_task"],
            plan_overview=plan_overview,
            step_num=last_output["step_num"],
            total_steps=total_steps,
            tool=last_output["tool"],
            step_input=step_input_val,
            status_str=status_str,
            output_preview=output_text[:1200],
            key_facts_json=key_facts_json,
        )

        try:
            raw = ollama.generate(reasoning_model, prompt).strip()
            fence_m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
            raw_json = fence_m.group(1) if fence_m else None
            if not raw_json:
                brace_m = re.search(r"(\{.*\})", raw, re.DOTALL)
                raw_json = brace_m.group(1) if brace_m else None

            if raw_json:
                parsed = json.loads(raw_json)
                action = str(parsed.get("action", "continue")).strip().lower()
                reasoning = str(parsed.get("reasoning", "")).strip()
                new_steps = parsed.get("new_steps") or []
                retry_instruction = str(parsed.get("retry_instruction", "")).strip()
                clarify_question = str(parsed.get("clarify_question", "")).strip()
            else:
                raise ValueError("No valid JSON found in LLM response")
        except Exception as exc:
            _log_terminal("Observer", f"[WARN] LLM observe reasoning failed ({exc}); falling back to deterministic policy.")
            if is_error or (is_ungrounded_search and revise_count == 0):
                if revise_count < MAX_REVISIONS:
                    action = "retry"
                    reasoning = "Tool error detected; triggering self-correcting retry."
                elif state["current_step"] + 1 < len(state["plan"]):
                    action = "continue"
                    reasoning = "Step error unresolved after retries; continuing with remaining plan."
                else:
                    action = "done"
                    reasoning = "Final step completed with error."
            elif state["current_step"] + 1 < len(state["plan"]):
                action = "continue"
                reasoning = "Step succeeded; continuing to next step."
            else:
                action = "done"
                reasoning = "All plan steps completed."

    observe_decision = {
        "action": action,
        "reasoning": reasoning,
        "new_steps": new_steps,
        "retry_instruction": retry_instruction,
        "clarify_question": clarify_question,
    }

    log_observe(action, reasoning, new_steps=new_steps if action == 'replan' else None, retry_count=revise_count + 1 if action == 'retry' else None)

    if action == "clarify" and clarify_question:
        trace_entries.append({"role": "thought", "content": f"Clarification required: {clarify_question}"})
        emit_sync(
            state.get("task_id"),
            "observe",
            {"task_id": state.get("task_id"), "action": "clarify", "reasoning": reasoning, "status": "clarifying"},
        )
        return {
            "trace": trace_entries,
            "status": "clarifying",
            "observe_decision": observe_decision,
            "clarify_question": clarify_question,
        }

    if action == "replan" and replan_count < MAX_REVISIONS:
        if not new_steps:
            task_l = state["original_task"].lower()
            executed_tools = {o.get("tool") for o in state.get("step_outputs", [])}
            if any(w in task_l for w in ("poem", "poetry", "rhyme")) and "llm" not in executed_tools:
                new_steps.append({"tool": "llm", "input": "Create a poem inspired by the image analysis."})
            if any(w in task_l for w in ("python", "code", "script", "print ")) and "code" not in executed_tools:
                m = re.search(r"write (?:a )?python code to (.*)", state["original_task"], re.IGNORECASE)
                c_inp = f"Write and run a Python script to {m.group(1).strip()}" if m else f"Write and execute Python script as requested in: {state['original_task']}"
                new_steps.append({"tool": "code", "input": c_inp})
            if any(w in task_l for w in ("document", "docx", "report")) and "document" not in executed_tools:
                new_steps.append({"tool": "document", "input": f"Draft formal document for: {state['original_task']}"})
        if new_steps:
            observe_decision["new_steps"] = new_steps
            trace_entries.append({"role": "thought", "content": f"Dynamic replanning triggered: {reasoning}"})
            emit_sync(
                state.get("task_id"),
                "observe",
                {"task_id": state.get("task_id"), "action": "replan", "reasoning": reasoning, "status": "replan"},
            )
            return {
                "trace": trace_entries,
                "status": "replan",
                "observe_decision": observe_decision,
            }

    if action == "retry" or is_error:
        if revise_count < MAX_REVISIONS:
            trace_entries.append({"role": "thought", "content": f"Self-correction retry triggered: {reasoning}"})
            if retry_instruction:
                state["plan"][state["current_step"]]["input"] = retry_instruction
            emit_sync(
                state.get("task_id"),
                "observe",
                {"task_id": state.get("task_id"), "action": "retry", "reasoning": reasoning, "status": "revising"},
            )
            return {
                "trace": trace_entries,
                "plan": state["plan"],
                "status": "revising",
                "observe_decision": observe_decision,
            }
        else:
            if state["current_step"] + 1 < len(state["plan"]):
                next_step = state["current_step"] + 1
                trace_entries.append({"role": "thought", "content": f"Step retries exhausted; continuing to Step {next_step + 1}."})
                emit_sync(
                    state.get("task_id"),
                    "observe",
                    {"task_id": state.get("task_id"), "action": "continue", "reasoning": reasoning, "status": "executing"},
                )
                return {
                    "trace": trace_entries,
                    "current_step": next_step,
                    "status": "executing",
                    "revise_count": 0,
                    "observe_decision": observe_decision,
                }
            else:
                trace_entries.append({"role": "thought", "content": "Workflow terminated with error on final step."})
                emit_sync(
                    state.get("task_id"),
                    "observe",
                    {"task_id": state.get("task_id"), "action": "done", "reasoning": reasoning, "status": "failed"},
                )
                return {
                    "trace": trace_entries,
                    "status": "failed",
                    "observe_decision": observe_decision,
                }

    # Autonomous End-of-Plan Guard:
    # If the decision was "continue" or "done", but no next step exists in the plan,
    # verify whether any core goals from the user request remain unfulfilled.
    next_step = state["current_step"] + 1
    if next_step >= len(state["plan"]):
        task_l = state["original_task"].lower()
        executed_tools = {o.get("tool") for o in state.get("step_outputs", [])}
        fallback_new_steps = []
        if any(w in task_l for w in ("poem", "poetry", "rhyme")) and "llm" not in executed_tools:
            fallback_new_steps.append({"tool": "llm", "input": "Create a poem inspired by the image analysis."})
        if any(w in task_l for w in ("python", "code", "script", "print ")) and "code" not in executed_tools:
            m = re.search(r"write (?:a )?python code to (.*)", state["original_task"], re.IGNORECASE)
            c_inp = f"Write and run a Python script to {m.group(1).strip()}" if m else f"Write and execute Python script as requested in: {state['original_task']}"
            fallback_new_steps.append({"tool": "code", "input": c_inp})
        if any(w in task_l for w in ("document", "docx", "report")) and "document" not in executed_tools:
            fallback_new_steps.append({"tool": "document", "input": f"Draft formal document for: {state['original_task']}"})

        if fallback_new_steps and replan_count < MAX_REVISIONS:
            _log_terminal("Observer", f"[GUARD] Detected unfulfilled user requirements at end of plan: {[s['tool'] for s in fallback_new_steps]}. Dynamic replanning triggered.")
            replan_action = "replan"
            replan_reasoning = f"Plan reached end, but unfulfilled user tasks detected: {[s['tool'] for s in fallback_new_steps]}. Replanning missing steps."
            observe_decision["action"] = replan_action
            observe_decision["new_steps"] = fallback_new_steps
            observe_decision["reasoning"] = replan_reasoning
            trace_entries.append({"role": "thought", "content": f"Dynamic replanning triggered: {replan_reasoning}"})
            emit_sync(
                state.get("task_id"),
                "observe",
                {"task_id": state.get("task_id"), "action": replan_action, "reasoning": replan_reasoning, "status": "replan"},
            )
            return {
                "trace": trace_entries,
                "status": "replan",
                "observe_decision": observe_decision,
            }

    # Deterministic Multi-Step Guard:
    # If the LLM returns "done" but there are still unexecuted steps remaining in the Master Plan,
    # override "done" to "continue" to guarantee all planned sub-tasks run to completion.
    if action == "done":
        if next_step < len(state["plan"]):
            _log_terminal(
                "Observer",
                f"[GUARD] Overriding LLM decision 'DONE' to 'CONTINUE': {len(state['plan']) - next_step} planned step(s) remain in Master Plan.",
            )
            action = "continue"
            reasoning = f"Step {last_output['step_num']} completed; continuing with pending Step {next_step + 1}/{len(state['plan'])}."
            observe_decision["action"] = "continue"
            observe_decision["reasoning"] = reasoning
        else:
            trace_entries.append({"role": "thought", "content": f"Workflow goal satisfied or completed: {reasoning}"})
            emit_sync(
                state.get("task_id"),
                "observe",
                {"task_id": state.get("task_id"), "action": "done", "reasoning": reasoning, "status": "complete"},
            )
            return {
                "trace": trace_entries,
                "status": "complete",
                "observe_decision": observe_decision,
            }

    # Default action: continue
    if next_step < len(state["plan"]):
        trace_entries.append({"role": "thought", "content": f"Step {last_output['step_num']} done; proceeding to Step {next_step + 1}/{len(state['plan'])}."})
        emit_sync(
            state.get("task_id"),
            "observe",
            {"task_id": state.get("task_id"), "action": "continue", "reasoning": reasoning, "status": "executing"},
        )
        return {
            "trace": trace_entries,
            "current_step": next_step,
            "status": "executing",
            "revise_count": 0,
            "observe_decision": observe_decision,
        }

    trace_entries.append({"role": "thought", "content": "All planned sub-tasks completed successfully. Routing to finalize."})
    emit_sync(
        state.get("task_id"),
        "observe",
        {"task_id": state.get("task_id"), "action": "done", "reasoning": reasoning, "status": "complete"},
    )
    return {
        "trace": trace_entries,
        "status": "complete",
        "observe_decision": observe_decision,
    }


def replan_node(state: AgentState) -> dict:
    """Dynamic Replanning: Re-structures remaining steps when observe node triggers replan."""
    decision = state.get("observe_decision") or {}
    new_step_defs = decision.get("new_steps") or []
    current_idx = state["current_step"]
    current_plan = list(state["plan"])

    updated_plan = current_plan[: current_idx + 1]
    next_num = current_idx + 2
    for s in new_step_defs:
        tool_name = _normalize_tool(s.get("tool") or s.get("tool_hint", "llm"))
        inp = str(s.get("input") or s.get("instruction") or s.get("description") or s.get("task") or "").strip()
        if inp:
            updated_plan.append({
                "step_num": next_num,
                "tool": tool_name,
                "input": inp,
                "status": "pending",
            })
            next_num += 1

    # Check if any new steps were actually added
    if len(updated_plan) <= current_idx + 1:
        _log_terminal("Agent", "[REPLAN] No valid new sub-tasks could be extracted. Completing workflow.")
        thought = {
            "role": "thought",
            "content": "Dynamic Replan attempted, but no further valid sub-tasks were identified. Completing execution.",
        }
        return {
            "plan": updated_plan,
            "status": "complete",
            "trace": [thought],
        }

    replan_count = state.get("replan_count", 0) + 1
    thought = {
        "role": "thought",
        "content": f"Dynamic Replan #{replan_count}: Restructured plan to {len(updated_plan)} total steps. Reason: {decision.get('reasoning')}",
    }

    log_node_enter("replan", state.get("task_id"), f"Dynamic replanning #{replan_count}/{MAX_REVISIONS}")
    log_plan(state.get("task_id", ""), updated_plan, is_resume=False)
    log_node_exit("replan", state.get("task_id"), status="OK", summary=f"Total steps now: {len(updated_plan)}")

    log_event(
        task_id=state.get("task_id"),
        event_type="replan",
        actor="reasoner",
        summary=f"Dynamic replan executed (Count: {replan_count}). Plan updated to {len(updated_plan)} steps.",
        metadata={
            "replan_count": replan_count,
            "reasoning": decision.get("reasoning"),
            "new_plan": updated_plan,
        },
        external_calls=0,
    )

    emit_sync(
        state.get("task_id"),
        "replan",
        {
            "task_id": state.get("task_id"),
            "replan_count": replan_count,
            "reasoning": decision.get("reasoning"),
            "plan": updated_plan,
        },
    )

    return {
        "plan": updated_plan,
        "current_step": current_idx + 1,
        "status": "executing",
        "replan_count": replan_count,
        "revise_count": 0,
        "trace": [thought],
    }


def clarify_node(state: AgentState) -> dict:
    """Clarification Gate: Halts graph to request required details from the human operator."""
    decision = state.get("observe_decision") or {}
    question = decision.get("clarify_question") or "Could you please clarify your request?"

    thought = {
        "role": "thought",
        "content": f"Agent paused: Requesting clarification from operator: {question}",
    }
    observation = {
        "role": "observation",
        "content": f"Awaiting operator clarification: {question}",
    }

    log_event(
        task_id=state.get("task_id"),
        event_type="clarify",
        actor="reasoner",
        summary=f"Clarification requested: {question}",
        metadata={"question": question},
        external_calls=0,
    )

    emit_sync(
        state.get("task_id"),
        "clarify",
        {
            "task_id": state.get("task_id"),
            "question": question,
        },
    )

    return {
        "status": "clarifying",
        "clarify_question": question,
        "final_answer": question,
        "trace": [thought, observation],
        "messages": [{"role": "assistant", "content": question}],
    }


def revise_node(state: AgentState) -> dict:
    """Dynamic Failure Recovery: Adapts the failing sub-task instruction with error context."""
    idx = state["current_step"]
    step = state["plan"][idx]
    last = state["step_outputs"][-1]
    revise_count = state.get("revise_count", 0)
    tool = step["tool"]

    log_node_enter("revise", state.get("task_id"), f"Step {step['step_num']} [{tool}] (Self-Correction #{revise_count + 1})")

    thought = {
        "role": "thought",
        "content": f"Dynamically repairing Sub-Task {step['step_num']} ({tool}) (revision #{revise_count + 1}).",
    }

    if tool == "code":
        err_msg = last.get("stderr") or last.get("output") or "Execution failure"
        step["input"] = (
            f"{step['input']}\n\n"
            f"[Correction Instruction]: The previous attempt resulted in an error:\n{err_msg}\n"
            f"Fix this bug and ensure the script executes with exit_code 0."
        )
    elif tool == "search":
        step["input"] = f"{state['original_task']} (broad search)"
    elif tool == "calc":
        err_msg = last.get("output") or "Calculation failed"
        step["input"] = (
            f"{step['input']}\n\n"
            f"[Correction Instruction]: The previous attempt resulted in an error:\n{err_msg}\n"
            f"Provide a valid Python arithmetic expression and exact numeric values from context without equals signs or variable assignments."
        )
    else:
        step["input"] = f"{step['input']} (retry attempt)"

    log_event(
        task_id=state.get("task_id"),
        event_type="revise",
        actor="agent_loop",
        summary=f"Dynamically revised Sub-Task {step['step_num']} input for {tool}.",
        metadata={
            "step_num": step["step_num"],
            "tool": tool,
            "revision": revise_count + 1,
            "new_input": step["input"],
        },
        external_calls=0,
    )

    emit_sync(
        state.get("task_id"),
        "revise",
        {
            "task_id": state.get("task_id"),
            "step_num": step["step_num"],
            "tool": tool,
            "revision": revise_count + 1,
            "new_input": step["input"],
        },
    )

    return {
        "plan": state["plan"],
        "status": "executing",
        "revise_count": revise_count + 1,
        "trace": [thought],
    }


def finalize_node(state: AgentState) -> dict:
    model = registry.get_model("reasoning")
    failed = state["status"] == "failed"
    awaiting_approval = state["status"] == "awaiting_approval"

    if awaiting_approval:
        last = state["step_outputs"][-1]
        final_answer = (
            f"Draft document '{last.get('title', 'Document')}' has been prepared and paused for human review.\n\n"
            f"Risk Level: {str(last.get('risk', 'medium')).capitalize()}\n"
            f"Confidence: {float(last.get('confidence', 0.5)) * 100:.0f}%\n"
            f"Reasoning: {last.get('reasoning', '')}\n\n"
            f"Please approve, edit, or reject the draft to proceed with final file delivery."
        )
        thought = {"role": "thought", "content": "Document draft prepared; awaiting human approval."}
        observation = {"role": "observation", "content": f"Final answer: {final_answer[:300]}"}
        log_event(
            task_id=state.get("task_id"),
            event_type="complete",
            actor=model,
            summary=f"Task paused awaiting human approval for '{last.get('title')}'.",
            metadata={"status": "awaiting_approval", "risk": last.get("risk")},
            external_calls=0,
        )
        emit_sync(
            state.get("task_id"),
            "final",
            {
                "task_id": state.get("task_id"),
                "status": "awaiting_approval",
                "final_answer": final_answer,
            },
        )
        return {
            "trace": [thought, observation],
            "status": "awaiting_approval",
            "final_answer": final_answer,
            "messages": [{"role": "assistant", "content": final_answer}],
        }

    # Deduplicate step outputs so only the latest attempt per step number is used in summary
    latest_outputs_by_step: Dict[int, dict] = {}
    for o in state.get("step_outputs", []):
        latest_outputs_by_step[o["step_num"]] = o
    deduped_outputs = list(latest_outputs_by_step.values())

    outputs_summary = "\n\n".join(
        f"Sub-Task {o['step_num']} ({o['tool']}): {o['output']}" for o in deduped_outputs
    )

    if len(deduped_outputs) == 1 and deduped_outputs[0]["tool"] in ("search", "document", "calc") and not deduped_outputs[0].get("error"):
        final_answer = deduped_outputs[0]["output"]
        thought = {"role": "thought", "content": "Sub-task completed directly with verified tool output."}
    else:
        history_section = ""
        if state.get("history_context"):
            history_section = f"{state['history_context']}\n"

        prompt = (
            f"{history_section}User's Original Request: {state['original_task']}\n\n"
            f"Sub-tasks executed and results:\n{outputs_summary}\n\n"
            + ("Note: not all steps succeeded; acknowledge this and answer as best as possible.\n\n" if failed else "")
            + "Write a clear, concise, professional final answer for the operator addressing the request."
        )

        thought = {"role": "thought", "content": "Synthesizing cohesive final answer from all sub-task results."}
        t_synth = time.perf_counter()
        log_node_enter("finalizer", state.get("task_id"), f"Synthesizing final answer with model '{model}'")
        try:
            final_answer = ollama.generate(model, prompt)
            if not final_answer.strip():
                _log_terminal("Finalizer", f"[WARN] Model '{model}' returned empty synthesis. Falling back to step output summary.")
                final_answer = f"Task completed. Here is a summary of what was done:\n\n{outputs_summary}"
        except Exception as exc:
            _log_terminal("Finalizer", f"[ERROR] Synthesis LLM call failed: {exc}. Using step output summary as answer.")
            final_answer = f"Task completed. Here is a summary of what was done:\n\n{outputs_summary}"
        log_node_exit("finalizer", state.get("task_id"), status="OK", elapsed_s=time.perf_counter() - t_synth)

    observation = {"role": "observation", "content": f"Final answer: {final_answer[:300]}"}

    if failed:
        log_event(
            task_id=state.get("task_id"),
            event_type="error",
            actor=model,
            summary="Task completed with failure status.",
            metadata={"status": "failed", "final_answer_preview": final_answer[:300]},
            external_calls=0,
        )
    else:
        log_event(
            task_id=state.get("task_id"),
            event_type="complete",
            actor=model,
            summary="Task completed successfully.",
            metadata={"status": "complete", "final_answer_preview": final_answer[:300]},
            external_calls=0,
        )

    emit_sync(
        state.get("task_id"),
        "final",
        {
            "task_id": state.get("task_id"),
            "status": "failed" if failed else "complete",
            "final_answer": final_answer,
        },
    )

    return {
        "trace": [thought, observation],
        "status": "failed" if failed else "complete",
        "final_answer": final_answer,
        "messages": [{"role": "user", "content": state["original_task"]}, {"role": "assistant", "content": final_answer}],
    }


def route_after_observe(state: AgentState) -> str:
    return state["status"]


def route_after_replan(state: AgentState) -> str:
    return "route_subtask" if state.get("status") == "executing" else "finalize"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("master_plan", master_plan_node)
    graph.add_node("route_subtask", route_subtask_node)
    graph.add_node("execute", execute_node)
    graph.add_node("observe", observe_node)
    graph.add_node("replan", replan_node)
    graph.add_node("clarify", clarify_node)
    graph.add_node("revise", revise_node)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("master_plan")
    graph.add_edge("master_plan", "route_subtask")
    graph.add_edge("route_subtask", "execute")
    graph.add_edge("execute", "observe")
    graph.add_conditional_edges(
        "observe",
        route_after_observe,
        {
            "executing": "route_subtask",
            "replan": "replan",
            "revising": "revise",
            "clarifying": "clarify",
            "complete": "finalize",
            "failed": "finalize",
            "awaiting_approval": "finalize",
        },
    )
    graph.add_conditional_edges(
        "replan",
        route_after_replan,
        {
            "route_subtask": "route_subtask",
            "finalize": "finalize",
        },
    )
    graph.add_edge("clarify", END)
    graph.add_edge("revise", "execute")
    graph.add_edge("finalize", END)
    return graph.compile()



_COMPILED_GRAPH = build_graph()


def run_agent(
    task: str,
    attachment_type: Optional[str] = None,
    task_id: Optional[str] = None,
    history: Optional[List[dict]] = None,
    initial_key_facts: Optional[Dict[str, Any]] = None,
    resume_state: Optional[AgentState] = None,
) -> dict:
    if not task_id:
        task_id = str(uuid.uuid4())

    t_agent_start = time.perf_counter()
    log_graph_start(task_id, task, history_len=len(history or []), facts_count=len(initial_key_facts or {}))

    history_ctx = _format_history(history)

    if resume_state:
        initial_state = dict(resume_state)
        initial_state["task_id"] = task_id
        initial_state["resumed"] = True
        initial_state["status"] = "executing"
        initial_state["clarify_question"] = None
        if "key_facts" in initial_state and isinstance(initial_state["key_facts"], dict):
            initial_state["key_facts"] = dict(initial_state["key_facts"])
            initial_state["key_facts"].pop("needs_clarification", None)
            initial_state["key_facts"].pop("clarify_question", None)
        if task:
            initial_state["operator_reply"] = task
            initial_state["original_task"] = f"{resume_state.get('original_task', '')}\n[Clarification]: {task}".strip()
    else:
        initial_state: AgentState = {
            "task_id": task_id,
            "original_task": task,
            "attachment_type": attachment_type,
            "routing_decision": None,
            "plan": [],
            "current_step": 0,
            "step_outputs": [],
            "messages": [],
            "status": "planning",
            "trace": [
                {
                    "role": "thought",
                    "content": f"Master Planner activated for request: {task[:100]}",
                }
            ],
            "revise_count": 0,
            "replan_count": 0,
            "final_answer": None,
            "history_context": history_ctx,
            "shared_memory": "",
            "key_facts": dict(initial_key_facts or {}),
            "observe_decision": None,
            "clarify_question": None,
        }

    final_state = _COMPILED_GRAPH.invoke(initial_state, config={"recursion_limit": 60})

    primary_role = (
        final_state.get("routing_decision", {}).get("model_role")
        if final_state.get("routing_decision")
        else "reasoning"
    )
    model_used = registry.get_model(primary_role)

    sources_used: List[dict] = []
    generated_files: List[dict] = []
    raw_code_runs: List[dict] = []
    approval_info = None
    draft_content = None

    for step_output in final_state.get("step_outputs", []):
        if "sources" in step_output and step_output["sources"]:
            sources_used.extend(step_output["sources"])
        if step_output.get("awaiting_approval"):
            approval_info = {
                "risk": step_output.get("risk"),
                "confidence": step_output.get("confidence"),
                "reasoning": step_output.get("reasoning"),
            }
            draft_content = step_output.get("draft_content")
        if "file_path" in step_output and not step_output.get("awaiting_approval"):
            generated_files.append({
                "filename": step_output.get("filename"),
                "file_path": step_output.get("file_path"),
                "title": step_output.get("title"),
                "grounded": step_output.get("grounded", True),
                "sources": step_output.get("sources", []),
            })
        if step_output.get("tool") == "code":
            raw_code_runs.append({
                "step_num": step_output["step_num"],
                "language": step_output.get("language", "python"),
                "code": step_output.get("code"),
                "stdout": step_output.get("stdout"),
                "stderr": step_output.get("stderr"),
                "exit_code": step_output.get("exit_code"),
                "timed_out": step_output.get("timed_out"),
                "duration_seconds": step_output.get("duration_seconds", 0.0),
                "error": step_output.get("error"),
            })

    # Consolidate code runs per sub-task: present the latest run as primary,
    # with prior attempts embedded as revisions so the frontend doesn't stack multiple redundant cards.
    runs_by_step: Dict[int, List[dict]] = {}
    for r in raw_code_runs:
        runs_by_step.setdefault(r.get("step_num", 1), []).append(r)

    code_runs: List[dict] = []
    for s_num, runs in runs_by_step.items():
        latest = dict(runs[-1])
        latest["attempt_count"] = len(runs)
        if len(runs) > 1:
            latest["revisions"] = runs[:-1]
        code_runs.append(latest)

    routing_decision = final_state.get("routing_decision") or {
        "task_type": "general",
        "model_role": "reasoning",
        "tools_needed": [],
        "reason": "Master planner orchestrator",
    }

    # Collect distinct models engaged across steps in execution order:
    models_used: List[str] = []
    for step in final_state.get("plan", []):
        m = step.get("model")
        if m and m not in models_used and not m.endswith("_tool") and m != "vault_search":
            models_used.append(m)
    for so in final_state.get("step_outputs", []):
        m = so.get("model")
        if m and m not in models_used and not m.endswith("_tool") and m != "vault_search":
            models_used.append(m)
    if model_used and model_used not in models_used:
        models_used.append(model_used)

    total_agent_elapsed = time.perf_counter() - t_agent_start
    log_graph_complete(task_id, final_state.get("status", "complete"), models_used, elapsed_s=total_agent_elapsed)

    result_payload = {
        "task_id": task_id,
        "task": task,
        "routing_decision": routing_decision,
        "plan": final_state.get("plan", []),
        "trace": final_state.get("trace", []),
        "step_outputs": final_state.get("step_outputs", []),
        "result": final_state.get("final_answer"),
        "sources": sources_used,
        "generated_files": generated_files,
        "code_runs": code_runs,
        "status": final_state.get("status"),
        "model_used": model_used,
        "models_used": models_used,
        "key_facts": final_state.get("key_facts", {}),
        "clarify_question": final_state.get("clarify_question"),
        "observe_decision": final_state.get("observe_decision"),
        "state_snapshot": final_state,
    }
    if approval_info:
        result_payload["approval"] = approval_info
        result_payload["draft_content"] = draft_content

    return result_payload



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

import json
import logging
from pathlib import Path
import re
from typing import List, Optional, Tuple
import uuid

from langgraph.graph import END, StateGraph

from backend.audit.logbook import log_event
from backend.brain.router import route
from backend.brain.state import AgentState
from backend.engine import ollama, registry
from backend.guard.approve import assess_risk, request_approval
from backend.tools.calc import calculate as calc_tool
from backend.tools.code import write_and_run as code_tool_run
from backend.tools.ocr import extract_text as ocr_tool_extract
from backend.tools.search import search as search_tool
from backend.tools.vision import describe_image as vision_tool_describe
from backend.tools.writer import draft_document, render_docx, write_document as writer_tool

logger = logging.getLogger("kavach.agent")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

MAX_TOTAL_STEPS = 5
MAX_REVISIONS = 2
ERROR_TRIGGER = "simulate_error"
CODE_TIMEOUT_SECONDS = 15
MAX_HISTORY_TURNS = 8
MAX_HISTORY_CHARS_PER_MSG = 400

VALID_TOOLS = {"llm", "search", "calc", "vision", "document", "code", "ocr"}

PLAN_PROMPT_TEMPLATE = """You are the planning module of an AI agent. Break the task below into the MINIMUM number of ordered steps required to complete it.

CRITICAL EFFICIENCY RULE:
Use the fewest steps possible. Do not create more than 3 steps unless the task genuinely requires multiple distinct tool calls (e.g. search AND then draft). A simple question or search needs 1 step, not 6. Do NOT create redundant "llm" steps.

Each step must be an object with:
  "step": <integer, starting at 1>
  "tool": one of ["llm", "search", "calc", "vision", "document", "code", "ocr"]
  "input": a short instruction/query for that tool

Tool Selection Rules:
- "search": for looking up SOPs, procedures, or facts in the Knowledge Vault. A search question needs ONLY 1 search step.
- "document": for drafting formal Word document (.docx) reports. Typically step 1 is "search" (if SOP context is needed) and step 2 is "document".
- "calc": for numerical math, formulas, or engineering calculations with step-by-step arithmetic.
- "code": for generating and running Python scripts in the secure sandbox.
- "ocr": for reading text from image/scanned document files.
- "vision": for analyzing engineering drawings, diagrams, or gauges.
- "llm": ONLY for general reasoning or direct questions where no specific tool is needed.

{history_section}Task: {task}
Task type: {task_type}{failure_context}

Respond with ONLY a raw JSON array of step objects. Max 3 steps (unless revising). No prose, no markdown fences, no explanation.
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


def _parse_plan(
    raw: str,
    fallback_input: str,
    task_type: Optional[str] = None,
    is_revision: bool = False,
) -> List[dict]:
    """Robustly parse the planner's JSON, enforcing minimum steps and soft ceilings."""
    text = (raw or "").strip()

    fence_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        bracket_match = re.search(r"(\[.*\])", text, re.DOTALL)
        if bracket_match:
            text = bracket_match.group(1)

    # Soft ceiling: max 3 steps for document/search tasks unless revising
    max_steps = 3 if (task_type in {"document", "search"} and not is_revision) else 6

    parsed_steps: List[dict] = []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            for item in parsed[:max_steps]:
                if not isinstance(item, dict):
                    continue
                tool = _normalize_tool(item.get("tool", "llm"))
                step_input = str(item.get("input", fallback_input))
                parsed_steps.append({"tool": tool, "input": step_input})
    except (json.JSONDecodeError, TypeError):
        parsed_steps = []

    # Sanity checks:
    # 1. Collapse consecutive duplicate "llm" steps
    collapsed: List[dict] = []
    for s in parsed_steps:
        if collapsed and s["tool"] == "llm" and collapsed[-1]["tool"] == "llm":
            continue
        collapsed.append(s)

    # 2. Task-type integrity
    if task_type == "search":
        for s in collapsed:
            if s["tool"] == "document":
                s["tool"] = "search"
    elif task_type == "document" and collapsed:
        if not any(s["tool"] == "document" for s in collapsed):
            collapsed[-1]["tool"] = "document"
    elif task_type == "vision" and collapsed:
        if not any(s["tool"] == "vision" for s in collapsed):
            collapsed[0]["tool"] = "vision"

    # 3. If empty, fallback to single step
    if not collapsed:
        fallback_tool = (
            "document"
            if task_type == "document"
            else ("search" if task_type == "search" else ("vision" if task_type == "vision" else "llm"))
        )
        collapsed = [{"tool": fallback_tool, "input": fallback_input}]

    # Format numbered steps
    steps: List[dict] = []
    for i, s in enumerate(collapsed[:max_steps]):
        steps.append({
            "step_num": i + 1,
            "tool": s["tool"],
            "input": s["input"],
            "status": "pending",
        })

    return steps


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

def plan_node(state: AgentState) -> dict:
    is_revision = state["status"] == "revising"
    revise_count = state.get("revise_count", 0)
    reasoning_model = registry.get_model("reasoning")

    failure_context = ""
    if is_revision and state["step_outputs"]:
        last = state["step_outputs"][-1]
        if last["tool"] == "code":
            guidance = (
                "The code failed to run. Revise the plan to include a 'code' step that "
                "regenerates and re-runs a corrected script accomplishing the same task."
            )
        elif last["tool"] == "search":
            if state["routing_decision"].get("task_type") == "document":
                guidance = "Revise the plan to either use broader search keywords or proceed to document the missing documentation."
            else:
                guidance = "Revise the plan to use broader or alternative search keywords to answer the query directly."
        elif last["tool"] == "calc":
            guidance = "The calculation failed or had missing inputs. Revise the plan to search/extract the missing values first."
        else:
            guidance = "Revise the plan to work around this failure."
        failure_context = (
            f"\n\nIMPORTANT: A previous attempt at step {last['step_num']} "
            f"(tool: {last['tool']}) reported: {last['output']}\n"
            f"{guidance}"
        )

    history_section = ""
    if state.get("history_context"):
        history_section = f"{state['history_context']}\n"

    prompt = PLAN_PROMPT_TEMPLATE.format(
        history_section=history_section,
        task=state["original_task"],
        task_type=state["routing_decision"]["task_type"],
        failure_context=failure_context,
    )


    thought = {
        "role": "thought",
        "content": (
            f"Re-planning after observation (revision #{revise_count + 1})."
            if is_revision
            else "Planning steps for task."
        ),
    }

    try:
        raw = ollama.generate(reasoning_model, prompt)
    except Exception as exc:  # noqa: BLE001 - surfaced into the plan fallback
        raw = ""
        thought = {"role": "thought", "content": f"Planning LLM call failed ({exc}); using single-step fallback plan."}

    steps = _parse_plan(
        raw,
        fallback_input=state["original_task"],
        task_type=state["routing_decision"].get("task_type"),
        is_revision=is_revision,
    )
    action = {"role": "action", "content": f"Generated plan: {json.dumps(steps)}"}

    log_event(
        task_id=state.get("task_id"),
        event_type="plan",
        actor=reasoning_model,
        summary=f"{'Re-planned' if is_revision else 'Generated plan'} with {len(steps)} steps",
        metadata={
            "task": state.get("original_task"),
            "model": reasoning_model,
            "is_revision": is_revision,
            "revise_count": revise_count,
            "steps": steps,
        },
        external_calls=0,
    )

    update = {
        "plan": steps,
        "current_step": 0,
        "status": "executing",
        "trace": [thought, action],
        "messages": [
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": raw},
        ],
    }
    if is_revision:
        update["revise_count"] = revise_count + 1
    return update


def execute_node(state: AgentState) -> dict:
    idx = state["current_step"]
    step = state["plan"][idx]
    tool = step["tool"]
    step_input = step["input"]

    thought = {"role": "thought", "content": f"Executing step {step['step_num']}: tool='{tool}', input={step_input!r}"}
    action = {"role": "action", "content": f"CALL {tool}({step_input!r})"}
    messages_update: List[dict] = []
    doc_meta: dict = {}
    code_meta: dict = {}
    extra_meta: dict = {}
    is_grounded_flag = True

    if tool == "llm":
        role = state["routing_decision"]["model_role"]
        model = registry.get_model(role)
        actor = model
        llm_prompt = step_input
        if state.get("history_context"):
            llm_prompt = f"{state['history_context']}\nUser query: {step_input}"
        try:
            output = ollama.generate(model, llm_prompt)
            is_error = False
        except Exception as exc:  # noqa: BLE001 - becomes an observed [error]
            output = f"[error] llm call failed: {exc}"
            is_error = True
        messages_update = [
            {"role": "user", "content": step_input},
            {"role": "assistant", "content": output},
        ]
        sources = None
    elif tool == "search":
        actor = "vault_search"
        result = search_tool(step_input, task_id=state.get("task_id"))
        answer = result["answer"]
        sources = result.get("sources", [])
        is_grounded_flag = result.get("grounded", True)
        if sources:
            filenames = ", ".join(sorted({s["filename"] for s in sources}))
            output = f"{answer}\n\n[Sources: {filenames}]"
        else:
            output = answer
        is_error = False
    elif tool == "calc":
        actor = "calc_tool"
        sources = None
        prior_context_list = [o["output"] for o in state["step_outputs"]]
        context_str = "\n".join(prior_context_list) if prior_context_list else None
        calc_res = calc_tool(step_input, context=context_str, task_id=state.get("task_id"))
        if calc_res.get("success"):
            output = f"Calculation '{calc_res['formula_name']}':\n" + "\n".join(calc_res.get("steps", []))
            is_error = False
        else:
            output = f"[error] {calc_res.get('error', 'Calculation failed')}"
            is_error = True
        extra_meta = {
            "calc_result": calc_res.get("result"),
            "formula_name": calc_res.get("formula_name"),
            "unit": calc_res.get("unit"),
        }
    elif tool == "ocr":
        actor = "ocr_tool"
        sources = None
        try:
            ocr_res = ocr_tool_extract(step_input.strip(), task_id=state.get("task_id"))
            output = f"OCR Extracted Text (Engine: {ocr_res['engine']}, Confidence: {ocr_res['confidence']:.2f}):\n{ocr_res['text']}"
            is_error = False
            actor = ocr_res["engine"]
            extra_meta = {
                "engine": ocr_res["engine"],
                "confidence": ocr_res["confidence"],
                "low_confidence": ocr_res["low_confidence"],
            }
        except Exception as exc:
            output = f"[error] OCR extraction failed: {exc}"
            is_error = True
    elif tool == "vision":
        actor = registry.get_model("vision")
        sources = None
        try:
            raw_input = step_input.strip()
            target_str = raw_input
            q_target = None
            if "|" in raw_input:
                parts = raw_input.split("|", 1)
                target_str = parts[0].strip()
                q_target = parts[1].strip()

            # Check if target_str is already a path or if we need to extract from text/task
            img_path_to_use = target_str
            img_pattern = r"([A-Za-z]:\\[^\r\n<>:\"|?*]+\.(?:png|jpg|jpeg|bmp|tiff|webp)|\S+\.(?:png|jpg|jpeg|bmp|tiff|webp))"
            
            # If target_str doesn't exist directly, search in target_str or original_task
            try:
                from backend.tools.vision import _resolve_image_path
                img_path_to_use = str(_resolve_image_path(target_str))
            except Exception:
                # Look for an image filename / path match in raw_input
                m = re.search(img_pattern, raw_input, re.IGNORECASE)
                if m:
                    img_path_to_use = m.group(1).strip()
                    if not q_target:
                        q_target = raw_input.replace(m.group(0), "").replace("Attached file:", "").strip() or None
                else:
                    # Look in original_task
                    m_orig = re.search(img_pattern, state.get("original_task", ""), re.IGNORECASE)
                    if m_orig:
                        img_path_to_use = m_orig.group(1).strip()
                        if not q_target:
                            q_target = raw_input.replace("Attached file:", "").strip() or None

            logger.info(f"[AGENT] Invoking vision tool with image={img_path_to_use}, question={q_target}")
            vis_res = vision_tool_describe(img_path_to_use, question=q_target, task_id=state.get("task_id"))
            output = vis_res["description"]
            is_error = False
            extra_meta = {"image_path": vis_res["image_path"], "question": q_target}
        except Exception as exc:
            logger.error(f"[AGENT] Vision tool failed: {exc}")
            output = f"[error] Vision analysis failed: {exc}"
            is_error = True
    elif tool == "code":
        actor = registry.get_model("code")
        sources = None

        prior_error = None
        for prev in reversed(state["step_outputs"]):
            if prev.get("tool") == "code" and prev.get("error"):
                prior_error = prev.get("stderr") or prev.get("output")
                break

        code_result = code_tool_run(
            step_input,
            prior_error=prior_error,
            timeout_seconds=CODE_TIMEOUT_SECONDS,
            task_id=state.get("task_id"),
        )
        is_error = not code_result["success"]
        if is_error:
            output = (
                f"[error] code execution failed (exit_code={code_result['exit_code']}, "
                f"timed_out={code_result['timed_out']}).\nstderr:\n{code_result['stderr']}"
            )
        else:
            output = f"Code executed successfully (exit_code=0).\nstdout:\n{code_result['stdout']}"

        code_meta = {
            "language": code_result.get("language", "python"),
            "code": code_result["code"],
            "stdout": code_result["stdout"],
            "stderr": code_result["stderr"],
            "exit_code": code_result["exit_code"],
            "timed_out": code_result["timed_out"],
            "duration_seconds": code_result.get("duration_seconds", 0.0),
        }
    elif tool == "document":
        actor = "writer"
        prior_sources: List[dict] = []
        has_search = False
        has_grounded_search = False
        last_search_grounded = None

        for prev_out in state["step_outputs"]:
            if prev_out.get("tool") == "search":
                has_search = True
                if prev_out.get("grounded", False):
                    has_grounded_search = True
                    last_search_grounded = True
                    if "sources" in prev_out and prev_out["sources"]:
                        existing_fns = {s["filename"] for s in prior_sources if "filename" in s}
                        for s in prev_out["sources"]:
                            if s.get("filename") not in existing_fns:
                                prior_sources.append(s)
                                existing_fns.add(s.get("filename"))
                else:
                    last_search_grounded = False

        if has_grounded_search:
            is_doc_grounded = True
        elif has_search:
            is_doc_grounded = bool(last_search_grounded)
        else:
            is_doc_grounded = True

        try:
            # Produce structured JSON draft first
            structured = draft_document(
                step_input,
                sources=prior_sources if is_doc_grounded else [],
                is_grounded=is_doc_grounded,
            )
            title = structured.get("title", "Technical Document")
            sections_list = structured.get("sections", [])
            sources = structured.get("sources", [])

            # Assess risk using Phase 11 heuristic
            risk_info = assess_risk(
                task_type="document",
                document_content=structured,
                sources_used=prior_sources if is_doc_grounded else [],
            )

            # Check if approval is required (medium or high risk)
            if risk_info.get("risk") in {"medium", "high"}:
                task_id = state.get("task_id") or str(uuid.uuid4())
                request_approval(
                    task_id=task_id,
                    document_content=structured,
                    risk_assessment=risk_info,
                    sources=prior_sources if is_doc_grounded else [],
                )
                output = (
                    f"Drafted document '{title}' (Risk: {risk_info['risk'].upper()}, "
                    f"Confidence: {risk_info['confidence'] * 100:.0f}%).\n"
                    f"Reasoning: {risk_info['reasoning']}\n"
                    f"Sections: {', '.join(s.get('heading', '') for s in sections_list)}\n"
                    f"Status: PAUSED for human approval before rendering final .docx."
                )
                is_error = False
                doc_meta = {
                    "title": title,
                    "grounded": is_doc_grounded,
                    "awaiting_approval": True,
                    "risk": risk_info["risk"],
                    "confidence": risk_info["confidence"],
                    "reasoning": risk_info["reasoning"],
                    "draft_content": structured,
                }
            else:
                # Low risk document: render docx immediately
                file_path = render_docx(structured)
                output = (
                    f"Generated document '{title}' saved to {file_path.name}.\n"
                    f"File path: {file_path}\n"
                    f"Grounded in SOPs: {is_doc_grounded}\n"
                    f"Sections: {', '.join(s.get('heading', '') for s in sections_list)}"
                )
                is_error = False
                doc_meta = {
                    "file_path": str(file_path),
                    "filename": file_path.name,
                    "title": title,
                    "grounded": is_doc_grounded,
                    "awaiting_approval": False,
                }
        except Exception as exc:  # noqa: BLE001
            output = f"[error] document generation failed: {exc}"
            is_error = True
            sources = None
    else:
        actor = tool
        sources = None
        output, is_error = _run_stub_tool(tool, step_input, state["original_task"], state.get("revise_count", 0))

    step_output = {
        "step_num": step["step_num"],
        "tool": tool,
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

    observation = {"role": "observation", "content": f"Result: {output[:300]}"}

    log_event(
        task_id=state.get("task_id"),
        event_type="step",
        actor=actor,
        summary=f"Step {step['step_num']} ({tool}): {'ERROR' if is_error else 'OK'} - {output[:100]}",
        metadata={
            "task": state.get("original_task"),
            "step_num": step["step_num"],
            "tool": tool,
            "model": actor,
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

    return {
        "step_outputs": [step_output],
        "trace": [thought, action, observation],
        "messages": messages_update,
    }


def observe_node(state: AgentState) -> dict:
    last_output = state["step_outputs"][-1]
    total_executed = len(state["step_outputs"])
    is_error = last_output.get("error", False)
    is_ungrounded_search = (last_output.get("tool") == "search") and not last_output.get("grounded", True)

    trace_entries = [
        {
            "role": "observation",
            "content": f"Step {last_output['step_num']} ({last_output['tool']}) -> "
            f"{'ERROR' if is_error else ('UNGROUNDED' if is_ungrounded_search else 'OK')}: {last_output['output'][:200]}",
        }
    ]

    # Check for approval gate pause
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
        return {"trace": trace_entries, "status": "awaiting_approval"}

    if total_executed >= MAX_TOTAL_STEPS:
        status = "failed" if is_error else "complete"
        trace_entries.append(
            {"role": "thought", "content": f"Hard cap of {MAX_TOTAL_STEPS} steps reached. Forcing finish."}
        )
        log_event(
            task_id=state.get("task_id"),
            event_type="observe",
            actor="agent_loop",
            summary=f"Hard cap of {MAX_TOTAL_STEPS} steps reached. Forcing finish.",
            metadata={"decision": "finish", "status": status, "total_executed": total_executed},
            external_calls=0,
        )
        return {"trace": trace_entries, "status": status}

    if is_error:
        if state.get("revise_count", 0) >= MAX_REVISIONS:
            trace_entries.append(
                {"role": "thought", "content": "Max revisions reached; giving up on repair, finishing with failure."}
            )
            log_event(
                task_id=state.get("task_id"),
                event_type="observe",
                actor="agent_loop",
                summary="Max revisions reached. Terminating with failure.",
                metadata={"decision": "failed", "revise_count": state.get("revise_count", 0)},
                external_calls=0,
            )
            return {"trace": trace_entries, "status": "failed"}

        trace_entries.append(
            {"role": "thought", "content": "Error detected in last step. Self-correcting: routing to REVISE (re-plan)."}
        )
        log_event(
            task_id=state.get("task_id"),
            event_type="observe",
            actor="agent_loop",
            summary=f"Error detected in step {last_output['step_num']}. Self-correcting: routing to REVISE (re-plan).",
            metadata={"decision": "revise", "failed_step": last_output["step_num"], "error_message": last_output["output"]},
            external_calls=0,
        )
        return {"trace": trace_entries, "status": "revising"}

    if is_ungrounded_search and state.get("revise_count", 0) == 0:
        trace_entries.append(
            {"role": "thought", "content": "Search did not find grounded SOP information. Self-correcting: routing to REVISE to try broader search."}
        )
        log_event(
            task_id=state.get("task_id"),
            event_type="observe",
            actor="agent_loop",
            summary=f"Search ungrounded in step {last_output['step_num']}. Routing to REVISE.",
            metadata={"decision": "revise", "failed_step": last_output["step_num"], "reason": "ungrounded_search"},
            external_calls=0,
        )
        return {"trace": trace_entries, "status": "revising"}

    next_step = state["current_step"] + 1
    if next_step >= len(state["plan"]):
        trace_entries.append({"role": "thought", "content": "All planned steps completed successfully."})
        log_event(
            task_id=state.get("task_id"),
            event_type="observe",
            actor="agent_loop",
            summary="All planned steps completed successfully. Routing to finalize.",
            metadata={"decision": "complete", "completed_steps": len(state["plan"])},
            external_calls=0,
        )
        return {"trace": trace_entries, "status": "complete"}

    trace_entries.append({"role": "thought", "content": f"Proceeding to step {next_step + 1}."})
    log_event(
        task_id=state.get("task_id"),
        event_type="observe",
        actor="agent_loop",
        summary=f"Step {last_output['step_num']} completed. Proceeding to step {next_step + 1}.",
        metadata={"decision": "continue", "next_step": next_step + 1},
        external_calls=0,
    )
    return {"trace": trace_entries, "current_step": next_step, "status": "executing"}


def finalize_node(state: AgentState) -> dict:
    role = state["routing_decision"]["model_role"]
    model = registry.get_model(role)
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
        return {
            "trace": [thought, observation],
            "status": "awaiting_approval",
            "final_answer": final_answer,
            "messages": [{"role": "assistant", "content": final_answer}],
        }

    outputs_summary = "\n".join(
        f"Step {o['step_num']} ({o['tool']}): {o['output']}" for o in state["step_outputs"]
    )
    history_section = ""
    if state.get("history_context"):
        history_section = f"{state['history_context']}\n"

    prompt = (
        f"{history_section}Current Task: {state['original_task']}\n\n"
        f"Steps executed and their results:\n{outputs_summary}\n\n"
        + ("Note: not all steps succeeded; acknowledge this and answer as best as possible.\n\n" if failed else "")
        + "Write a clear, concise final answer for the user based on the above."
    )

    thought = {"role": "thought", "content": "Synthesizing final answer from step outputs."}
    try:
        final_answer = ollama.generate(model, prompt)
    except Exception as exc:  # noqa: BLE001
        final_answer = f"[error] Could not synthesize final answer: {exc}"

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

    return {
        "trace": [thought, observation],
        "status": "failed" if failed else "complete",
        "final_answer": final_answer,
        "messages": [{"role": "user", "content": prompt}, {"role": "assistant", "content": final_answer}],
    }


def route_after_observe(state: AgentState) -> str:
    return state["status"]


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_node)
    graph.add_node("observe", observe_node)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("plan")
    graph.add_edge("plan", "execute")
    graph.add_edge("execute", "observe")
    graph.add_conditional_edges(
        "observe",
        route_after_observe,
        {
            "executing": "execute",
            "revising": "plan",
            "complete": "finalize",
            "failed": "finalize",
            "awaiting_approval": "finalize",
        },
    )
    graph.add_edge("finalize", END)
    return graph.compile()


_COMPILED_GRAPH = build_graph()


def run_agent(
    task: str,
    attachment_type: Optional[str] = None,
    task_id: Optional[str] = None,
    history: Optional[List[dict]] = None,
) -> dict:
    if not task_id:
        task_id = str(uuid.uuid4())

    history_ctx = _format_history(history)

    has_img_signal = bool(
        attachment_type in ("image", "photo", "picture", "file")
        or any(ext in (task or "").lower() for ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"))
    )
    logger.info(f"[ROUTER] Message has attachment: {has_img_signal} (attachment_type={attachment_type})")

    routing_decision = route(task, attachment_type=attachment_type)
    model_role = routing_decision.model_role
    model_tag = registry.get_model(model_role)

    logger.info(f"[ROUTER] Selected task_type='{routing_decision.task_type}', model_role='{model_role}' ({model_tag})")
    if has_img_signal and routing_decision.task_type != "vision":
        logger.warning(f"[ROUTER] MISROUTE - image detected but routed to {routing_decision.task_type}")

    log_event(
        task_id=task_id,
        event_type="route",
        actor="router",
        summary=f"Routed to task_type='{routing_decision.task_type}', model_role='{model_role}' ({model_tag})",
        metadata={
            "task": task,
            "task_type": routing_decision.task_type,
            "model_role": model_role,
            "model_tag": model_tag,
            "tools_needed": routing_decision.tools_needed,
            "reason": routing_decision.reason,
        },
        external_calls=0,
    )

    initial_state: AgentState = {
        "task_id": task_id,
        "original_task": task,
        "routing_decision": routing_decision.model_dump(),
        "plan": [],
        "current_step": 0,
        "step_outputs": [],
        "messages": [],
        "status": "planning",
        "trace": [
            {
                "role": "thought",
                "content": (
                    f"Routed to task_type='{routing_decision.task_type}', "
                    f"model_role='{routing_decision.model_role}'. Reason: {routing_decision.reason}"
                ),
            }
        ],
        "revise_count": 0,
        "final_answer": None,
        "history_context": history_ctx,
    }


    final_state = _COMPILED_GRAPH.invoke(initial_state, config={"recursion_limit": 60})

    model_used = registry.get_model(final_state["routing_decision"]["model_role"])

    sources_used: List[dict] = []
    generated_files: List[dict] = []
    code_runs: List[dict] = []
    approval_info = None
    draft_content = None

    for step_output in final_state["step_outputs"]:
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
            code_runs.append({
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

    result_payload = {
        "task_id": task_id,
        "task": task,
        "routing_decision": final_state["routing_decision"],
        "plan": final_state["plan"],
        "trace": final_state["trace"],
        "step_outputs": final_state["step_outputs"],
        "result": final_state["final_answer"],
        "sources": sources_used,
        "generated_files": generated_files,
        "code_runs": code_runs,
        "status": final_state["status"],
        "model_used": model_used,
    }
    if approval_info:
        result_payload["approval"] = approval_info
        result_payload["draft_content"] = draft_content

    return result_payload

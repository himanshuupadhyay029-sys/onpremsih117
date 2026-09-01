"""agent.py — the agent loop: PLAN -> EXECUTE -> OBSERVE, wired as a cyclic
LangGraph StateGraph (not a straight line).

Phase 2: agent loop with self-correction and router.
Phase 3: append-only audit logbook integration.
Phase 4: Knowledge Vault FAISS RAG search tool.
Phase 5: Word Document (.docx) writer with anti-hallucination guard.
Phase 6: network-isolated Docker sandbox for code execution with error-feedback self-correction.
Phase 7: OCR (reading scanned/image documents) + Vision (multimodal image/drawing analysis).
Phase 8: Deterministic engineering math calculator (calc.py) showing real arithmetic steps.
"""

import json
import re
from typing import List, Optional, Tuple
import uuid

from langgraph.graph import END, StateGraph

from backend.audit.logbook import log_event
from backend.brain.router import route
from backend.brain.state import AgentState
from backend.engine import ollama, registry
from backend.tools.calc import calculate as calc_tool
from backend.tools.code import write_and_run as code_tool_run
from backend.tools.ocr import extract_text as ocr_tool_extract
from backend.tools.search import search as search_tool
from backend.tools.vision import describe_image as vision_tool_describe
from backend.tools.writer import write_document as writer_tool

MAX_TOTAL_STEPS = 10
MAX_REVISIONS = 3
ERROR_TRIGGER = "simulate_error"
CODE_TIMEOUT_SECONDS = 15

VALID_TOOLS = {"llm", "search", "calc", "vision", "document", "code", "ocr"}

PLAN_PROMPT_TEMPLATE = """You are the planning module of an AI agent. Break the task below into 1 to 6 ordered steps required to complete it.

Each step must be an object with:
  "step": <integer, starting at 1>
  "tool": one of ["llm", "search", "calc", "vision", "document", "code", "ocr"]
  "input": a short instruction/query for that tool

Use "llm" for steps that require reasoning, writing, or explaining WITHOUT executing anything.
Use "calc" for steps performing numerical math, formulas, or engineering calculations with step-by-step arithmetic.
Use "code" for steps that need to generate AND ACTUALLY RUN a Python script in the secure sandbox.
Use "search" for steps needing SOP or reference information from the Knowledge Vault.
Use "ocr" for steps reading/extracting text from an image or scanned document file path.
Use "vision" for steps analyzing photos, engineering drawings, diagrams, or gauges using multimodal AI.
Use "document" for steps creating formal docx reports.

Task: {task}
Task type: {task_type}{failure_context}

Respond with ONLY a raw JSON array of step objects. No prose, no markdown fences, no explanation.
"""


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


def _parse_plan(raw: str, fallback_input: str) -> List[dict]:
    """Robustly parse the planner's JSON, handling markdown-fenced output."""
    text = (raw or "").strip()

    fence_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        bracket_match = re.search(r"(\[.*\])", text, re.DOTALL)
        if bracket_match:
            text = bracket_match.group(1)

    steps: List[dict] = []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            for i, item in enumerate(parsed[:6]):
                if not isinstance(item, dict):
                    continue
                tool = _normalize_tool(item.get("tool", "llm"))
                step_input = str(item.get("input", fallback_input))
                steps.append({"step_num": i + 1, "tool": tool, "input": step_input, "status": "pending"})
    except (json.JSONDecodeError, TypeError):
        steps = []

    if not steps:
        steps = [{"step_num": 1, "tool": "llm", "input": fallback_input, "status": "pending"}]

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
            guidance = "Revise the plan to either use broader search keywords or proceed to document the missing documentation."
        elif last["tool"] == "calc":
            guidance = "The calculation failed or had missing inputs. Revise the plan to search/extract the missing values first."
        else:
            guidance = "Revise the plan to work around this failure."
        failure_context = (
            f"\n\nIMPORTANT: A previous attempt at step {last['step_num']} "
            f"(tool: {last['tool']}) reported: {last['output']}\n"
            f"{guidance}"
        )

    prompt = PLAN_PROMPT_TEMPLATE.format(
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

    steps = _parse_plan(raw, fallback_input=state["original_task"])
    action = {"role": "action", "content": f"Generated plan: {json.dumps(steps)}"}

    log_event(
        task_id=state.get("task_id"),
        event_type="plan",
        actor=reasoning_model,
        summary=f"{'Re-planned' if is_revision else 'Generated plan'} with {len(steps)} steps",
        metadata={
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
        try:
            output = ollama.generate(model, step_input)
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
            target_str = step_input.strip()
            q_target = None
            if "|" in target_str:
                parts = target_str.split("|", 1)
                target_str = parts[0].strip()
                q_target = parts[1].strip()

            vis_res = vision_tool_describe(target_str, question=q_target, task_id=state.get("task_id"))
            output = vis_res["description"]
            is_error = False
            extra_meta = {"image_path": vis_res["image_path"], "question": q_target}
        except Exception as exc:
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
            "code": code_result["code"],
            "stdout": code_result["stdout"],
            "stderr": code_result["stderr"],
            "exit_code": code_result["exit_code"],
            "timed_out": code_result["timed_out"],
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
            doc_res = writer_tool(
                step_input,
                sources=prior_sources if is_doc_grounded else [],
                is_grounded=is_doc_grounded,
                task_id=state.get("task_id"),
            )
            sections_list = doc_res["structured_content"].get("sections", [])
            output = (
                f"Generated document '{doc_res['title']}' saved to {doc_res['filename']}.\n"
                f"File path: {doc_res['file_path']}\n"
                f"Grounded in SOPs: {is_doc_grounded}\n"
                f"Sections: {', '.join(s.get('heading', '') for s in sections_list)}"
            )
            is_error = False
            sources = doc_res["structured_content"].get("sources", [])
            doc_meta = {
                "file_path": doc_res["file_path"],
                "filename": doc_res["filename"],
                "title": doc_res["title"],
                "grounded": is_doc_grounded,
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
            "step_num": step["step_num"],
            "tool": tool,
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

    outputs_summary = "\n".join(
        f"Step {o['step_num']} ({o['tool']}): {o['output']}" for o in state["step_outputs"]
    )
    prompt = (
        f"Task: {state['original_task']}\n\n"
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
        {"executing": "execute", "revising": "plan", "complete": "finalize", "failed": "finalize"},
    )
    graph.add_edge("finalize", END)
    return graph.compile()


_COMPILED_GRAPH = build_graph()


def run_agent(task: str, attachment_type: Optional[str] = None, task_id: Optional[str] = None) -> dict:
    if not task_id:
        task_id = str(uuid.uuid4())

    routing_decision = route(task, attachment_type=attachment_type)
    model_role = routing_decision.model_role
    model_tag = registry.get_model(model_role)

    log_event(
        task_id=task_id,
        event_type="route",
        actor="router",
        summary=f"Routed to task_type='{routing_decision.task_type}', model_role='{model_role}' ({model_tag})",
        metadata={
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
    }

    final_state = _COMPILED_GRAPH.invoke(initial_state, config={"recursion_limit": 60})

    model_used = registry.get_model(final_state["routing_decision"]["model_role"])

    sources_used: List[dict] = []
    generated_files: List[dict] = []
    code_runs: List[dict] = []
    for step_output in final_state["step_outputs"]:
        if "sources" in step_output and step_output["sources"]:
            sources_used.extend(step_output["sources"])
        if "file_path" in step_output:
            generated_files.append({
                "filename": step_output.get("filename"),
                "file_path": step_output.get("file_path"),
                "title": step_output.get("title"),
                "grounded": step_output.get("grounded", True),
            })
        if step_output.get("tool") == "code":
            code_runs.append({
                "step_num": step_output["step_num"],
                "code": step_output.get("code"),
                "stdout": step_output.get("stdout"),
                "stderr": step_output.get("stderr"),
                "exit_code": step_output.get("exit_code"),
                "timed_out": step_output.get("timed_out"),
                "error": step_output.get("error"),
            })

    return {
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

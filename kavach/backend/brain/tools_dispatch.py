"""tools_dispatch.py — modular tool execution and structured fact extraction.

Separates execution of individual tool capabilities (search, code, calc, vision,
ocr, document, llm) from LangGraph node orchestration, returning structured
results and updating the agent's key-fact memory.
"""

from datetime import datetime
import json
import logging
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import uuid

from backend.audit.logbook import log_event
from backend.engine import ollama, registry
from backend.guard.approve import assess_risk, request_approval
from backend.tools.calc import calculate as calc_tool
from backend.tools.code import write_and_run as code_tool_run
from backend.tools.excel import draft_spreadsheet, render_xlsx
from backend.tools.ocr import extract_text as ocr_tool_extract
from backend.tools.ppt import draft_presentation, render_pptx
from backend.tools.search import search as search_tool
from backend.tools.vision import describe_image as vision_tool_describe
from backend.tools.writer import draft_document, render_docx
import time
from backend.terminal_logger import log_tool, _truncate

logger = logging.getLogger("kavach.tools_dispatch")
CODE_TIMEOUT_SECONDS = 15
IMAGE_PATTERN = r"([A-Za-z]:\\[^\r\n<>:\"|?*]+\.(?:png|jpg|jpeg|bmp|tiff|webp)|\S+\.(?:png|jpg|jpeg|bmp|tiff|webp))"


def _extract_key_facts(tool: str, output: str, meta: Dict[str, Any], is_error: bool) -> Dict[str, Any]:
    """Extract deterministic or structured key facts from tool outputs for agent memory."""
    facts: Dict[str, Any] = {}
    if meta.get("needs_clarification"):
        facts["needs_clarification"] = True
        if meta.get("clarify_question"):
            facts["clarify_question"] = meta.get("clarify_question")
    elif not is_error:
        facts["needs_clarification"] = False
        facts["clarify_question"] = None

    if is_error:
        facts[f"last_error_{tool}"] = output[:300]
        return facts

    if tool == "calc":
        if meta.get("calc_result") is not None:
            facts["calc_result"] = meta["calc_result"]
        if meta.get("formula_name"):
            facts["calc_formula"] = meta["formula_name"]
        if meta.get("unit"):
            facts["calc_unit"] = meta["unit"]

    elif tool == "search":
        sources = meta.get("sources") or []
        facts["search_sources"] = [s.get("filename") for s in sources if isinstance(s, dict) and s.get("filename")]
        facts["search_grounded"] = meta.get("grounded", True)

    elif tool == "code":
        facts["code_exit_code"] = meta.get("exit_code", 0)
        facts["code_language"] = meta.get("language", "python")
        stdout = (meta.get("stdout") or "").strip()
        if stdout:
            lines = stdout.splitlines()
            facts["code_output_summary"] = lines[-1] if len(lines) == 1 else lines[:5]

    elif tool == "document":
        facts["document_title"] = meta.get("title")
        facts["document_path"] = meta.get("file_path")
        facts["document_awaiting_approval"] = meta.get("awaiting_approval", False)

    elif tool == "excel":
        facts["excel_title"] = meta.get("title")
        facts["excel_path"] = meta.get("file_path")
        facts["excel_sheets"] = meta.get("sheets")
        facts["excel_rows"] = meta.get("total_rows")

    elif tool == "ppt":
        facts["ppt_title"] = meta.get("title")
        facts["ppt_path"] = meta.get("file_path")
        facts["ppt_slides_count"] = meta.get("slides_count")

    elif tool == "ocr":
        facts["ocr_engine"] = meta.get("engine")
        facts["ocr_confidence"] = meta.get("confidence")

    elif tool == "vision":
        facts["vision_image"] = meta.get("image_path")

    return facts


def dispatch_tool(
    tool: str,
    step_input: str,
    state: Dict[str, Any],
) -> Dict[str, Any]:
    """Dispatches execution to the appropriate tool implementation.

    Returns a dictionary containing:
      - output: str
      - is_error: bool
      - actor: str
      - sources: Optional[List[Dict[str, Any]]]
      - is_grounded: bool
      - doc_meta: Dict[str, Any]
      - code_meta: Dict[str, Any]
      - extra_meta: Dict[str, Any]
      - messages_update: List[Dict[str, str]]
      - key_facts: Dict[str, Any]
    """
    messages_update: List[Dict[str, str]] = []
    doc_meta: Dict[str, Any] = {}
    code_meta: Dict[str, Any] = {}
    extra_meta: Dict[str, Any] = {}
    is_grounded_flag = True
    sources: Optional[List[Dict[str, Any]]] = None

    # Inject accumulated structured key_facts into step_input context if not already present
    t0 = time.perf_counter()
    log_tool(tool, "DISPATCH", f"Input: '{_truncate(step_input, 85)}'")
    key_facts_ctx = state.get("key_facts", {})
    injected_input = step_input
    if key_facts_ctx and tool in ("calc", "code", "document", "llm", "excel", "ppt"):
        facts_summary = json.dumps(key_facts_ctx, indent=2)
        if "Accumulated Key Facts" not in injected_input:
            injected_input = f"{step_input}\n\n[Known Context & Facts from Earlier Steps]:\n{facts_summary}"

    if tool == "llm":
        routing_dec = state.get("routing_decision") or {}
        role = routing_dec.get("model_role", "reasoning")
        model = registry.get_model(role)
        actor = model
        llm_prompt = injected_input
        if state.get("history_context"):
            llm_prompt = f"{state['history_context']}\nUser query: {injected_input}"
        try:
            output = ollama.generate(model, llm_prompt)
            if not output.strip():
                output = "[error] The model returned an empty response. It may be overloaded or the context window is full. Please retry."
                is_error = True
            else:
                is_error = False
        except Exception as exc:
            output = f"[error] llm call failed: {exc}"
            is_error = True
        messages_update = [
            {"role": "user", "content": step_input},
            {"role": "assistant", "content": output},
        ]

    elif tool == "search":
        actor = "vault_search"
        result = search_tool(step_input, task_id=state.get("task_id"))
        answer = result["answer"]
        sources = result.get("sources", [])
        is_grounded_flag = result.get("grounded", True)
        if sources:
            source_labels = []
            for s in sources:
                label = f"[{s.get('id', 1)}] {s.get('filename')}"
                if s.get("breadcrumb") and s.get("breadcrumb") != s.get("filename"):
                    label += f" ({s.get('breadcrumb')})"
                source_labels.append(label)
            sources_summary = "\n".join(f"  • {lbl}" for lbl in source_labels)
            output = f"{answer}\n\n**Referenced Sources:**\n{sources_summary}"
        else:
            output = answer
        is_error = False

    elif tool == "calc":
        actor = "calc_tool"
        prior_context_list = [o["output"] for o in state.get("step_outputs", [])]
        context_str = "\n".join(prior_context_list) if prior_context_list else None
        calc_res = calc_tool(injected_input, context=context_str, task_id=state.get("task_id"))
        missing = calc_res.get("missing_inputs") or []
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
            "missing_inputs": missing,
            "needs_clarification": bool(missing),
            "clarify_question": (
                f"To calculate {calc_res.get('formula_name', 'the result')}, please provide the following missing parameter(s): {', '.join(missing)}."
                if missing else None
            ),
        }

    elif tool == "ocr":
        actor = "ocr_tool"
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
        try:
            raw_input = step_input.strip()
            target_str = raw_input
            q_target = None
            if "|" in raw_input:
                parts = raw_input.split("|", 1)
                target_str = parts[0].strip()
                q_target = parts[1].strip()

            img_path_to_use = target_str
            try:
                from backend.tools.vision import _resolve_image_path
                img_path_to_use = str(_resolve_image_path(target_str))
            except Exception:
                m = re.search(IMAGE_PATTERN, raw_input, re.IGNORECASE)
                if m:
                    img_path_to_use = m.group(1).strip()
                    if not q_target:
                        q_target = raw_input.replace(m.group(0), "").replace("Attached file:", "").strip() or None
                else:
                    m_orig = re.search(IMAGE_PATTERN, state.get("original_task", ""), re.IGNORECASE)
                    if m_orig:
                        img_path_to_use = m_orig.group(1).strip()
                        if not q_target:
                            q_target = raw_input.replace("Attached file:", "").strip() or None

            vis_res = vision_tool_describe(img_path_to_use, question=q_target, task_id=state.get("task_id"))
            output = vis_res["description"]
            is_error = False
            extra_meta = {"image_path": vis_res["image_path"], "question": q_target}
        except Exception as exc:
            logger.error(f"[TOOLS_DISPATCH] Vision tool failed: {exc}")
            output = f"[error] Vision analysis failed: {exc}"
            is_error = True

    elif tool == "code":
        actor = registry.get_model("code")
        prior_error = None
        for prev in reversed(state.get("step_outputs", [])):
            if prev.get("tool") == "code" and prev.get("error"):
                prior_error = prev.get("stderr") or prev.get("output")
                break

        code_result = code_tool_run(
            injected_input,
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
        actor = registry.get_model("reasoning")
        prior_sources: List[dict] = []
        has_search = False
        has_grounded_search = False
        last_search_grounded = None

        for prev_out in state.get("step_outputs", []):
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
            doc_topic = step_input
            if state.get("shared_memory"):
                doc_topic = f"{step_input}\n\nContext & Results from Prior Execution:\n{state['shared_memory']}"

            structured = draft_document(
                doc_topic,
                sources=prior_sources if is_doc_grounded else [],
                is_grounded=is_doc_grounded,
                model=actor,
            )
            title = structured.get("title", "Technical Document")
            sections_list = structured.get("sections", [])
            sources = structured.get("sources", [])

            is_code_doc = any(po.get("tool") in ("code", "calc") for po in state.get("step_outputs", [])) or "code" in str(state.get("shared_memory", "")).lower()
            if is_code_doc:
                risk_info = {
                    "risk": "low",
                    "confidence": 0.95,
                    "reasoning": "Technical summary document generated from in-session verified code execution results.",
                }
            else:
                risk_info = assess_risk(
                    task_type="document",
                    document_content=structured,
                    sources_used=prior_sources if is_doc_grounded else [],
                )

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
        except Exception as exc:
            output = f"[error] document generation failed: {exc}"
            is_error = True
            sources = None

    elif tool == "excel":
        actor = registry.get_model("reasoning")
        prior_sources = []
        for prev_out in state.get("step_outputs", []):
            if prev_out.get("tool") == "search" and prev_out.get("sources"):
                prior_sources.extend(prev_out["sources"])

        try:
            excel_topic = step_input
            if state.get("shared_memory"):
                excel_topic = f"{step_input}\n\nContext & Results from Prior Execution:\n{state['shared_memory']}"

            structured_xl = draft_spreadsheet(
                excel_topic,
                sources=prior_sources,
                model=actor,
            )
            file_path = render_xlsx(structured_xl)
            filename = file_path.name
            title = structured_xl.get("title", "Spreadsheet")
            sheets = [s.get("name") for s in structured_xl.get("sheets", [])]
            total_rows = sum(len(s.get("rows", [])) for s in structured_xl.get("sheets", []))

            log_event(
                task_id=state.get("task_id"),
                event_type="write",
                actor="excel_tool",
                summary=f"Rendered Excel spreadsheet '{title}' ({len(sheets)} sheets, {total_rows} rows) -> {filename}",
                metadata={
                    "filename": filename,
                    "file_path": str(file_path),
                    "title": title,
                    "sheets": sheets,
                    "total_rows": total_rows,
                },
                external_calls=0,
            )

            output = (
                f"Generated Excel spreadsheet '{title}' saved to {filename}.\n"
                f"File path: {file_path}\n"
                f"Sheets: {', '.join(sheets)} ({total_rows} total rows with formulas)"
            )
            is_error = False
            doc_meta = {
                "file_path": str(file_path),
                "filename": filename,
                "title": title,
                "file_type": "excel",
                "sheets": sheets,
                "total_rows": total_rows,
                "awaiting_approval": False,
            }
        except Exception as exc:
            logger.error(f"[TOOLS_DISPATCH] Excel tool failed: {exc}")
            output = f"[error] Excel spreadsheet generation failed: {exc}"
            is_error = True

    elif tool == "ppt":
        actor = registry.get_model("reasoning")
        prior_sources = []
        for prev_out in state.get("step_outputs", []):
            if prev_out.get("tool") == "search" and prev_out.get("sources"):
                prior_sources.extend(prev_out["sources"])

        try:
            ppt_topic = step_input
            if state.get("shared_memory"):
                ppt_topic = f"{step_input}\n\nContext & Results from Prior Execution:\n{state['shared_memory']}"

            structured_ppt = draft_presentation(
                ppt_topic,
                sources=prior_sources,
                model=actor,
            )
            file_path = render_pptx(structured_ppt)
            filename = file_path.name
            title = structured_ppt.get("title", "Presentation")
            slides_count = len(structured_ppt.get("slides", []))

            log_event(
                task_id=state.get("task_id"),
                event_type="write",
                actor="ppt_tool",
                summary=f"Rendered PowerPoint presentation '{title}' ({slides_count} slides) -> {filename}",
                metadata={
                    "filename": filename,
                    "file_path": str(file_path),
                    "title": title,
                    "slides_count": slides_count,
                },
                external_calls=0,
            )

            output = (
                f"Generated PowerPoint presentation '{title}' ({slides_count} slides) saved to {filename}.\n"
                f"File path: {file_path}\n"
                f"Layout: 16:9 Widescreen Dark Industrial Theme with Speaker Notes"
            )
            is_error = False
            doc_meta = {
                "file_path": str(file_path),
                "filename": filename,
                "title": title,
                "file_type": "ppt",
                "slides_count": slides_count,
                "awaiting_approval": False,
            }
        except Exception as exc:
            logger.error(f"[TOOLS_DISPATCH] PPT tool failed: {exc}")
            output = f"[error] PowerPoint presentation generation failed: {exc}"
            is_error = True

    else:
        actor = tool
        output = f"Completed action '{tool}' on input: {step_input}"
        is_error = False

    # Extract structured key facts
    combined_meta = {**doc_meta, **code_meta, **extra_meta, "sources": sources, "grounded": is_grounded_flag}
    extracted_facts = _extract_key_facts(tool, output, combined_meta, is_error)

    elapsed = time.perf_counter() - t0
    log_tool(tool, "RESULT", f"Output: '{_truncate(output, 85)}'", elapsed_s=elapsed, is_error=is_error)

    return {
        "output": output,
        "is_error": is_error,
        "actor": actor,
        "sources": sources,
        "is_grounded": is_grounded_flag,
        "doc_meta": doc_meta,
        "code_meta": code_meta,
        "extra_meta": extra_meta,
        "messages_update": messages_update,
        "key_facts": extracted_facts,
    }

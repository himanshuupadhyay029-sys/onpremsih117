"""main.py — FastAPI entry point. Wires the engine, agent brain, audit logbook, and download service."""

import os

# Strictly local: disable LangChain/LangSmith tracing and telemetry before anything
# that might read these at import time.
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_TRACING"] = "false"
os.environ["LANGCHAIN_ENDPOINT"] = ""
os.environ.pop("LANGCHAIN_API_KEY", None)
os.environ.pop("LANGSMITH_API_KEY", None)

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import uuid
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend import config
from backend.engine import registry, ollama
from backend.audit.logbook import log_event, read_events
from backend.auth.routes import router as auth_router, get_optional_user
from backend.brain.agent import run_agent
from backend.brain.event_bus import emit_sync, register_task, unregister_task
from backend.chat.routes import router as chat_router
from backend.db.models import AgentRun, Chat, Message, User
from backend.db.session import get_db, SessionLocal
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.guard.approve import get_approval, resolve_approval
from backend.tools.writer import render_docx
from backend.vault.ingest import METADATA_PATH, SUPPORTED_EXTENSIONS, ingest_document
from backend.shield.firewall import (
    check_firewall_status,
    disable_firewall_lockdown,
    enable_firewall_lockdown,
)
from backend.shield.monitor import (
    get_active_connections,
    get_monitor_summary,
    start_monitor,
    stop_monitor,
)

app = FastAPI(title="KAVACH", description="Phase 10: Frontend UI + Sovereignty Proof + Agent Brain + Auth & Persistent Chat")

# Explicit CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)

VANILLA_FRONTEND_DIR = config.PROJECT_ROOT / "frontend"
REACT_FRONTEND_DIR = config.PROJECT_ROOT / "frontend-react" / "dist"
UPLOADS_DIR = config.PROJECT_ROOT / "knowledge" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

if (REACT_FRONTEND_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(REACT_FRONTEND_DIR / "assets")), name="assets")
if VANILLA_FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(VANILLA_FRONTEND_DIR)), name="static")


@app.on_event("startup")
def _start_shield_monitor() -> None:
    start_monitor(interval_seconds=1.0)


@app.on_event("shutdown")
def _stop_shield_monitor() -> None:
    stop_monitor()


class RunRequest(BaseModel):
    task: str
    attachment_type: Optional[str] = None
    task_id: Optional[str] = None
    chat_id: Optional[str] = None
    history: Optional[List[Dict[str, Any]]] = None



@app.get("/")
def ui_root():
    """Serves the primary React frontend UI shell."""
    if REACT_FRONTEND_DIR.exists() and (REACT_FRONTEND_DIR / "index.html").exists():
        return FileResponse(REACT_FRONTEND_DIR / "index.html")
    return FileResponse(VANILLA_FRONTEND_DIR / "index.html")


@app.get("/vanilla")
def vanilla_ui():
    """Serves the legacy vanilla frontend."""
    return FileResponse(VANILLA_FRONTEND_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/run")
def run(
    req: RunRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    chat = None
    user_msg = None
    chat_id = req.chat_id

    if current_user:
        if chat_id:
            try:
                c_uuid = uuid.UUID(chat_id)
                chat = db.query(Chat).filter(Chat.id == c_uuid, Chat.user_id == current_user.id).first()
            except Exception:
                chat = None

        if not chat:
            clean_title = req.task.strip().split("\n")[0]
            if len(clean_title) > 40:
                clean_title = clean_title[:37] + "..."
            chat = Chat(
                user_id=current_user.id,
                title=clean_title or "New Chat",
                chat_type="general",
            )
            db.add(chat)
            db.commit()
            db.refresh(chat)

        try:
            user_msg = Message(
                id=uuid.uuid4(),
                chat_id=chat.id,
                role="user",
                content=req.task,
                meta={"attachment_type": req.attachment_type, "task_id": req.task_id},
            )
            db.add(user_msg)
            chat.updated_at = func.now()
            db.commit()
        except Exception as exc:
            print(f"[ERROR] Failed to persist user message: {exc}", flush=True)

    history = []
    initial_key_facts = {}
    if chat:
        try:
            if user_msg:
                db_msgs = (
                    db.query(Message)
                    .filter(Message.chat_id == chat.id, Message.id != user_msg.id)
                    .order_by(Message.created_at.asc())
                    .all()
                )
            else:
                db_msgs = (
                    db.query(Message)
                    .filter(Message.chat_id == chat.id)
                    .order_by(Message.created_at.asc())
                    .all()
                )
            history = [{"role": m.role, "content": m.content} for m in db_msgs]
            if chat.agent_memory:
                initial_key_facts = dict(chat.agent_memory)
        except Exception as exc:
            print(f"[WARN] Failed to load history: {exc}", flush=True)

    if not history and req.history:
        history = req.history

    agent_res = run_agent(
        req.task,
        attachment_type=req.attachment_type,
        task_id=req.task_id,
        history=history,
        initial_key_facts=initial_key_facts,
    )

    if chat:
        try:
            # Merge updated agent memory
            new_facts = agent_res.get("key_facts") or {}
            if new_facts:
                merged_mem = dict(chat.agent_memory or {})
                merged_mem.update(new_facts)
                chat.agent_memory = merged_mem

            asst_msg = Message(
                id=uuid.uuid4(),
                chat_id=chat.id,
                role="assistant",
                content=agent_res.get("result", "") or "",
                meta={
                    "task_id": agent_res.get("task_id"),
                    "status": agent_res.get("status"),
                    "trace": agent_res.get("trace", []),
                    "steps": agent_res.get("steps", agent_res.get("plan", [])),
                    "step_outputs": agent_res.get("step_outputs", []),
                    "sources": agent_res.get("sources", []),
                    "generated_files": agent_res.get("generated_files", []),
                    "code_runs": agent_res.get("code_runs", []),
                    "approval": agent_res.get("approval"),
                    "draft_content": agent_res.get("draft_content"),
                    "model_used": agent_res.get("model_used"),
                    "models_used": agent_res.get("models_used", []),
                    "routing_decision": agent_res.get("routing_decision"),
                    "clarify_question": agent_res.get("clarify_question"),
                    "key_facts": agent_res.get("key_facts"),
                },
            )
            db.add(asst_msg)

            # Persist AgentRun for state snapshot and resume
            task_id_str = agent_res.get("task_id") or req.task_id or str(uuid.uuid4())
            agent_run = db.query(AgentRun).filter(AgentRun.task_id == task_id_str).first()
            if not agent_run:
                agent_run = AgentRun(
                    id=uuid.uuid4(),
                    chat_id=chat.id,
                    task_id=task_id_str,
                    status=agent_res.get("status", "complete"),
                    state_snapshot=agent_res.get("state_snapshot", {}),
                )
                db.add(agent_run)
            else:
                agent_run.status = agent_res.get("status", "complete")
                agent_run.state_snapshot = agent_res.get("state_snapshot", {})
                agent_run.updated_at = func.now()

            if chat.title == "New Chat":
                clean_title = req.task.strip().split("\n")[0]
                if len(clean_title) > 40:
                    clean_title = clean_title[:37] + "..."
                chat.title = clean_title or "New Chat"

            chat.updated_at = func.now()
            db.commit()
        except Exception as exc:
            print(f"[ERROR] Failed to persist assistant message & run: {exc}", flush=True)

    if chat:
        agent_res["chat_id"] = str(chat.id)
        agent_res["chat_title"] = chat.title
    else:
        agent_res["chat_id"] = None
        agent_res["chat_title"] = None

    return agent_res


@app.get("/run/stream")
async def run_stream(
    task: str,
    task_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    attachment_type: Optional[str] = None,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Real-time SSE streaming endpoint for KAVACH autonomous agent execution."""
    if not task_id:
        task_id = str(uuid.uuid4())

    loop = asyncio.get_running_loop()
    queue = register_task(task_id, loop)

    chat = None
    if current_user:
        if chat_id:
            try:
                c_uuid = uuid.UUID(chat_id)
                chat = db.query(Chat).filter(Chat.id == c_uuid, Chat.user_id == current_user.id).first()
            except Exception:
                chat = None
        if not chat:
            clean_title = task.strip().split("\n")[0]
            if len(clean_title) > 40:
                clean_title = clean_title[:37] + "..."
            chat = Chat(user_id=current_user.id, title=clean_title or "New Chat", chat_type="general")
            db.add(chat)
            db.commit()
            db.refresh(chat)

        try:
            user_msg = Message(
                id=uuid.uuid4(),
                chat_id=chat.id,
                role="user",
                content=task,
                meta={"attachment_type": attachment_type, "task_id": task_id},
            )
            db.add(user_msg)
            chat.updated_at = func.now()
            db.commit()
        except Exception as exc:
            print(f"[ERROR] Failed to persist user msg in stream: {exc}", flush=True)

    history = []
    initial_key_facts = {}
    if chat:
        try:
            db_msgs = db.query(Message).filter(Message.chat_id == chat.id).order_by(Message.created_at.asc()).all()
            history = [{"role": m.role, "content": m.content} for m in db_msgs[:-1]]
            if chat.agent_memory:
                initial_key_facts = dict(chat.agent_memory)
        except Exception as exc:
            print(f"[WARN] Failed to load history in stream: {exc}", flush=True)

    chat_db_id = str(chat.id) if chat else None
    chat_db_title = chat.title if chat else None

    def _execute_worker():
        worker_db = SessionLocal()
        try:
            res = run_agent(
                task,
                attachment_type=attachment_type,
                task_id=task_id,
                history=history,
                initial_key_facts=initial_key_facts,
            )
            if chat_db_id:
                try:
                    c = worker_db.query(Chat).filter(Chat.id == uuid.UUID(chat_db_id)).first()
                    if c:
                        new_facts = res.get("key_facts") or {}
                        if new_facts:
                            merged_mem = dict(c.agent_memory or {})
                            merged_mem.update(new_facts)
                            c.agent_memory = merged_mem

                        asst_msg = Message(
                            id=uuid.uuid4(),
                            chat_id=c.id,
                            role="assistant",
                            content=res.get("result", "") or "",
                            meta={
                                "task_id": res.get("task_id"),
                                "status": res.get("status"),
                                "trace": res.get("trace", []),
                                "steps": res.get("steps", res.get("plan", [])),
                                "step_outputs": res.get("step_outputs", []),
                                "sources": res.get("sources", []),
                                "generated_files": res.get("generated_files", []),
                                "code_runs": res.get("code_runs", []),
                                "approval": res.get("approval"),
                                "draft_content": res.get("draft_content"),
                                "model_used": res.get("model_used"),
                                "models_used": res.get("models_used", []),
                                "routing_decision": res.get("routing_decision"),
                                "clarify_question": res.get("clarify_question"),
                                "key_facts": res.get("key_facts"),
                            },
                        )
                        worker_db.add(asst_msg)

                        ar = worker_db.query(AgentRun).filter(AgentRun.task_id == task_id).first()
                        if not ar:
                            ar = AgentRun(
                                id=uuid.uuid4(),
                                chat_id=c.id,
                                task_id=task_id,
                                status=res.get("status", "complete"),
                                state_snapshot=res.get("state_snapshot", {}),
                            )
                            worker_db.add(ar)
                        else:
                            ar.status = res.get("status", "complete")
                            ar.state_snapshot = res.get("state_snapshot", {})
                            ar.updated_at = func.now()

                        c.updated_at = func.now()
                        worker_db.commit()
                except Exception as exc:
                    print(f"[ERROR] Worker failed DB persist: {exc}", flush=True)

            res["chat_id"] = chat_db_id
            res["chat_title"] = chat_db_title
            emit_sync(task_id, "done_stream", res)
        except Exception as exc:
            emit_sync(task_id, "error", {"error": str(exc)})
        finally:
            worker_db.close()

    loop.run_in_executor(None, _execute_worker)

    async def sse_generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=90.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                event_name = event.get("event", "message")
                event_data = event.get("data", {})
                yield f"event: {event_name}\ndata: {json.dumps(event_data)}\n\n"

                if event_name in ("done_stream", "error"):
                    break
        finally:
            unregister_task(task_id)

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class ReplyRequest(BaseModel):
    reply: str
    chat_id: Optional[str] = None


@app.post("/run/{task_id}/reply")
def reply_to_agent(
    task_id: str,
    req: ReplyRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Resumes a paused agent run after user clarification or operator feedback."""
    agent_run = db.query(AgentRun).filter(AgentRun.task_id == task_id).first()
    if not agent_run:
        raise HTTPException(status_code=404, detail="Agent run not found")

    snapshot = dict(agent_run.state_snapshot or {})
    if not snapshot:
        raise HTTPException(status_code=400, detail="No resume snapshot available for this run")

    curr_idx = snapshot.get("current_step", 0)
    if snapshot.get("plan") and curr_idx < len(snapshot["plan"]):
        orig_inp = snapshot["plan"][curr_idx]["input"]
        snapshot["plan"][curr_idx]["input"] = f"{orig_inp}\n\n[Operator Feedback/Clarification]: {req.reply}"

    snapshot["status"] = "executing"
    snapshot["clarify_question"] = None

    res = run_agent(
        task="",
        task_id=task_id,
        resume_state=snapshot,
    )

    agent_run.status = res.get("status", "complete")
    agent_run.state_snapshot = res.get("state_snapshot", {})
    agent_run.updated_at = func.now()

    if agent_run.chat_id:
        chat = db.query(Chat).filter(Chat.id == agent_run.chat_id).first()
        if chat:
            asst_msg = Message(
                id=uuid.uuid4(),
                chat_id=chat.id,
                role="assistant",
                content=res.get("result", "") or "",
                meta={
                    "task_id": res.get("task_id"),
                    "status": res.get("status"),
                    "trace": res.get("trace", []),
                    "steps": res.get("steps", res.get("plan", [])),
                    "step_outputs": res.get("step_outputs", []),
                    "sources": res.get("sources", []),
                    "generated_files": res.get("generated_files", []),
                    "code_runs": res.get("code_runs", []),
                    "model_used": res.get("model_used"),
                    "models_used": res.get("models_used", []),
                    "routing_decision": res.get("routing_decision"),
                    "key_facts": res.get("key_facts"),
                },
            )
            db.add(asst_msg)
            chat.updated_at = func.now()

    db.commit()
    return res




@app.get("/models")
def models():
    reg = registry.load_registry()
    try:
        installed = ollama.list_models()
    except Exception as exc:
        installed = []
        return {"registry": reg, "installed": installed, "warning": str(exc)}
    return {"registry": reg, "installed": installed}


class ModelAssignRequest(BaseModel):
    role: str
    model: str

@app.post("/models/assign")
def assign_model(req: ModelAssignRequest):
    try:
        new_reg = registry.set_model(req.role, req.model)
        return {"success": True, "registry": new_reg}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

class ModelPullRequest(BaseModel):
    model: str

class ModelCancelRequest(BaseModel):
    model: str

@app.get("/models/info")
def get_model_info_endpoint(model: str):
    """Returns availability and all available tags/quantizations for a given model from Ollama library."""
    return ollama.get_model_tags_and_quants(model)

@app.get("/models/pull/stream")
async def pull_model_stream_endpoint(model: str):
    """Streams pull progress directly from Ollama as Server-Sent Events (SSE)."""
    return StreamingResponse(
        ollama.stream_pull_model(model),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

@app.post("/models/pull/cancel")
async def cancel_model_pull_endpoint(req: ModelCancelRequest):
    """Cancels an ongoing model pull immediately."""
    cancelled = await ollama.cancel_pull_model(req.model)
    return {"success": True, "cancelled": cancelled, "model": req.model}

@app.post("/models/pull")
def pull_model_endpoint(req: ModelPullRequest):
    try:
        ollama.pull_model(req.model)
        return {"success": True, "message": f"Successfully pulled {req.model}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/models/{model_name:path}")
def delete_model_endpoint(model_name: str):
    try:
        ollama.delete_model(model_name)
        return {"success": True, "message": f"Successfully deleted {model_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CodeExecuteRequest(BaseModel):
    code: str
    language: Optional[str] = "python"
    stdin: Optional[str] = None
    task_id: Optional[str] = None

@app.post("/code/run")
def run_code_endpoint(req: CodeExecuteRequest):
    """Executes code in the network-isolated Docker sandbox with optional interactive stdin."""
    try:
        from backend.tools import sandbox
        return sandbox.run_code(
            code=req.code,
            language=req.language or "python",
            user_stdin=req.stdin,
            task_id=req.task_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/audit")
def audit(task_id: Optional[str] = None):
    return {"events": read_events(task_id=task_id)}


class ApprovalRequest(BaseModel):
    decision: str
    edited_content: Optional[Any] = None


@app.get("/approval/{task_id}")
def get_approval_endpoint(task_id: str):
    record = get_approval(task_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"No approval record found for task '{task_id}'.")
    return record


@app.post("/approval/{task_id}")
def post_approval_endpoint(task_id: str, req: ApprovalRequest):
    record = get_approval(task_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"No approval record found for task '{task_id}'.")

    decision = req.decision.strip().lower()
    if decision not in {"approve", "reject", "edit"}:
        raise HTTPException(status_code=400, detail="Decision must be 'approve', 'reject', or 'edit'.")

    resolved = resolve_approval(task_id, decision=decision, edited_content=req.edited_content)

    if decision == "reject":
        return {
            "task_id": task_id,
            "status": "rejected",
            "decision": "reject",
            "message": "Document generation rejected by operator. No file generated.",
            "filename": None,
            "file_path": None,
        }

    # If approved or edited, now render the final downloadable .docx file
    content_to_render = resolved["document_content"]
    if isinstance(content_to_render, str):
        content_to_render = {
            "title": "Document (Edited)",
            "sections": [{"heading": "Content", "body": content_to_render}],
            "sources": resolved.get("sources", []),
        }

    file_path = render_docx(content_to_render)
    filename = file_path.name
    resolved["filename"] = filename
    resolved["file_path"] = str(file_path)

    log_event(
        task_id=task_id,
        event_type="write",
        actor="writer",
        summary=f"Rendered final approved document '{content_to_render.get('title')}' -> {filename}",
        metadata={
            "filename": filename,
            "file_path": str(file_path),
            "decision": decision,
            "risk": resolved.get("risk"),
        },
        external_calls=0,
    )

    return {
        "task_id": task_id,
        "status": resolved["status"],
        "decision": decision,
        "filename": filename,
        "file_path": str(file_path),
        "download_url": f"/download/{filename}",
        "title": content_to_render.get("title"),
    }


@app.get("/download/{filename}")
def download_file(filename: str):
    """Serves a generated file from OUTPUTS_DIR with strict path-traversal safety."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename format.")

    file_path = config.OUTPUTS_DIR / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found in outputs.")

    media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if filename.endswith(".csv"):
        media_type = "text/csv"
    elif filename.endswith(".json"):
        media_type = "application/json"

    return FileResponse(path=file_path, filename=filename, media_type=media_type)


@app.get("/knowledge/list")
def knowledge_list():
    """Read-only: aggregates the existing FAISS metadata.json into per-document chunk counts."""
    if not METADATA_PATH.exists():
        return {"documents": [], "total_chunks": 0}

    with open(METADATA_PATH, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    counts: dict = {}
    for entry in metadata:
        name = entry.get("source_filename", "unknown")
        counts[name] = counts.get(name, 0) + 1

    documents = [{"filename": name, "chunk_count": count} for name, count in sorted(counts.items())]
    return {"documents": documents, "total_chunks": len(metadata)}


@app.post("/knowledge/upload")
def knowledge_upload(file: UploadFile = File(...), ingest: bool = Form(True)):
    """Saves an uploaded document and (optionally) runs it through the existing
    Phase 4/7 ingestion pipeline. ingest=False is used by the task composer, which
    only needs the file on disk for the ocr/vision tools to read."""
    safe_name = Path(file.filename or "upload").name
    suffix = Path(safe_name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    content = file.file.read()
    dest = UPLOADS_DIR / safe_name
    dest.write_bytes(content)

    log_event(
        event_type="upload",
        actor="ui",
        summary=f"Uploaded '{safe_name}' ({len(content)} bytes), ingest={ingest}",
        metadata={"filename": safe_name, "bytes": len(content), "ingest": ingest, "file_path": str(dest)},
        external_calls=0,
    )

    if not ingest:
        return {"filename": safe_name, "file_path": str(dest), "ingested": False, "chunk_count": 0}

    result = ingest_document(dest)  # logs its own "ingest" audit event
    return {
        "filename": safe_name,
        "file_path": str(dest),
        "ingested": True,
        "chunk_count": result["chunk_count"],
    }


@app.get("/shield/status")
def shield_status():
    return {
        "monitor": get_monitor_summary(),
        "firewall": check_firewall_status(),
    }


@app.post("/shield/lockdown")
def shield_lockdown():
    result = enable_firewall_lockdown()
    if not result.get("success"):
        raise HTTPException(status_code=403, detail=result.get("error"))
    return result


@app.post("/shield/unlock")
def shield_unlock():
    result = disable_firewall_lockdown()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Unknown error disabling lockdown."))
    return result


@app.websocket("/shield/monitor")
async def shield_monitor_ws(websocket: WebSocket):
    """Streams a live connection snapshot every ~1 second (Phase 10 frontend consumes this)."""
    await websocket.accept()
    try:
        while True:
            conns = get_active_connections()
            external = [c for c in conns if c["classification"] == "external"]
            external_kavach = [c for c in external if c.get("is_kavach_process")]
            snapshot = {
                "total_count": len(conns),
                "external_count": len(external_kavach),
                "external_count_all_processes": len(external),
                "connections": conns,
            }
            await websocket.send_json(snapshot)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass

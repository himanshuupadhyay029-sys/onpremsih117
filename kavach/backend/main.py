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
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend import config
from backend.engine import registry, ollama
from backend.audit.logbook import log_event, read_events, verify_chain
from backend.auth.routes import router as auth_router, get_optional_user, get_current_user, require_role
from backend.brain.agent import run_agent
from backend.brain.event_bus import emit_sync, register_task, unregister_task
from backend.chat.routes import router as chat_router
from backend.db.models import AgentRun, Chat, Message, User
from backend.db.session import get_db, SessionLocal
from sqlalchemy import func
from sqlalchemy.orm import Session
from backend.guard.approve import (
    get_approval,
    resolve_approval,
    list_pending_approvals_db,
    list_approval_history_db,
    get_pending_approvals_count,
)
from backend.tools.writer import render_docx
from backend.terminal_logger import log_gateway, _truncate
from backend.vault.ingest import SUPPORTED_EXTENSIONS, ingest_document, delete_document, get_user_paths
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
def _on_startup() -> None:
    start_monitor(interval_seconds=1.0)


@app.on_event("shutdown")
def _on_shutdown() -> None:
    stop_monitor()


# In-memory snapshot cache for fast task state resumption across anonymous and authenticated sessions
_AGENT_RUNS_CACHE: Dict[str, Dict[str, Any]] = {}


class RunRequest(BaseModel):
    task: str
    attachment_type: Optional[str] = None
    vault_files: Optional[List[str]] = None
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
    log_gateway("POST /run", req.task_id, f"Task: '{_truncate(req.task, 65)}'")
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
                meta={"attachment_type": req.attachment_type, "vault_files": req.vault_files, "task_id": req.task_id},
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

    user_id_str = str(current_user.id) if current_user else None
    agent_res = run_agent(
        req.task,
        attachment_type=req.attachment_type,
        task_id=req.task_id,
        history=history,
        initial_key_facts=initial_key_facts,
        user_id=user_id_str,
        vault_files=req.vault_files,
    )


    task_id_str = agent_res.get("task_id") or req.task_id or str(uuid.uuid4())
    if agent_res.get("state_snapshot"):
        _AGENT_RUNS_CACHE[task_id_str] = agent_res["state_snapshot"]

    try:
        if chat:
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

            if chat.title == "New Chat":
                clean_title = req.task.strip().split("\n")[0]
                if len(clean_title) > 40:
                    clean_title = clean_title[:37] + "..."
                chat.title = clean_title or "New Chat"

            chat.updated_at = func.now()

        # Persist AgentRun for state snapshot and resume
        agent_run = db.query(AgentRun).filter(AgentRun.task_id == task_id_str).first()
        if not agent_run:
            agent_run = AgentRun(
                id=uuid.uuid4(),
                chat_id=chat.id if chat else None,
                task_id=task_id_str,
                status=agent_res.get("status", "complete"),
                state_snapshot=agent_res.get("state_snapshot", {}),
            )
            db.add(agent_run)
        else:
            agent_run.status = agent_res.get("status", "complete")
            agent_run.state_snapshot = agent_res.get("state_snapshot", {})
            agent_run.updated_at = func.now()

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
    vault_files: Optional[List[str]] = Query(None),
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Real-time SSE streaming endpoint for KAVACH autonomous agent execution."""
    if not task_id:
        task_id = str(uuid.uuid4())

    parsed_vault_files: List[str] = []
    if vault_files:
        for vf in vault_files:
            if isinstance(vf, str) and vf.startswith("[") and vf.endswith("]"):
                try:
                    parsed_vault_files.extend(json.loads(vf))
                except Exception:
                    parsed_vault_files.append(vf)
            elif isinstance(vf, str) and "," in vf:
                parsed_vault_files.extend([item.strip() for item in vf.split(",") if item.strip()])
            elif vf:
                parsed_vault_files.append(vf)

    log_gateway("POST /run/stream", task_id, f"Task: '{_truncate(task, 65)}'")
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
                meta={
                    "attachment_type": attachment_type,
                    "vault_files": parsed_vault_files or None,
                    "task_id": task_id,
                },
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
    user_id_str = str(current_user.id) if current_user else None

    def _execute_worker():
        worker_db = SessionLocal()
        try:
            res = run_agent(
                task,
                attachment_type=attachment_type,
                task_id=task_id,
                history=history,
                initial_key_facts=initial_key_facts,
                user_id=user_id_str,
                vault_files=parsed_vault_files or None,
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

                        c.updated_at = func.now()
                        worker_db.commit()
                except Exception as exc:
                    print(f"[ERROR] Worker failed DB persist: {exc}", flush=True)

            # Always cache state snapshot and persist AgentRun for task resumption
            _AGENT_RUNS_CACHE[task_id] = res.get("state_snapshot", {})
            try:
                c_uuid = uuid.UUID(chat_db_id) if chat_db_id else None
                ar = worker_db.query(AgentRun).filter(AgentRun.task_id == task_id).first()
                if not ar:
                    ar = AgentRun(
                        id=uuid.uuid4(),
                        chat_id=c_uuid,
                        task_id=task_id,
                        status=res.get("status", "complete"),
                        state_snapshot=res.get("state_snapshot", {}),
                    )
                    worker_db.add(ar)
                else:
                    if c_uuid:
                        ar.chat_id = c_uuid
                    ar.status = res.get("status", "complete")
                    ar.state_snapshot = res.get("state_snapshot", {})
                    ar.updated_at = func.now()
                worker_db.commit()
            except Exception as exc:
                print(f"[ERROR] Worker failed to persist AgentRun: {exc}", flush=True)

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
    log_gateway("POST /run/{task_id}/reply", task_id, f"Reply: '{_truncate(req.reply, 65)}'")
    agent_run = db.query(AgentRun).filter(AgentRun.task_id == task_id).first()
    snapshot = None
    if agent_run and agent_run.state_snapshot:
        snapshot = dict(agent_run.state_snapshot)
    if not snapshot and task_id in _AGENT_RUNS_CACHE:
        snapshot = dict(_AGENT_RUNS_CACHE[task_id])

    if not snapshot:
        raise HTTPException(status_code=404, detail="No resume snapshot available for this run")

    snapshot["resumed"] = True
    snapshot["status"] = "executing"
    snapshot["clarify_question"] = None
    snapshot["operator_reply"] = req.reply

    user_id_str = str(current_user.id) if current_user else None
    res = run_agent(
        task=req.reply,
        task_id=task_id,
        resume_state=snapshot,
        user_id=user_id_str,
    )


    _AGENT_RUNS_CACHE[task_id] = res.get("state_snapshot", {})

    if agent_run:
        agent_run.status = res.get("status", "complete")
        agent_run.state_snapshot = res.get("state_snapshot", {})
        agent_run.updated_at = func.now()

    chat = None
    if agent_run and agent_run.chat_id:
        chat = db.query(Chat).filter(Chat.id == agent_run.chat_id).first()
    elif req.chat_id:
        try:
            chat = db.query(Chat).filter(Chat.id == uuid.UUID(req.chat_id)).first()
        except Exception:
            chat = None

    if chat:
        user_msg = Message(
            id=uuid.uuid4(),
            chat_id=chat.id,
            role="user",
            content=req.reply,
            meta={"clarification_reply": True, "task_id": task_id},
        )
        db.add(user_msg)

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
def assign_model(req: ModelAssignRequest, current_user: User = Depends(require_role('admin'))):
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
def delete_model_endpoint(model_name: str, current_user: User = Depends(require_role('admin'))):
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
def audit(
    task_id: Optional[str] = None,
    user_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """Returns audit events. Admin/auditor can optionally view another user's events via ?user_id=."""
    target_user_id = str(current_user.id)
    if user_id and current_user.role in ('admin', 'auditor'):
        target_user_id = user_id
        # Audit the admin override for viewing another user's log
        if user_id != str(current_user.id):
            log_event(
                event_type="admin_override",
                actor=str(current_user.id),
                summary=f"Admin/auditor '{current_user.name}' viewed audit log of user {user_id}",
                metadata={"action": "view_audit_log", "target_user_id": user_id},
                external_calls=0,
                user_id=str(current_user.id),
            )
    return {"events": read_events(user_id=target_user_id, task_id=task_id)}


@app.get("/audit/verify")
def verify_audit_chain_endpoint(
    user_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """Verifies cryptographic SHA-256 hash-chain integrity of the audit log."""
    target_user_id = str(current_user.id)
    if user_id and current_user.role in ('admin', 'auditor'):
        target_user_id = user_id

    result = verify_chain(user_id=target_user_id)
    return result



class ApprovalRequest(BaseModel):
    decision: str
    edited_content: Optional[Any] = None


@app.get("/approvals/count")
def get_approvals_count_endpoint(
    current_user: User = Depends(require_role("approver", "admin", "auditor")),
    db: Session = Depends(get_db),
):
    """Returns the count of pending approvals awaiting review for the user's role and department."""
    return {"pending_count": get_pending_approvals_count(current_user, db)}


@app.get("/approvals/pending")
def get_pending_approvals_endpoint(
    current_user: User = Depends(require_role("approver", "admin")),
    db: Session = Depends(get_db),
):
    """Lists pending approvals scoped to the user's department (or all for admin)."""
    return list_pending_approvals_db(current_user, db)


@app.get("/approvals/history")
def get_approval_history_endpoint(
    current_user: User = Depends(require_role("approver", "admin", "auditor")),
    db: Session = Depends(get_db),
):
    """Lists past resolved approvals with unified diffs, decisions, and requester details."""
    return list_approval_history_db(current_user, db)


@app.get("/approval/{task_id}")
def get_approval_endpoint(task_id: str):
    record = get_approval(task_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"No approval record found for task '{task_id}'.")
    return record


@app.post("/approval/{task_id}")
def post_approval_endpoint(
    task_id: str,
    req: ApprovalRequest,
    current_user: User = Depends(require_role("approver", "admin")),
    db: Session = Depends(get_db),
):
    log_gateway("POST /approval/{task_id}", task_id, f"Decision: '{req.decision}' by {current_user.email} ({current_user.role}/{current_user.department})")
    record = get_approval(task_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"No approval record found for task '{task_id}'.")

    decision = req.decision.strip().lower()
    if decision not in {"approve", "reject", "edit"}:
        raise HTTPException(status_code=400, detail="Decision must be 'approve', 'reject', or 'edit'.")

    # Department-scoped approval routing:
    # An approver can only decide approvals for their department (or general tasks)
    task_dept = record.get("department", "general")
    if current_user.role == "approver" and task_dept and task_dept != "general" and current_user.department != task_dept:
        raise HTTPException(
            status_code=403,
            detail=f"Approver from department '{current_user.department}' is not authorized to decide approvals for department '{task_dept}'.",
        )

    try:
        resolved = resolve_approval(task_id, decision=decision, approver_user=current_user, edited_content=req.edited_content)
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))

    if decision == "reject":
        try:
            agent_run = db.query(AgentRun).filter(AgentRun.task_id == task_id).first()
            if agent_run:
                agent_run.status = "rejected"
                agent_run.updated_at = func.now()
            msgs = db.query(Message).filter(Message.role == "assistant").order_by(Message.created_at.desc()).limit(30).all()
            for m in msgs:
                if m.meta and m.meta.get("task_id") == task_id:
                    meta = dict(m.meta or {})
                    meta["approval_outcome"] = {
                        "rejected": True,
                        "decision": "reject",
                        "message": "Document generation rejected by operator. No file generated.",
                    }
                    m.meta = meta
                    break
            db.commit()
        except Exception as exc:
            print(f"[WARN] Failed to persist rejection in DB: {exc}", flush=True)

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

    try:
        agent_run = db.query(AgentRun).filter(AgentRun.task_id == task_id).first()
        if agent_run:
            agent_run.status = "complete"
            agent_run.updated_at = func.now()
        msgs = db.query(Message).filter(Message.role == "assistant").order_by(Message.created_at.desc()).limit(30).all()
        for m in msgs:
            if m.meta and m.meta.get("task_id") == task_id:
                meta = dict(m.meta or {})
                meta["approval_outcome"] = {
                    "approved": True,
                    "decision": decision,
                    "filename": filename,
                    "file_path": str(file_path),
                    "title": content_to_render.get("title") or filename,
                }
                m.meta = meta
                break
        db.commit()
    except Exception as exc:
        print(f"[WARN] Failed to persist approval outcome in DB: {exc}", flush=True)

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

    media_type = "application/octet-stream"
    if filename.endswith(".docx"):
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif filename.endswith(".xlsx"):
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif filename.endswith(".pptx"):
        media_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    elif filename.endswith(".csv"):
        media_type = "text/csv"
    elif filename.endswith(".json"):
        media_type = "application/json"

    return FileResponse(path=file_path, filename=filename, media_type=media_type)


@app.get("/knowledge/list")
def knowledge_list(current_user: User = Depends(get_current_user)):
    """Read-only: aggregates the existing user FAISS metadata.json into per-document chunk counts."""
    _, _, _, metadata_path, _ = get_user_paths(str(current_user.id))
    if not metadata_path.exists():
        return {"documents": [], "total_chunks": 0}

    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    except Exception as exc:
        return {"documents": [], "total_chunks": 0, "error": f"Metadata read error: {exc}"}

    counts: dict = {}
    for entry in metadata:
        name = entry.get("source_filename", "unknown")
        counts[name] = counts.get(name, 0) + 1

    documents = [{"filename": name, "chunk_count": count} for name, count in sorted(counts.items())]
    return {"documents": documents, "total_chunks": len(metadata)}


@app.post("/knowledge/upload")
def knowledge_upload(
    file: UploadFile = File(...),
    ingest: bool = Form(True),
    department: str = Form("general"),
    classification_level: str = Form("internal"),
    current_user: User = Depends(get_current_user),
):
    """Saves an uploaded document and (optionally) runs it through the existing
    Phase 4/7 ingestion pipeline for the authenticated user."""
    safe_name = Path(file.filename or "upload").name
    suffix = Path(safe_name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    user_id_str = str(current_user.id)
    uploads_dir, _, _, _, _ = get_user_paths(user_id_str)

    try:
        content = file.file.read()
        dest = uploads_dir / safe_name
        dest.write_bytes(content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {exc}")

    log_event(
        event_type="upload",
        actor="ui",
        summary=f"Uploaded '{safe_name}' ({len(content)} bytes), ingest={ingest}",
        metadata={"filename": safe_name, "bytes": len(content), "ingest": ingest, "file_path": str(dest)},
        external_calls=0,
        user_id=user_id_str,
    )

    if not ingest:
        return {
            "filename": safe_name,
            "file_path": str(dest),
            "ingested": False,
            "chunk_count": 0,
            "chunks_created": 0,
        }

    try:
        result = ingest_document(
            dest,
            user_id=user_id_str,
            department=department,
            classification_level=classification_level,
        )  # logs its own "document_ingested" audit event
        chunk_count = result.get("chunk_count", 0)
        return {
            "filename": safe_name,
            "file_path": str(dest),
            "ingested": True,
            "chunk_count": chunk_count,
            "chunks_created": chunk_count,
        }
    except ollama.OllamaError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Local embedding service error: {exc}",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Document ingestion error: {exc}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to ingest document into knowledge vault: {exc}",
        )


@app.delete("/knowledge/{filename:path}")
def knowledge_delete(filename: str, current_user: User = Depends(get_current_user)):
    """Deletes all chunks, embeddings, and BM25 index entries for a document and removes the file from disk for user."""
    safe_name = Path(filename).name
    user_id_str = str(current_user.id)
    try:
        res = delete_document(safe_name, user_id=user_id_str)
        if not res.get("success"):
            raise HTTPException(status_code=404, detail=res.get("message", "Document not found in vault."))
        return res
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete document: {exc}")



@app.get("/shield/status")
def shield_status():
    return {
        "monitor": get_monitor_summary(),
        "firewall": check_firewall_status(),
    }


@app.post("/shield/lockdown")
def shield_lockdown(elevate: bool = False, current_user: User = Depends(require_role('admin'))):
    result = enable_firewall_lockdown(elevate=elevate)
    return result


@app.post("/shield/unlock")
def shield_unlock(elevate: bool = False, current_user: User = Depends(require_role('admin'))):
    result = disable_firewall_lockdown(elevate=elevate)
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

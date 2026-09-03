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
from typing import Any, Optional, Union

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import config
from backend.audit.logbook import log_event, read_events
from backend.brain.agent import run_agent
from backend.engine import ollama, registry
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

app = FastAPI(title="KAVACH", description="Phase 10: Frontend UI + Sovereignty Proof + Agent Brain")

FRONTEND_DIR = config.PROJECT_ROOT / "frontend-react" / "dist"
UPLOADS_DIR = config.PROJECT_ROOT / "knowledge" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="assets")


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


@app.get("/")
def ui_root():
    """Serves the Phase 10 UI shell."""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/run")
def run(req: RunRequest):
    return run_agent(req.task, attachment_type=req.attachment_type, task_id=req.task_id)


@app.get("/models")
def models():
    reg = registry.load_registry()
    try:
        installed = ollama.list_models()
    except ollama.OllamaError as exc:
        installed = []
        return {"registry": reg, "installed": installed, "warning": str(exc)}
    return {"registry": reg, "installed": installed}


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

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
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend import config
from backend.audit.logbook import read_events
from backend.brain.agent import run_agent
from backend.engine import ollama, registry
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

app = FastAPI(title="KAVACH", description="Phase 9: Sovereignty Proof (Firewall + Connection Monitor) + Brain")


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

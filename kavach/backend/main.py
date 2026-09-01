"""main.py — FastAPI entry point. Wires the engine, agent brain, audit logbook, and download service."""

import os

# Strictly local: disable LangChain/LangSmith tracing and telemetry before anything
# that might read these at import time.
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGCHAIN_TRACING"] = "false"
os.environ["LANGCHAIN_ENDPOINT"] = ""
os.environ.pop("LANGCHAIN_API_KEY", None)
os.environ.pop("LANGSMITH_API_KEY", None)

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend import config
from backend.audit.logbook import read_events
from backend.brain.agent import run_agent
from backend.engine import ollama, registry

app = FastAPI(title="KAVACH", description="Phase 5: Word Document Writer + RAG + Audit + Brain")


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

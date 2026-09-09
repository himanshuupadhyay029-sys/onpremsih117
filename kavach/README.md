# KAVACH: Sovereign On-Premises Operations Assistant

**KAVACH** (सुरक्षा कवच / Shield) is a 100% offline, air-gapped autonomous AI assistant engineered for critical industrial infrastructure. Built for **Smart India Hackathon 2026 (Problem Statement SIH26117)** for **Mangalore Refinery and Petrochemicals Limited (MRPL)**, KAVACH addresses the strict operational demand for an intelligent assistant that runs entirely within an air-gapped perimeter with zero cloud LLM dependencies, verifiable isolation, and zero external data leakage.

The live system is a **multi-user operator console**: local Ollama models, a LangGraph Master Planner with self-correction and clarification, a FAISS Knowledge Vault of SOPs, an isolated Docker sandbox (Python / JavaScript / C), OCR and vision, a deterministic calculator, a formal `.docx` generator with a human approval gate, JWT auth with PostgreSQL chat persistence, and a real-time Shield monitor proving KAVACH itself makes no external calls.

Full architecture: [`KAVACH_CONTEXT.md`](KAVACH_CONTEXT.md). Developer quickstart: [`startup.md`](startup.md).

---

## 1. Prerequisites

Before installing KAVACH, ensure the host meets the following requirements:

- **Operating System:** Windows 10 or Windows 11 (64-bit) is the supported demo host (Shield uses Windows Defender Firewall). Linux/macOS can run the API, Postgres, and sandbox without the Windows lockdown path.
- **Python 3.11 specifically:** Do **not** use Python 3.12, 3.13, or 3.14. FAISS CPU wheels, image libraries, and pytesseract bindings are tested on 3.11.
- **Node.js 18+** with `npm` (for the React operator console in development).
- **Ollama:** Installed and running locally ([ollama.com](https://ollama.com)).
- **Docker Desktop:** Installed and **RUNNING** (WSL2 backend on Windows). Required for PostgreSQL **and** the isolated code sandbox (`--network none`).
- **Tesseract OCR:** Installed on Windows (e.g. UB-Mannheim at `C:\Program Files\Tesseract-OCR\tesseract.exe`).

---

## 2. Step-by-Step Setup Guide

Follow these steps in a PowerShell terminal from the `kavach/` directory.

### Step 1: Create and Activate Python 3.11 Virtual Environment
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```
*(If PowerShell restricts script execution, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first).*

### Step 2: Install Locked Dependencies
```powershell
pip install -r requirements.txt
```

### Step 3: Pull the Required Local Ollama Models
Role assignments live in `backend/models.json`. Ensure Ollama is running, then pull:

```powershell
# Embedding (Knowledge Vault RAG)
ollama pull nomic-embed-text:latest

# Code generation & sandbox self-correction
ollama pull granite4.1:3b

# Reasoning, planning, general chat, drafting, vision & claim verification
ollama pull gemma3:4b
```

Any model role can be changed in `backend/models.json` or hot-swapped from the Model Settings screen in the operator console. There is **no** dedicated 1.5B router model; routing is rule-based.

### Step 4: Start PostgreSQL and Apply Migrations
Postgres is mapped to host port **5434** (container 5432) to avoid colliding with a local Postgres install.

```powershell
docker compose up -d postgres
python -m alembic upgrade head
```

Connection defaults: `127.0.0.1:5434` / database `kavach_db` / user `kavach` / password `kavach_secret`.

### Step 5: Pre-pull Sandbox Docker Images
```powershell
docker pull python:3.11-slim
docker pull node:20-slim
docker pull gcc:13-slim
```

### Step 6: Verify Services
```powershell
ollama list
docker ps
```
Confirm `kavach_postgres` is healthy and the four Ollama models are present.

---

## 3. Running KAVACH

### Backend (required)
```powershell
.\run_backend.ps1
```
or:
```powershell
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

`run_backend.ps1` checks Admin elevation (needed for firewall lockdown), waits for Postgres on **5434**, runs Alembic, then starts Uvicorn.

- API docs: `http://127.0.0.1:8000/docs`
- Operator UI (React `frontend-react/dist/`): **`http://127.0.0.1:8000`**
- Legacy vanilla UI: `http://127.0.0.1:8000/vanilla`

### React frontend (development)
If you are iterating on the UI, run Vite separately (proxies API calls to port 8000):

```powershell
cd frontend-react
npm install
npm run dev
```

Open **`http://localhost:3000`**. Docker Compose can also serve the frontend on host port **5173**.

The React shell loads Inter and Source Serif 4 from Google Fonts when a network is available; on a fully air-gapped host those requests fail and the UI falls back to system fonts.

---

## 4. First-Time Setup: Knowledge Vault Ingestion

To enable grounded RAG search and citation, ingest SOPs into the Knowledge Vault.

**From the UI:** open Chat / Knowledge Vault, upload `.pdf`, `.md`, `.txt`, `.docx`, or image scans, then ingest. The server chunks content, embeds with `nomic-embed-text`, and writes `knowledge/faiss_index/`.

**From the CLI** (demo corpus):
```powershell
python scripts/ingest_docs.py testdata
```

---

## 5. What the Operator Console Includes

| Screen | Purpose |
| :--- | :--- |
| **Chat** | Persistent chats (when signed in), live SSE agent trace, clarification, approval, interactive code cards |
| **Knowledge Vault** | Upload and ingest SOPs into FAISS |
| **Audit Log** | Append-only JSONL events (`outputs/audit_log.jsonl`) |
| **Model Settings** | Assign roles, pull / cancel / delete Ollama models |
| **Shield bar** | Live WebSocket connection classification + Windows firewall lockdown |

Guests can run the agent without an account; login (httpOnly JWT cookie) persists chats and messages in PostgreSQL.

---

## 6. Known Limitations & Technical Realities

To maintain complete engineering credibility during review, KAVACH documents its practical constraints plainly:

1. **Firewall lockdown requires Administrator elevation.** `POST /shield/lockdown` uses Windows Defender Firewall (`netsh advfirewall`). Start Uvicorn from a PowerShell opened with **Run as Administrator**.
2. **Tesseract is the primary OCR engine.** PaddleOCR was tested and hits a fatal oneDNN crash on Windows. This is a deliberate fallback, not an incomplete install.
3. **OCR / vision quality depends on scan resolution.** Crisp printed SOPs reach 70–95% OCR confidence. Degraded handwriting or complex P&IDs receive assisted understanding, not certified engineering interpretation.
4. **Audit log is append-only JSONL, not SHA-256 hash-chained.** Events record `external_calls`; there is no prev-hash chain in `backend/audit/logbook.py`.
5. **Pending document approvals are in-memory** and are lost if the FastAPI process restarts.
6. **`GET /models/info` is not air-gapped.** Inspecting Ollama library tags contacts `ollama.com`. Model pull itself talks only to the local Ollama daemon.
7. **No user RBAC.** “Operator” / “supervisor” is UX language. Chat history is isolated per account; vault, audit, models, and shield APIs are not role-gated.
8. **Google Fonts on the React shell.** Offline hosts skip the CDN; the UI still works.

---

## 7. Project Structure

```
kavach/
├── backend/
│   ├── auth/            # JWT register / login / cookie session
│   ├── audit/           # Append-only JSONL logbook
│   ├── brain/           # LangGraph Master Planner, router, event_bus
│   ├── chat/            # Persistent chat API
│   ├── db/              # SQLAlchemy models & session (Postgres)
│   ├── engine/          # Ollama client & models.json registry
│   ├── guard/           # Claim verify + human approval gate
│   ├── shield/          # Firewall lockdown & live socket monitor
│   ├── tools/           # search, writer, code, sandbox, calc, ocr, vision
│   ├── vault/           # FAISS ingest + retrieve
│   ├── config.py
│   ├── main.py
│   └── models.json      # reasoning / code / vision / embedding roles
├── frontend-react/      # Primary React 18 + Vite operator console
├── frontend/            # Legacy vanilla SPA (/vanilla)
├── knowledge/           # uploads/ and faiss_index/
├── migrations/          # Alembic 001, 002
├── outputs/             # .docx, audit_log.jsonl, sovereignty_session.jsonl
├── scripts/             # ingest_docs.py, generate_synthetic_scans.py
├── testdata/            # Demo SOPs
├── docker-compose.yml   # postgres (+ optional frontend)
├── requirements.txt
├── run_backend.ps1
├── startup.md
├── KAVACH_CONTEXT.md
└── README.md
```

---

## 8. Context & Acknowledgements

Developed for **Smart India Hackathon (SIH) 2026** — Problem Statement **SIH26117** for **Mangalore Refinery and Petrochemicals Limited (MRPL)**.

KAVACH demonstrates that critical industrial infrastructure can deploy a high-capability autonomous assistant without sending a single operational byte to a public cloud LLM.

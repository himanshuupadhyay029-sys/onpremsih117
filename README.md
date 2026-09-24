# KAVACH: Sovereign On-Premises Operations Assistant

**KAVACH** (सुरक्षा कवच / Shield) is a 100% offline, air-gapped autonomous AI assistant engineered for critical industrial infrastructure. Built for **Smart India Hackathon 2026 (Problem Statement SIH26117)** for **Mangalore Refinery and Petrochemicals Limited (MRPL)**, KAVACH addresses the strict operational demand for an intelligent assistant that runs entirely within an air-gapped perimeter with zero cloud LLM dependencies, verifiable cryptographic isolation, and zero external data leakage.

The live system is a **multi-user operator console**: local Ollama models, a LangGraph Master Planner with self-correction and clarification, a FAISS Knowledge Vault of SOPs, an isolated Docker sandbox (Python / JavaScript / C), OCR and multimodal vision, a deterministic calculator, a formal `.docx` generator with a human approval gate, JWT authentication with PostgreSQL chat persistence, and a real-time Shield monitor proving KAVACH makes zero external network calls.

---

## 1. Prerequisites

Before installing KAVACH, ensure your Windows host meets the following requirements:

- **Operating System:** Windows 10 or Windows 11 (64-bit) is the primary supported host (Shield uses Windows Defender Firewall).
- **Python 3.11 specifically:** Python 3.11 is required (do **not** use Python 3.12, 3.13, or 3.14). *Why:* Critical compiled C++ extensions (FAISS CPU wheels, image processing libraries, and pytesseract bindings) are stable and tested on 3.11.
- **Node.js 18+** with `npm` (for the React operator console).
- **Ollama:** Installed and running locally ([ollama.com](https://ollama.com)).
- **Docker Desktop:** Installed and **RUNNING** on Windows with the WSL2 backend. *Why:* Required for PostgreSQL **and** the isolated code execution sandbox (`--network none`).
- **Tesseract OCR:** Installed on Windows (e.g. from UB-Mannheim at `C:\Program Files\Tesseract-OCR\tesseract.exe`).

---

## 2. Step-by-Step Setup Guide

Follow these exact steps in order in a standard PowerShell terminal:

### Step 1: Clone Repository & Enter Directory
```powershell
git clone <repository-url>
cd onpremsih117/kavach
```

### Step 2: Create and Activate Python 3.11 Virtual Environment
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```
*(If PowerShell restricts script execution, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first).*

### Step 3: Install Locked Dependencies
```powershell
pip install -r requirements.txt
```

### Step 4: Pull Required Local Ollama Models
Ensure Ollama is running, then pull the required models:
```powershell
# 1. Embedding (Knowledge Vault RAG)
ollama pull nomic-embed-text:latest

# 2. Code Generation & Sandbox Execution
ollama pull granite4.1:3b

# 3. Reasoning, Planning, Drafting, Vision & Verification
ollama pull gemma3:4b
```
*(Model roles can also be customized in `backend/models.json` or hot-swapped from the Model Settings screen in the operator console).*

### Step 5: Start PostgreSQL & Apply Migrations
Postgres runs mapped to host port **5434** (container 5432) to avoid collision with any existing local PostgreSQL instances:
```powershell
docker compose up -d postgres
python -m alembic upgrade head
```

### Step 6: Pre-pull Sandbox Docker Images
Pre-pull the lightweight, network-isolated execution images:
```powershell
docker pull python:3.11-slim
docker pull node:20-slim
docker pull gcc:13-slim
```

### Step 7: Verify Services
```powershell
ollama list
docker ps
```
Confirm `kavach_postgres` is healthy and the local Ollama models are present.

---

## 3. Running KAVACH

### Backend Server
Run the startup script:
```powershell
.\run_backend.ps1
```
or manually:
```powershell
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

- **API Documentation (Swagger UI):** `http://127.0.0.1:8000/docs`
- **Backend Health / API Root:** `http://127.0.0.1:8000`

### React Operator Console
In a separate terminal:
```powershell
cd frontend-react
npm install
npm run dev
```
Open **`http://localhost:5173`** (or **`http://localhost:3000`** depending on port config) to access the operator console.

---

## 4. Knowledge Vault Ingestion

To enable grounded RAG search and citation, ingest SOPs into the Knowledge Vault:

- **Via Operator Console UI:** Navigate to **Knowledge Vault**, upload documents (`.pdf`, `.md`, `.txt`, `.docx`, or image scans), and click **Ingest into Vault**. The server chunks content, generates embeddings locally using `nomic-embed-text`, and stores them in offline FAISS indexes.
- **Via CLI (Batch Demo Corpus):**
  ```powershell
  python scripts/ingest_docs.py testdata
  ```

---

## 5. What the Operator Console Includes

| Screen / Feature | Purpose |
| :--- | :--- |
| **Chat Console** | Multi-turn chat with persistent database storage, live SSE execution streaming, code cards, and clarification prompts |
| **Knowledge Vault** | Multi-file document upload, chunking, and local FAISS vector store indexing |
| **Audit Log** | Immutable append-only audit trail recording user and agent actions (`outputs/audit_log.jsonl`) |
| **Model Settings** | Assign model roles (Reasoning, Coding, Vision, Embedding) and pull local models |
| **Shield Bar & Lockdown** | Real-time socket monitor displaying internal vs external connections and one-click Windows firewall lockdown |
| **Human Approval Gate** | High-impact actions and deliverables require supervisor sign-off before execution |

---

## 6. Known Limitations & Technical Realities

To maintain complete engineering credibility during review, KAVACH documents its practical constraints:

1. **Firewall Lockdown Requires Administrator Elevation:** `POST /shield/lockdown` uses Windows Defender Firewall (`netsh advfirewall`). Start the server terminal as **Administrator** to activate this feature.
2. **Tesseract is the Primary OCR Engine:** PaddleOCR encounters an upstream oneDNN bug on Windows. Tesseract OCR is the reliable, documented OCR fallback.
3. **OCR / Vision Quality:** Crisp printed SOPs reach 70–95% accuracy. Complex engineering schematics receive assisted AI interpretation rather than legally certified engineering analysis.
4. **Audit Trail:** Events are logged in an append-only JSONL format recording process signatures and timestamps.
5. **Air-Gapped Operation:** The core system is completely offline. Any external font or CDN fallback gracefully drops to standard local OS fallbacks when network access is severed.

---

## 7. Project Structure

```
onpremsih117/
├── kavach/
│   ├── backend/
│   │   ├── audit/           # Append-only JSONL logbook
│   │   ├── auth/            # JWT authentication & session management
│   │   ├── brain/           # LangGraph Master Planner, router, event_bus
│   │   ├── chat/            # Chat routes & session persistence
│   │   ├── db/              # SQLAlchemy database models & session
│   │   ├── engine/          # Local Ollama client & model registry
│   │   ├── guard/           # Claim verification & human approval gate
│   │   ├── shield/          # Firewall lockdown & socket monitor
│   │   ├── tools/           # search, writer, code, sandbox, calc, ocr, vision
│   │   ├── vault/           # FAISS ingest, retrieval & reranking
│   │   ├── config.py        # Central configuration
│   │   ├── main.py          # FastAPI application entrypoint
│   │   └── models.json      # Model role assignments
│   ├── frontend-react/      # React 18 + Vite Operator Console
│   ├── frontend/            # Vanilla HTML/JS interface
│   ├── knowledge/           # FAISS index and uploaded document storage
│   ├── migrations/          # Alembic database migrations
│   ├── outputs/             # Generated deliverables, logs, and temp artifacts
│   ├── scripts/             # Ingestion and helper automation scripts
│   ├── testdata/            # Sample SOP documents and test scans
│   ├── docker-compose.yml   # PostgreSQL service definition
│   ├── requirements.txt     # Python dependencies
│   └── run_backend.ps1      # PowerShell backend startup script
├── .gitignore
└── README.md
```

---

## 8. Context & Acknowledgements

Developed for **Smart India Hackathon (SIH) 2026** — Problem Statement **SIH26117** for **Mangalore Refinery and Petrochemicals Limited (MRPL)**.

KAVACH demonstrates that critical industrial infrastructure can deploy a high-capability autonomous AI assistant without sending a single operational byte to a public cloud LLM.

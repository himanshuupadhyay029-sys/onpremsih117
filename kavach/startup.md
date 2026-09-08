# 🛡️ KAVACH — Quickstart & Developer Setup Guide

Welcome to **KAVACH**, an on-premises, sovereign industrial operations AI assistant. KAVACH operates in an air-gapped / offline environment with local LLM models (via Ollama), isolated Docker code execution sandboxes, FAISS vector search, and a PostgreSQL persistence layer.

This guide contains everything required for any team member to set up, configure, and run KAVACH from scratch with zero confusion.

---

## 🏗️ Architecture & Component Overview

| Component | Technology | Default Port / Location | Purpose |
| :--- | :--- | :--- | :--- |
| **Backend API** | FastAPI, Python 3.11, LangGraph | `http://localhost:8000` | REST API, stateful agent loop, router, audit logger |
| **Frontend UI** | React 18, Vite | `http://localhost:3000` | Glassmorphic operator chat UI, code sandbox, model manager |
| **Local LLM Engine** | Ollama | `http://localhost:11434` | Offline model inference for reasoning, code, vision, and embeddings |
| **Database** | PostgreSQL 16 (Docker) | `localhost:5434` (mapped to `5432`) | Chats, messages, user accounts, and session data |
| **Code Sandbox** | Docker (isolated, `--network=none`) | Ephemeral containers | Safe execution of Python, JavaScript, and C scripts |
| **Knowledge Vault** | FAISS + Nomic Embed Text | `knowledge/faiss_index/` | Local document RAG search with grounded citations |
| **OCR Engine** | Tesseract OCR + PyPDF | Local binary / pip | Image text and scanned document transcription |
| **Document Writer** | python-docx | `outputs/` | Word (.docx) formal reports & SOP generator |

> ⚠️ **Important Note on Port Changes (PostgreSQL: 5434)**:
> In earlier versions, PostgreSQL was mapped to port `5432` or `5433`. To eliminate port conflicts on developer workstations that already have a local PostgreSQL service running, the host port is mapped to **`5434`** (container port remains `5432`).
> This change is synchronized across:
> - `docker-compose.yml` (`ports: - "5434:5432"`)
> - `backend/db/session.py` (default `DATABASE_URL` uses `127.0.0.1:5434`)
> - `alembic.ini` (`sqlalchemy.url` uses port `5434`)
> - `run_backend.ps1` (TCP healthcheck checks port `5434`)
>
> If you connect with an external database GUI (DBeaver, pgAdmin), use:
> `Host: 127.0.0.1` | `Port: 5434` | `Database: kavach_db` | `User: kavach` | `Password: kavach_secret`
>
> **Frontend Ports**:
> - Running locally via `npm run dev`: serves on `http://localhost:3000` (configured in `frontend-react/vite.config.js`).
> - Running via Docker Compose (`docker compose up frontend`): mapped to host port `5173:5173`.

---

## 📋 Prerequisites

Before starting, ensure the following software is installed on your workstation:

1. **Operating System**: Windows 10/11, macOS, or Linux.
2. **Python**: Version `3.11+` installed and added to `PATH`.
3. **Node.js**: Version `18+` or `20+` with `npm` installed.
4. **Docker Desktop**: Installed and running (required for PostgreSQL and isolated code execution).
5. **Ollama**: Installed from [ollama.com](https://ollama.com) and running.
6. *(Optional for OCR)* **Tesseract OCR**:
   - **Windows**: Install [Tesseract Windows Installer](https://github.com/UB-Mannheim/tesseract/wiki) to default path `C:\Program Files\Tesseract-OCR\tesseract.exe`.
   - **Linux**: `sudo apt-get install tesseract-ocr`.

---

## 🚀 Step-by-Step Setup Instructions

### Step 1: Open Terminal & Navigate to Project Root
Open PowerShell (recommended) or terminal in the project directory:
```powershell
cd c:\Users\Asus\Documents\Kavach_1\onpremsih117\kavach
```

---

### Step 2: Set Up Python Virtual Environment & Dependencies

1. **Create virtual environment**:
   ```powershell
   python -m venv .venv
   ```

2. **Activate the virtual environment**:
   - **Windows PowerShell**:
     ```powershell
     .\.venv\Scripts\Activate.ps1
     ```
     *(If you get an execution policy error, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first)*
   - **Linux / macOS**:
     ```bash
     source .venv/bin/activate
     ```

3. **Install Python dependencies**:
   ```powershell
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

---

### Step 3: Pull Ollama Local Models

Make sure the Ollama service is running (`ollama serve` or Ollama background icon in system tray).

KAVACH maps specific models to task roles in `backend/models.json`:
```json
{
  "reasoning": "qwen2.5:7b-instruct",
  "code": "qwen2.5-coder:3b",
  "vision": "qwen2.5vl:3b",
  "embedding": "nomic-embed-text:latest"
}
```

Pull the required models in your terminal:
```powershell
# 1. Embedding model (Required for Knowledge Vault RAG)
ollama pull nomic-embed-text:latest

# 2. Specialist Code Model (Fast, accurate code generation)
ollama pull qwen2.5-coder:3b

# 3. Primary Reasoning / Document Model (Decomposer & Writer)
ollama pull qwen2.5:7b-instruct

# 4. Multimodal Vision Model (For diagrams, schematics & photos)
ollama pull qwen2.5vl:3b
```

> **💡 Low VRAM / CPU-Only Machines:**
> If your machine has limited VRAM (less than 8GB), you can switch `reasoning` in `backend/models.json` to `qwen2.5:3b` or use 4-bit quantizations (e.g. `qwen2.5:7b-instruct-q4_K_M`).

---

### Step 4: Start PostgreSQL Database & Apply Migrations

1. **Launch PostgreSQL via Docker Compose**:
   ```powershell
   docker compose up -d postgres
   ```
   *This starts the PostgreSQL 16 container exposed on host port `5434` with user `kavach` and password `kavach_secret`.*

2. **Verify container status**:
   ```powershell
   docker ps
   ```
   Ensure `kavach_postgres` shows `(healthy)`.

3. **Apply Database Migrations with Alembic**:
   ```powershell
   python -m alembic upgrade head
   ```
   *This creates all necessary database tables: `chats`, `messages`, and `users`.*

---

### Step 5: Pre-pull Docker Sandbox Images (For Code Execution)

KAVACH executes code inside completely isolated Docker containers with `--network=none` and strict RAM/CPU limits. Pre-pull the runtime images so scripts don't timeout while downloading images:

```powershell
docker pull python:3.11-slim
docker pull node:20-slim
docker pull gcc:13-slim
```

---

### Step 6: Ingest Documents into Knowledge Vault (FAISS RAG)

To populate the Knowledge Vault with initial Standard Operating Procedures (SOPs) and policies from `testdata/`:

```powershell
python scripts/ingest_docs.py testdata
```

This chunks the documents, embeds them using `nomic-embed-text`, and generates the local vector store under `knowledge/faiss_index/`.

---

### Step 7: Launch the FastAPI Backend

You can launch the backend using either the automated PowerShell runner or standard Uvicorn command:

#### Option A: Automated PowerShell Script
```powershell
.\run_backend.ps1
```
*(Runs elevation check, verifies PostgreSQL on port 5434, runs alembic migrations, and launches Uvicorn on port 8000).*

#### Option B: Direct Python / Uvicorn Command
```powershell
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

Verify backend is healthy by opening:
- API Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
- Healthcheck: [http://localhost:8000/models](http://localhost:8000/models)

---

### Step 8: Launch the React Frontend

Open a new terminal window:

```powershell
cd c:\Users\Asus\Documents\Kavach_1\onpremsih117\kavach\frontend-react

# Install dependencies (only required on first setup)
npm install

# Start development server
npm run dev
```

Open your browser and navigate to:
👉 **[http://localhost:3000](http://localhost:3000)** (or port 5173 if running without port override)

---

## 🎯 How Key Features Work

### 1. Dynamic Model Switching & Master Planner
- When you send a compound query (e.g. *"Write a python code to calculate 50*10 and then create a document for this code"*):
  1. The **Master Planner** decomposes the request into ordered sub-tasks: `[code]` then `[document]`.
  2. The **Router** switches the active model dynamically:
     - Step 1 routes to `qwen2.5-coder:3b` (role: `code`).
     - Step 2 routes to `qwen2.5:7b-instruct` (role: `reasoning`).
  3. **Terminal Logging**: Your terminal will print real-time events:
     ```text
     [Planner] [OK] Master Plan established (2 sub-task(s)):
        * Step 1: [code] Write Python script...
        * Step 2: [document] Create formal document...
     [Router] [SWITCH] Step 1/2: Routing to 'code' | Active model switched to 'qwen2.5-coder:3b' (code)
     [Executor] [RUN] Executing Sub-Task 1/2 [code] with model 'qwen2.5-coder:3b'...
     [Router] [SWITCH] Step 2/2: Routing to 'document' | Active model switched to 'qwen2.5:7b-instruct' (reasoning)
     [Agent] [COMPLETE] Task complete. Models engaged: qwen2.5-coder:3b -> qwen2.5:7b-instruct
     ```
  4. **Frontend Visibility**:
     - The message header shows: `Models · qwen2.5-coder:3b → qwen2.5:7b-instruct`.
     - Each step row displays an active model chip badge (`qwen2.5-coder:3b` or `qwen2.5:7b-instruct`).

### 2. Interactive Docker Code Sandbox
- The generated code block provides:
  - **In-Place Code Editing**: Modify the code directly in the browser.
  - **Interactive Stdin Drawer**: Provide custom input text to test `input()` / stdin without code changes.
  - **Execute in Sandbox**: Runs directly inside the isolated Docker container (`python:3.11-slim`) and streams stdout/stderr back in milliseconds.
  - **Consolidated Revisions Stepper**: If self-correction was needed, prior revisions are cleanly stacked in a stepper (`Revision 1`, `Latest`) without cluttering the screen.

### 3. Document Writer & Download
- The agent automatically compiles Word documents (`.docx`) into the `outputs/` directory.
- For code documentation and routine tasks, a download card with the file name and size appears immediately on the frontend.
- For high-risk industrial SOP generation lacking vault sources, the **Human Approval Gate** pauses generation and presents an Approval/Edit/Reject card.

### 4. Model Settings & Downloader Screen
- Click **Model Settings** in the top navigation bar to:
  - See all installed models and their active role assignments.
  - Reassign which model handles `reasoning`, `code`, `vision`, or `embedding`.
  - Search any model from the Ollama library, inspect available quantizations (e.g. `q4_K_M`, `q8_0`, `fp16`), and stream model download progress with an instant **Cancel Pull** button.

---

## 🧪 Testing Everything Works

Run the included test suite to verify your setup:

```powershell
# 1. Test database & chat session pipeline
.\.venv\Scripts\python.exe test_chat_pipeline.py

# 2. Test Docker sandbox code execution (Python, JS, C)
.\.venv\Scripts\python.exe test_code_sandbox.py

# 3. Test multi-step Master Planner decomposition
.\.venv\Scripts\python.exe test_master_planner.py

# 4. Test Knowledge Vault search and citations
.\.venv\Scripts\python.exe test_search_improvements.py
```

---

## 🛠️ Common Troubleshooting FAQ

### Q1: `ModuleNotFoundError: No module named 'langgraph'` or other imports
**Cause**: The command ran using system Python instead of the virtual environment.  
**Fix**: Always run using `.\.venv\Scripts\python.exe <script>` or ensure your terminal shows `(.venv)`.

### Q2: `PostgreSQL not reachable at 127.0.0.1:5434`
**Cause**: Docker Desktop is not running or the container is stopped.  
**Fix**:
1. Open Docker Desktop.
2. Run: `docker compose up -d postgres`.
3. Check container logs: `docker compose logs postgres`.

### Q3: `UnicodeEncodeError: 'charmap' codec can't encode character...`
**Cause**: Windows PowerShell default console encoding (CP1252).  
**Fix**: Handled automatically by KAVACH's `_log_terminal` fallback. You can also run `chcp 65001` in your console to enable full UTF-8 support.

### Q4: Code sandbox fails with `Docker daemon not responding` or container timeout
**Cause**: Docker Desktop is not started or sandbox image is downloading for the first time.  
**Fix**: Ensure Docker Desktop is running and run `docker pull python:3.11-slim`.

### Q5: `ollama: connection refused` or `model not found`
**Cause**: Ollama is not running on port 11434, or the assigned model was not pulled.  
**Fix**:
1. Run `ollama list` to see installed models.
2. Ensure model names match `backend/models.json`.
3. Run `ollama pull <model_name>` if missing.

---

## 📂 Key File & Folder Map

```text
kavach/
├── backend/
│   ├── brain/           # Agentic loop (agent.py, router.py, state.py)
│   ├── db/              # SQLAlchemy session & database models
│   ├── engine/          # Ollama client & models.json registry
│   ├── guard/           # Risk assessment & approval gate
│   ├── tools/           # Sandbox, calc, writer, ocr, vision, search
│   ├── vault/           # FAISS RAG vector store & document ingestion
│   ├── config.py        # Central directory paths & endpoints
│   ├── main.py          # FastAPI application routes
│   └── models.json      # Active model assignments per role
├── frontend-react/      # React 18 + Vite frontend
│   ├── src/components/  # MessageTurn, NewTaskScreen, ModelSettingsScreen
│   └── src/styles/      # index.css (Dark glassmorphic design system)
├── knowledge/           # FAISS index and persistent vault metadata
├── migrations/          # Alembic database migration scripts
├── outputs/             # Generated .docx documents and audit_log.jsonl
├── scripts/             # CLI helpers (ingest_docs.py)
├── testdata/            # Sample SOPs and test documents
├── docker-compose.yml   # PostgreSQL 16 container definition
├── requirements.txt     # Complete Python dependencies
├── run_backend.ps1      # Automated backend startup script
└── startup.md           # This setup guide
```

---

🛡️ **KAVACH Team** — Secure, air-gapped, sovereign operations.

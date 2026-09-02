# KAVACH: Sovereign On-Premises Operations Assistant

**KAVACH** (सुरक्षा कवच / Shield) is a 100% offline, air-gapped autonomous AI assistant engineered for critical industrial infrastructure. Built for **Smart India Hackathon 2026 (Problem Statement SIH26117)** for **Mangalore Refinery and Petrochemicals Limited (MRPL)**, KAVACH addresses the strict operational demand for an intelligent assistant that runs entirely within an air-gapped perimeter with zero cloud dependencies, verifiable cryptographic isolation, and zero external data leakage.

The system combines local LLMs, an agentic decision loop with self-correction, an indexed Knowledge Vault of standard operating procedures (SOPs), an isolated Docker code execution sandbox, OCR/multimodal vision, a deterministic mathematical calculator, a formal document generator, a human approval gate for high-stakes outputs, and a real-time network monitor providing mathematical proof of zero external calls.

---

## 1. Prerequisites

Before installing KAVACH, ensure your Windows host meets the following requirements:

- **Operating System:** Windows 10 or Windows 11 (64-bit).
- **Python 3.11 specifically:** Python 3.11 is required (do **not** use Python 3.12, 3.13, or 3.14). *Why:* Critical compiled C++ extensions (FAISS CPU wheels, image processing libraries, and pytesseract bindings) are stable and tested on 3.11.
- **Ollama:** Installed and running locally ([ollama.ai](https://ollama.ai)).
- **Docker Desktop:** Installed and **RUNNING** on Windows with the WSL2 backend. *Why:* Required specifically for the isolated code execution sandbox (`--network none`).
- **Tesseract OCR:** Installed on Windows (e.g. from UB-Mannheim at `C:\Program Files\Tesseract-OCR\tesseract.exe`).

---

## 2. Step-by-Step Setup Guide

Follow these exact steps in order in a standard PowerShell terminal:

### Step 1: Clone Repository & Enter Directory
```powershell
git clone <repository-url>
cd sih2026/kavach
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

### Step 4: Pull the 4 Required Local Ollama Models
Ensure Ollama is running, then pull each model role:
```powershell
# 1. Reasoning, Planning, Drafting & Claim Verification (~2.0 GB)
ollama pull qwen2.5:3b-instruct

# 2. Fast Intent Triage & Routing (~1.0 GB)
ollama pull qwen2.5:1.5b-instruct

# 3. Code Generation & Sandbox Self-Correction (~2.0 GB)
ollama pull qwen2.5-coder:3b

# 4. Multimodal Vision & Diagram Understanding (~1.8 GB)
ollama pull moondream:latest
```

### Step 5: Pull the Sandbox Docker Image
Pre-pull the lightweight, network-isolated execution image:
```powershell
docker pull python:3.11-slim
```

### Step 6: Verify Services are Active
```powershell
# Confirm Ollama models are present
ollama list

# Confirm Docker daemon is running
docker ps
```

---

## 3. Running KAVACH

Start the sovereign FastAPI server using Uvicorn:

```powershell
python -m uvicorn backend.main:app --reload --port 8000
```

Once started, open your web browser to:
**`http://127.0.0.1:8000`**

The web interface is 100% self-contained. It contains zero external CDNs, fonts, or scripts, ensuring full operation in completely air-gapped environments.

---

## 4. First-Time Setup: Knowledge Vault Ingestion

To enable grounded RAG search and citation, ingest your organization's SOPs and manuals into the Knowledge Vault:

1. Open the web interface at `http://127.0.0.1:8000`.
2. Click the **Knowledge Vault** tab in the navigation bar.
3. Upload your SOP documents (`.pdf`, `.md`, `.txt`, `.docx`, or `.png`/`.jpg` scans).
4. Click **Ingest into Vault**. The server extracts text, chunks content, generates embeddings locally, and indexes them into an offline FAISS vector store.

*(Alternatively, run the batch ingestion script: `python -m backend.vault.ingest`)*.

---

## 5. Known Limitations & Technical Realities

To maintain complete engineering credibility during review, KAVACH documents its practical constraints plainly:

1. **Firewall Lockdown Requires Administrator Elevation:**
   The API-triggered network lockdown feature (`POST /sovereignty/lockdown`) uses Windows Defender Firewall APIs (`netsh advfirewall`). Windows requires elevated permissions to add firewall rules. To use this feature, start the Uvicorn server from a PowerShell terminal opened with **"Run as Administrator"**.
2. **Tesseract as Primary OCR Engine (PaddlePaddle Windows oneDNN Bug):**
   PaddleOCR was initially tested but exhibits a severe upstream oneDNN compatibility crash on Windows (`oneDNN: The system cannot find the file specified`). KAVACH uses **Tesseract OCR (`pytesseract`)** as its primary, fully working OCR engine. This is a deliberate, documented architectural fallback.
3. **OCR / Vision Quality & Image Resolution:**
   OCR confidence and multimodal understanding depend on scan clarity and resolution. Crisp printed SOPs and digital inspection sheets achieve 70–95% confidence. Degraded hand-written notes or complex piping P&ID schematics receive "assisted understanding", not legally certified engineering interpretations.
4. **Planner Step-Count Variation:**
   While Phase 12 introduced soft ceilings and prompt tightening that keeps simple tasks between 1 and 3 steps, small local models (3B parameters) can occasionally plan 2 steps instead of 1 for similar-complexity requests. The agent's observation loop ensures accuracy regardless of step count.

---

## 6. Project Structure

```
kavach/
├── backend/            # Core backend application
│   ├── audit/          # Immutable JSONL audit logbook & hash chaining
│   ├── brain/          # LangGraph agent loop (plan, execute, observe, revise) & router
│   ├── engine/         # Ollama engine wrapper & role-based model registry
│   ├── guard/          # Anti-hallucination verification & human approval gate
│   ├── sandbox/        # Docker isolated execution sandbox (--network none)
│   ├── sovereignty/    # Windows firewall lockdown & real-time network sniffer
│   ├── tools/          # Specialized tools (search, writer, code, calc, ocr, vision)
│   ├── vault/          # RAG ingestion pipeline, local embedding & FAISS index
│   ├── config.py       # Central path and runtime configuration
│   └── main.py         # FastAPI routes and lifecycle orchestration
├── frontend/           # Sovereign web interface (Vanilla HTML5/CSS3/JS, zero CDNs)
├── knowledge/          # Knowledge Vault storage (raw documents & indexed SOPs)
├── outputs/            # Generated deliverables (.docx), audit logs, and temp artifacts
├── scripts/            # Setup, ingestion, and synthetic scan generators
├── testdata/           # Test fixtures, evaluation documents, and synthetic scans
└── requirements.txt    # Locked Python 3.11 dependencies
```

---

## 7. Context & Acknowledgements

Developed for **Smart India Hackathon (SIH) 2026** — Problem Statement **SIH26117** for **Mangalore Refinery and Petrochemicals Limited (MRPL)**.
KAVACH demonstrates that critical industrial infrastructure can deploy high-capability autonomous AI without transmitting a single byte outside the sovereign perimeter.

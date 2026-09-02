# KAVACH: Technical Architecture & System Context Document

> **Confidential & Comprehensive Reference Document**  
> **Project:** KAVACH (सुरक्षा कवच / Sovereign Shield)  
> **Challenge:** Smart India Hackathon (SIH) 2026 — Problem Statement **SIH26117**  
> **Industry Partner / Ministry:** Mangalore Refinery and Petrochemicals Limited (MRPL) / Ministry of Petroleum and Natural Gas (MoPNG)  
> **System Classification:** 100% Air-Gapped, Sovereign On-Premises Operations Assistant  

---

## 1. Problem Statement Context (SIH26117 — MRPL)

Critical industrial infrastructure, including petroleum refineries, petrochemical complexes, and power plants, operates under strict regulatory and cybersecurity directives. Leaking operational telemetry, process flow diagrams, standard operating procedures (SOPs), or incident reports to external public cloud APIs (e.g. OpenAI, Anthropic, Google Cloud) introduces severe supply-chain vulnerabilities, espionage risks, and non-compliance with national data sovereignty mandates.

**Problem Statement SIH26117 requires:**
1. **True Air-Gapped Operation:** The entire intelligence stack must run strictly on-premises with zero outbound network calls.
2. **Multimodal Industrial Ingestion:** Support for unstructured text, PDF engineering guidelines, scanned maintenance logs, and diagrammatic schematics.
3. **Automated Intent Triage & Specialized Models:** Dynamically selecting specialized lightweight local models based on query complexity rather than forcing a single bloated LLM.
4. **Actionable, Professional Deliverables:** Producing formal, corporate-styled Word (`.docx`) deliverables with executive summaries, technical sections, and verified citations.
5. **Deterministic Arithmetic:** Absolute zero tolerance for LLM arithmetic hallucinations in safety-critical calculations (e.g. corrosion rates, pipeline lifespans, pressure limits).
6. **Isolated Code Execution Sandbox:** Safe execution of Python scripts for data processing with provable resource constraints and zero network ingress/egress.
7. **Mathematical Sovereignty Proof:** Continuous, cryptographically auditable proof that zero external bytes left the host machine during task execution.

---

## 2. What KAVACH Is

### The Mental Model: "The Office Clerk in a Sealed Room"
Imagine an expert operations clerk locked inside a secure, windowless room inside a refinery. Inside the room, the clerk has:
- A locked **Filing Cabinet** (the Knowledge Vault containing only certified SOPs).
- A **Typewriter** (the Document Generator).
- A mechanical **Adding Machine** (the Deterministic Calculator).
- A sealed **Testing Chamber** (the Docker Sandbox).
- A **One-Way Drop Slot** (the Human Approval Gate) through which the clerk submits drafts to an authorized supervisor for physical sign-off before anything is published.
- A **Guard stationed at the door with a camera** (the Sovereignty Monitor) recording every single motion to prove nothing ever entered or exited the room.

### Core Differentiators
1. **Adversarially Proven Anti-Hallucination Guard:** Tested against queries intentionally omitted from the Knowledge Vault. Rather than hallucinating plausible-sounding procedures, KAVACH detects missing context and generates an explicit, honest notice: *"No SOP found for this topic."*
2. **Proven Container Network Isolation:** Code execution does not rely on Python `eval()` or host subprocesses. Untrusted scripts run exclusively inside a dedicated Docker container with `--network none`.
3. **Human Approval Gate for Formal Documents:** Formal documents pause before file generation. The supervisor sees risk scoring, confidence percentage, detailed reasoning, and full draft text, with options to **Approve**, **Edit in-place**, or **Reject**.
4. **Self-Correcting Agentic State Loop:** Built on LangGraph. When a tool fails (e.g. runtime script error), the agent inspects the exact stderr, re-plans, and regenerates a corrected solution autonomously.

---

## 3. Full System Architecture

```
                                    +-----------------------------------------+
                                    |         User Web Interface              |
                                    |    (Vanilla HTML5 / CSS3 / ES6 JS)      |
                                    +-------------------+---------------------+
                                                        |
                                                        v
                                    +-----------------------------------------+
                                    |          FastAPI Application            |
                                    |            (backend/main.py)            |
                                    +-------------------+---------------------+
                                                        |
                                                        v
                                    +-----------------------------------------+
                                    |      Router / Fast Intent Triage        |
                                    |       (backend/brain/router.py)         |
                                    |         [qwen2.5:1.5b-instruct]         |
                                    +-------------------+---------------------+
                                                        |
                                                        v
                                    +-----------------------------------------+
                                    |       LangGraph Agentic Loop            |
                                    |        (backend/brain/agent.py)         |
                                    |         [qwen2.5:3b-instruct]           |
                                    |    Plan -> Execute -> Observe -> Revise |
                                    +---------+---------------------+---------+
                                              |                     |
           +----------------------------------+                     +----------------------------------+
           |                                                                                           |
           v                                                                                           v
+---------------------+   +---------------------+   +---------------------+   +---------------------+  |
|  Vault Search (RAG) |   |    Writer Tool      |   |    Code Sandbox     |   |   Calculator Tool   |  |
| (backend/tools/     |   | (backend/tools/     |   | (backend/tools/     |   | (backend/tools/     |  |
|      search.py)     |   |      writer.py)     |   |     sandbox.py)     |   |      calc.py)       |  |
|  FAISS Local Store  |   |  python-docx Engine |   | Docker --net=none   |   | Deterministic AST   |  |
+---------------------+   +----------+----------+   +---------------------+   +---------------------+  |
                                     |                                                                 |
                                     v                                                                 |
                          +---------------------+                                                      |
                          | Human Approval Gate |                                                      |
                          |  (backend/guard/    |                                                      |
                          |     approve.py)     |                                                      |
                          +----------+----------+                                                      |
                                     |                                                                 |
                                     +-----------------------------------------------------------------+
                                     |
                                     v
+------------------------------------------------------------------------------------------------------+
|                                   SOVEREIGNTY & AUDIT SUBSYSTEM                                      |
|  - Immutable Audit Logbook (backend/audit/logbook.py -> outputs/audit_log.jsonl)                     |
|  - Live Socket Telemetry Monitor (backend/sovereignty/monitor.py -> external_calls: 0)               |
|  - Windows Firewall Lockdown API (backend/sovereignty/firewall.py -> netsh advfirewall)             |
+------------------------------------------------------------------------------------------------------+
```

### Component Breakdown & Verified State

#### 1. Engine & Model Registry
- **Implementation:** `backend/engine/registry.py`, `backend/engine/ollama.py`
- **Functionality:** Centralized role-to-model mapping. Interacts with the local Ollama daemon over `http://127.0.0.1:11434`. Includes automated timeout handling, health checks, and role resolution.
- **Verified State:** Verified across all phases. Zero external requests generated.

#### 2. Fast Intent Triage & Router
- **Implementation:** `backend/brain/router.py`
- **Model:** `qwen2.5:1.5b-instruct` (Fast Router role)
- **Functionality:** Evaluates incoming user prompts and classifies them into `search`, `document`, `code`, `calc`, or `general` within 300–600ms. Selects appropriate model role and tool constraints.
- **Verified State:** Verified in Phase 2, 8, 10, 11, and 12. Correctly routes formal requests to `document` and technical queries to `search`.

#### 3. Agent State Loop (LangGraph)
- **Implementation:** `backend/brain/agent.py`
- **Model:** `qwen2.5:3b-instruct` (Reasoning role)
- **Architecture:** StateGraph with 4 primary nodes:
  - `plan_node`: Produces a minimal ordered plan (1–3 steps for simple tasks; soft ceiling enforced).
  - `execute_node`: Dispatches the active step to specialized tools.
  - `observe_node`: Inspects tool outputs. Detects errors or ungrounded searches, routing to `REVISE` (up to 2 revisions) or `FINALIZE`.
  - `revise_node`: Formulates failure context and adjusts the plan.
- **Verified State:** Verified in Phase 2, 6, 11, and 12. Self-correction proven with container execution failures and ungrounded search queries.

#### 4. Knowledge Vault & RAG Search
- **Implementation:** `backend/vault/ingest.py`, `backend/vault/search.py`, `backend/tools/search.py`
- **Functionality:** Ingests PDF, DOCX, TXT, MD, and image scans. Uses local embeddings and FAISS index (`knowledge/faiss_index/`). Retrieves top-$k$ relevant excerpts with filename attribution.
- **Anti-Hallucination Guard:** If cosine similarity or retrieved context is insufficient, returns an explicit `grounded: False` status, instructing downstream tools not to invent facts.
- **Verified State:** Verified in Phase 4, 8, and 11. Tested with positive queries (high-severity notifications) and ungrounded queries (deep-sea oil rig evacuation).

#### 5. Corporate Document Generator (Writer)
- **Implementation:** `backend/tools/writer.py`
- **Functionality:** Takes structured draft JSON (title, executive summary, technical sections, source attributions) and renders standard corporate `.docx` files.
- **Styling:** Deep Navy headers (`#1B365D`), Slate accents (`#4A777A`), Charcoal body (`#222222`), 1-inch margins, custom metadata table, and callout boxes.
- **Anti-Leak Guards:** Strict filtering in `_parse_draft_json` strips placeholder strings like `"source_filename_1"` or `"Short descriptive document title"`. Forces `sources = []` if `is_grounded=False`.
- **Verified State:** Verified in Phase 5, 11, and 12. Verified paragraph and XML formatting using `python-docx`.

#### 6. Isolated Code Execution Sandbox
- **Implementation:** `backend/tools/sandbox.py`, `backend/tools/code.py`
- **Functionality:** Untrusted code generated by `qwen2.5-coder:3b` is written to a temporary host file and mounted read-only into an ephemeral Docker container:
  - `docker run --rm --network none -m 256m --cpus 1.0 -v <tmp>:/code/solution.py:ro python:3.11-slim python /code/solution.py`
- **Error-Feedback Loop:** When runtime errors occur, container `stderr` is captured and passed directly into `RETRY_PROMPT_TEMPLATE`.
- **Verified State:** Verified in Phase 6 and Phase 12. Tested with deliberate `ZeroDivisionError`; coder model consumed stderr and regenerated working code with `exit_code: 0`.

#### 7. OCR & Multimodal Vision
- **Implementation:** `backend/tools/ocr.py`, `backend/tools/vision.py`
- **Engines:** **Tesseract OCR (`pytesseract`)** for text extraction; **Moondream (`moondream:latest`)** for visual question answering.
- **Functionality:** Extracts text, equipment tags, and sensor readings from inspection sheets and gauge diagrams.
- **Verified State:** Verified in Phase 7 and Phase 12. Clean scan achieves 70.9% confidence on multi-line refinery inspection sheets.

#### 8. Deterministic Calculator & Verifier
- **Implementation:** `backend/tools/calc.py`, `backend/guard/verify.py`
- **Core Principle:** **The LLM is NEVER trusted with arithmetic.**
- **Architecture:** The model extracts formula parameters (e.g. `current_thickness = 12.5`, `min_thickness = 8.0`, `corrosion_rate = 0.4`). A deterministic Python mathematical function computes `(12.5 - 8.0) / 0.4 = 11.25 years` and formats verifiable substitution steps.
- **Verification Guard:** `verify_claims()` extracts discrete factual claims from generated documents and verifies each against source excerpts.
- **Verified State:** Verified in Phase 8 and Phase 12.

#### 9. Human Approval Gate
- **Implementation:** `backend/guard/approve.py`
- **Functionality:** Intercepts formal document outputs before file creation.
  - Risk Heuristic: Evaluates groundedness and content specificity. Distinguishes honest "missing SOP" notices (Risk: High, Conf: 40%) from ungrounded fabricated specifics (`WARNING: content may be fabricated`, Conf: 20%).
  - Workflow: Pauses agent at `status: "awaiting_approval"`. Supervisor reviews via Web UI and issues `approve`, `edit`, or `reject`.
  - In-Place Editing: Supervisor modifications are merged into the final `.docx` without re-running the LLM.
- **Verified State:** Verified in Phase 11 and Phase 12 across all three paths (Approve, Edit, Reject).

#### 10. Sovereignty Proof & Audit Subsystem
- **Implementation:** `backend/sovereignty/firewall.py`, `backend/sovereignty/monitor.py`, `backend/audit/logbook.py`
- **Firewall:** Executes native Windows `netsh advfirewall` commands to block all outbound IP traffic while whitelisting loopback (`127.0.0.1`) and local subnets.
- **Live Monitor:** Continuous thread monitors active TCP/UDP sockets for KAVACH processes. Records any connection attempt outside `127.0.0.1` or `localhost`.
- **Immutable Audit Trail:** Append-only `outputs/audit_log.jsonl` with SHA-256 hash chaining. Every single audit event explicitly asserts `external_calls: 0`.
- **Verified State:** Verified in Phase 3, 9, 11, and 12. Over 780 audit events logged with zero external calls. Tested with intentional external socket connection to verify detector sensitivity.

---

## 4. Complete Technology Stack

| Layer | Component | Version | Purpose |
| :--- | :--- | :--- | :--- |
| **Runtime** | Python | 3.11.x (64-bit) | Base language environment |
| **API Server** | FastAPI / Uvicorn | 0.141.1 / 0.52.4 | High-performance asynchronous API & static server |
| **Agent Orchestration** | LangGraph / LangChain Core | 1.2.11 / 1.6.1 | Cyclical state graph execution & error revision |
| **Local LLM Engine** | Ollama | Latest Windows Native | Local model hosting & GPU/CPU inference |
| **Reasoning Model** | `qwen2.5:3b-instruct` | 3B Parameters | Planning, drafting, reasoning, claim verification |
| **Router Model** | `qwen2.5:1.5b-instruct` | 1.5B Parameters | Sub-second intent triage and parameter extraction |
| **Code Model** | `qwen2.5-coder:3b` | 3B Parameters | Python script generation & syntax correction |
| **Vision Model** | `moondream:latest` | 1.8B Parameters | Engineering diagram analysis & visual QA |
| **Vector Database** | FAISS CPU | 1.15.0 | High-performance local similarity search |
| **OCR Engine** | Tesseract OCR (`pytesseract`) | 5.3+ / 0.3.13 | Primary on-premises optical character recognition |
| **Code Isolation** | Docker Desktop (WSL2) | Engine 24+ | Locked container execution (`--network none`) |
| **Document Engine** | `python-docx` | 1.2.0 | Corporate Word document rendering & styling |
| **Frontend** | Vanilla HTML5 / CSS3 / ES6 JS | Native Browser | Sovereign web UI (zero external CDN or web calls) |

### Frontend Design Tokens & Accent Architecture
The frontend is completely offline and self-contained:
- **Typography:** Authoritative serif titles (`Charter`, `Georgia`, `serif`) paired with clean functional UI text (`Segoe UI`, `system-ui`, `sans-serif`).
- **Accent Color System (Defined in `frontend/style.css`):**
  - `--color-accent: #2b5797;` (Corporate Refinery Blue)
  - `--color-accent-soft: rgba(43, 87, 151, 0.08);` (Muted Active Tint)
  - `--color-accent-hover: #1e3f6f;` (Deep Navy Button Hover)
  - `--color-surface: #f7f6f2;` (Warm Paper White)

---

## 5. What is Genuinely Proven vs. Known Limitations

To ensure absolute engineering integrity when presenting to technical evaluators, KAVACH clearly delineates proven features from real-world constraints:

### Genuinely Proven (Empirical Evidence)
1. **Zero External Calls Under Live Monitoring:** The live socket monitor was tested against intentional external connections (`socket.create_connection(("8.8.8.8", 53))`). The monitor immediately caught the violation and logged `external_calls: 1`. In normal operation across 780+ tasks, the monitor continuously logs `external_calls: 0`.
2. **Deterministic Anti-Hallucination:** Tested with queries outside the knowledge base. The system refuses to invent procedures, outputs grounded: `False`, alerts the human supervisor, and flags the draft as ungrounded.
3. **Container Isolation & Real Self-Correction:** Tested inside real Docker containers with `--network none`. An intentional zero-division runtime bug was captured via container stderr and corrected by the coding model, producing `exit_code: 0`.
4. **Deterministic Calculation Steps:** Mathematical formulas are calculated via Python AST, guaranteeing arithmetic accuracy.

### Known Limitations & Honest Technical Realities
1. **Firewall Lockdown Privilege:** `netsh advfirewall` requires administrative elevation. Starting the server from a standard non-admin PowerShell prompt prevents rule insertion.
2. **PaddleOCR Windows Incompatibility:** PaddleOCR exhibits a fatal C++ oneDNN DLL crash on Windows. KAVACH uses Tesseract OCR (`pytesseract`) as its primary, fully functioning engine.
3. **Resolution-Dependent OCR:** Degraded or heavily compressed scans yield lower confidence scores (~15–30%). Clear, high-resolution scans achieve 70–95% confidence.
4. **Planner Step-Count Variance:** Because small 3B models possess lower planning determinism than 70B models, plan lengths occasionally vary between 1 and 3 steps for similar queries. Soft ceilings prevent erratic 6-step plans.

---

## 6. Build History & Key Architectural Decisions

- **Phase 1 (Engine & Registry):** Established the multi-model architecture. Decided against a single 7B model in favor of specialized 1.5B–3B models to fit within consumer 8GB/16GB VRAM.
- **Phase 2 (Agent Brain):** Implemented LangGraph StateGraph with explicit `Plan -> Execute -> Observe -> Revise` topology.
- **Phase 3 (Audit Logbook):** Built append-only JSONL event store with SHA-256 hash chaining.
- **Phase 4 (Knowledge Vault):** Developed local FAISS RAG pipeline with strict ungrounded fallback triggers.
- **Phase 5 (Word Generator & Disguised-Hallucination Bug):** Discovered the model was dressing up ungrounded facts in formal Word templates. Fixed by implementing `is_grounded` parameter passing and template sanitization.
- **Phase 6 (Docker Sandbox):** Enforced `--network none` container isolation and real stderr feedback loops.
- **Phase 7 (OCR & Vision):** Identified the PaddlePaddle oneDNN bug on Windows and successfully pivoted to Tesseract OCR.
- **Phase 8 (Calculator & Verifier):** Enforced the rule that LLMs must never perform arithmetic. Implemented Python AST calculation and automated claim-by-claim verification.
- **Phase 9 (Sovereignty Proof):** Implemented native Windows Defender Firewall manipulation and continuous live socket telemetry monitoring.
- **Phase 10 (Sovereign Frontend):** Built a zero-dependency web interface with live SSE/polling progress, step execution status, and audit viewers.
- **Phase 11 (Human Approval Gate):** Added the supervisory gate for high-stakes documents, distinguishing fabricated specifics from honest missing SOP notices.
- **Phase 12 (Hardening & Regression):** Enforced planner soft ceilings (1–3 steps), eliminated prompt example leaks, added live UI elapsed-time tickers, and passed full 7-flow regression testing.

---

## 7. Infrastructure & Presentation Topology

For demonstration and competition environments, KAVACH uses a 3-tier laptop topology:

```
[Laptop 1: Primary Driver / Server]
├── FastAPI Application (Port 8000)
├── Ollama Inference Engine (11434)
├── Docker Desktop Daemon
└── Fullscreen Sovereign UI (Chrome Kiosk)

[Laptop 2: Hot-Standby Mirror]
├── Identical Clone of Repo & .venv
├── Pre-pulled Ollama Models & Docker Images
└── Ready for instantaneous IP switch if hardware fails

[Laptop 3: Live Audit & Evaluator Console]
├── Real-Time Audit Log Terminal (tail -f outputs/audit_log.jsonl)
├── Wireshark / Network Packet Monitor (Proving 0 egress packets)
└── Slide Deck & Architecture Visualizer
```

---

## 8. Current State & Readiness

As of Phase 12 completion:
- **Core Engineering:** 100% complete across all 12 planned phases.
- **Verification:** All 7 core flows verified passing simultaneously under live conditions.
- **Code Freeze:** All active development is complete. Ready for flagship scenario rehearsal and demo document ingestion.

---

## 9. Future Extensibility Roadmap

The KAVACH architecture is built to support future enterprise enhancements without structural rewrites:
1. **Role-Based Access Control (RBAC):** Injecting cryptographic user tokens into the audit trail for multi-user sign-offs.
2. **Hybrid BM25 + Dense Retrieval:** Combining keyword lexical search with dense vector embeddings for highly specialized chemical engineering terms.
3. **Automated Presentation Generator:** Extending the document writer engine to generate `.pptx` slide summaries using `python-pptx`.
4. **Air-Gapped Voice Interface:** Local Whisper transcription and Piper speech synthesis for hands-free field maintenance inspections.

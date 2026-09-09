# KAVACH: Technical Architecture & System Context Document

> **Confidential & Comprehensive Reference Document**  
> **Project:** KAVACH (सुरक्षा कवच / Sovereign Shield)  
> **Challenge:** Smart India Hackathon (SIH) 2026 — Problem Statement **SIH26117**  
> **Industry Partner / Ministry:** Mangalore Refinery and Petrochemicals Limited (MRPL) / Ministry of Petroleum and Natural Gas (MoPNG)  
> **System Classification:** 100% Air-Gapped, Sovereign On-Premises Operations Assistant  
> **Document status:** Reflects the live codebase (post–Phase 12). Setup commands live in `startup.md`.

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
- A **Console** (the React operator UI: Chat, Knowledge Vault, Audit Log, Model Settings) through which authorized staff talk to the clerk.
- A locked **Filing Cabinet** (the Knowledge Vault containing only certified SOPs).
- A **Typewriter** (the Document Generator).
- A mechanical **Adding Machine** (the Deterministic Calculator).
- A sealed **Testing Chamber** (the Docker Sandbox for Python, JavaScript, and C).
- A **Master Planner** who decomposes a compound request into ordered sub-tasks before any tool is touched.
- A **One-Way Drop Slot** (the Human Approval Gate) through which the clerk submits drafts to an authorized supervisor for physical sign-off before anything is published.
- A **Clarification Window** through which the clerk may pause and ask the operator a single clarifying question, then resume from saved state.
- A **Guard stationed at the door with a camera** (the Shield monitor) recording every connection to prove nothing ever entered or exited the room.

### Core Differentiators
1. **Adversarially Proven Anti-Hallucination Guard:** Tested against queries intentionally omitted from the Knowledge Vault. Rather than hallucinating plausible-sounding procedures, KAVACH detects missing context and generates an explicit, honest notice: *"No SOP found for this topic."*
2. **Proven Container Network Isolation:** Code execution does not rely on Python `eval()` or host subprocesses. Untrusted scripts run exclusively inside a dedicated Docker container with `--network none`.
3. **Human Approval Gate for Formal Documents:** Formal documents pause before file generation. The supervisor sees risk scoring, confidence percentage, detailed reasoning, and full draft text, with options to **Approve**, **Edit in-place**, or **Reject**.
4. **Self-Correcting Agentic State Loop:** Built on LangGraph. A Master Planner decomposes the request; when a tool fails (e.g. runtime script error), the agent inspects the exact stderr, revises or replans, and regenerates a corrected solution. If the request is underspecified, it pauses for a human reply and resumes from a persisted state snapshot.
5. **Live Operator Trace:** The React console streams plan, tool, observation, and clarification events over SSE so the operator sees every step as it happens — not a black-box wait.

---

## 3. Full System Architecture

```
                         +----------------------------------------------+
                         |         Operator Web Console                 |
                         |  React 18 + Vite  (frontend-react/, /)       |
                         |  Legacy vanilla fallback  (frontend/, /vanilla)
                         |  Chat · Vault · Audit · Model Settings       |
                         +----------------------+-----------------------+
                                                |
                         REST  ·  SSE /run/stream  ·  WS /shield/monitor
                                                |
                                                v
                         +----------------------------------------------+
                         |           FastAPI Application                |
                         |             (backend/main.py)                |
                         |  Auth · Chats · Agent · Models · Shield      |
                         +------+------------------+--------------------+
                                |                  |
                                v                  v
                   +------------------+   +---------------------------+
                   | PostgreSQL 16    |   | LangGraph Agent Brain     |
                   | host port 5434   |   | (backend/brain/agent.py)  |
                   | users, chats,    |   | master_plan -> route_     |
                   | messages,        |   | subtask -> execute ->     |
                   | agent_runs       |   | observe -> replan|revise  |
                   +------------------+   |        |clarify|finalize  |
                                          +---+---------------------+-+
                                              |                     |
           +----------------------------------+                     +----------------------------------+
           |                                                                                           |
           v                                                                                           v
+---------------------+   +---------------------+   +---------------------+   +---------------------+  |
|  Vault Search (RAG) |   |    Writer Tool      |   |    Code Sandbox     |   |   Calculator Tool   |  |
| (backend/tools/     |   | (backend/tools/     |   | (backend/tools/     |   | (backend/tools/     |  |
|      search.py)     |   |      writer.py)     |   |     sandbox.py)     |   |      calc.py)       |  |
|  FAISS + nomic      |   |  python-docx Engine |   | Docker --net=none   |   | Deterministic AST   |  |
|  embed-text         |   |                     |   | Python / JS / C     |   |                     |  |
+---------------------+   +----------+----------+   +---------------------+   +---------------------+  |
                                     |                                              OCR / Vision / LLM |
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
|                                   SHIELD & AUDIT SUBSYSTEM                                           |
|  - Append-only Audit Logbook (backend/audit/logbook.py -> outputs/audit_log.jsonl)                   |
|  - Live Socket Telemetry Monitor (backend/shield/monitor.py -> external_calls: 0)                    |
|  - Windows Firewall Lockdown API (backend/shield/firewall.py -> netsh advfirewall)                   |
|  - Endpoints: GET /shield/status · POST /shield/lockdown|unlock · WS /shield/monitor                 |
+------------------------------------------------------------------------------------------------------+
```

Local inference is always Ollama at `http://localhost:11434`. Role-to-model mapping is loaded from `backend/models.json` (never hardcoded in Python). LangSmith / LangChain tracing is forced off at process start in `backend/main.py`.

### Component Breakdown & Verified State

#### 1. Engine & Model Registry
- **Implementation:** `backend/engine/registry.py`, `backend/engine/ollama.py`, `backend/engine/prompts.py`, `backend/models.json`
- **Functionality:** Centralized role-to-model mapping and standardized on-premise industrial system prompt enforcement. Interacts with the local Ollama daemon over `http://127.0.0.1:11434`. Includes timeout handling, health checks, and hot-swap via `POST /models/assign`. The Model Settings screen can pull, cancel, inspect, and delete models.
- **Live role map:**

| Role | Model | Used for |
| :--- | :--- | :--- |
| `reasoning` | `gemma3:4b` | Master planning, drafting, search synthesis, calc parameter extraction, claim verification, router fallback |
| `code` | `granite4.1:3b` | Python / JavaScript / C generation and stderr self-correction |
| `vision` | `gemma3:4b` | Diagrams, photos, gauges (assisted understanding) |
| `embedding` | `nomic-embed-text:latest` | Knowledge Vault chunk embeddings |

- **Verified State:** Registry is the single source of truth. The multimodal engineering/drawing system prompt is scoped strictly to `vision` tasks to prevent prompt anchoring and hallucination during general chat/reasoning. Code generation calls with `granite4.1:3b` enforce the focused software engineering system prompt. Model roles can be reassigned dynamically without restarting the server.

#### 2. Fast Intent Triage & Router
- **Implementation:** `backend/brain/router.py`
- **Mechanism:** Rule-based keyword scoring. Typical classification is well under 50 ms with **no LLM call**. A single cheap one-word classification call to the **reasoning** model is made only on a genuine tie or when no keyword signal exists. Planner-designated tool hints (`document`, `code`, `calc`, `search`, `vision`, `ocr`, `llm`) are respected first.
- **Task types:** `document`, `code`, `calc`, `search`, `vision`, `ocr`, `llm`.
- **Verified State:** Replaced the earlier dedicated `qwen2.5:1.5b-instruct` router. Image attachments and OCR keywords short-circuit to `vision` / `ocr` without scoring.

#### 3. Agent State Loop (LangGraph)
- **Implementation:** `backend/brain/agent.py`, `backend/brain/state.py`, `backend/brain/tools_dispatch.py`, `backend/brain/event_bus.py`
- **Model:** `gemma3:4b` (Reasoning role) for planning / observation; per-step routing may switch to `code` or `vision`.
- **Architecture:** Compiled StateGraph with these nodes:
  - `master_plan`: Decomposes a compound request into ordered sub-tasks (e.g. `[code]` then `[document]`).
  - `route_subtask`: Calls the rule-based router for the active step and switches the live model role.
  - `execute`: Dispatches the step through `tools_dispatch` (`search`, `calc`, `code`, `document`, `ocr`, `vision`, `llm`).
  - `observe`: Inspects tool outputs. Routes to `executing` (next step), `replan`, `revising`, `clarifying`, `complete`, `failed`, or `awaiting_approval`.
  - `replan`: Rewrites remaining steps when the original plan is insufficient.
  - `revise`: Feeds tool stderr / failure context back into the same step (sandbox self-correction).
  - `clarify`: Pauses the graph, stores `state_snapshot` on `agent_runs`, and waits for `POST /run/{task_id}/reply`.
  - `finalize`: Assembles the operator-facing answer and key-fact memory.
- **Live events:** Nodes emit `plan`, `step_start`, `tool_done`, `observe`, `replan`, `revise`, `clarify`, `final`, `done_stream`, and `error` onto an in-process asyncio queue consumed by `GET /run/stream`.
- **Memory:** Chat-scoped `agent_memory` (JSONB) plus per-run `key_facts` extracted from tool outputs.
- **Verified State:** Master Planner, clarification resume, and SSE streaming are the live loop. The older four-node `Plan -> Execute -> Observe -> Revise` graph is historical.

#### 4. Knowledge Vault & RAG Search
- **Implementation:** `backend/vault/ingest.py`, `backend/vault/retrieve.py`, `backend/tools/search.py`
- **Functionality:** Ingests PDF, DOCX, TXT, MD, and image scans. Chunks (~500 tokens, 50 overlap), embeds with `nomic-embed-text`, and stores a local FAISS index at `knowledge/faiss_index/`. Retrieves top-k excerpts with filename attribution. Batch ingest: `python scripts/ingest_docs.py testdata`.
- **Anti-Hallucination Guard:** If cosine similarity or retrieved context is insufficient, returns an explicit `grounded: False` status, instructing downstream tools not to invent facts.
- **Verified State:** FAISS is the live vector store (not ChromaDB). UI upload is `POST /knowledge/upload`; listing is `GET /knowledge/list`.

#### 5. Corporate Document Generator (Writer)
- **Implementation:** `backend/tools/writer.py`
- **Functionality:** Takes structured draft JSON (title, executive summary, technical sections, source attributions) and renders standard corporate `.docx` files into `outputs/`. Download via `GET /download/{filename}`.
- **Styling:** Dark navy titles, slate metadata, charcoal body, 1-inch margins, custom metadata table, and callout boxes.
- **Anti-Leak Guards:** Strict filtering in `_parse_draft_json` strips placeholder strings like `"source_filename_1"` or `"Short descriptive document title"`. Forces `sources = []` if `is_grounded=False`.
- **Verified State:** Formal / high-risk drafts pause at the Human Approval Gate before `render_docx` is called. Routine code-documentation drafts may download immediately.

#### 6. Isolated Code Execution Sandbox
- **Implementation:** `backend/tools/sandbox.py`, `backend/tools/code.py`
- **Functionality:** Untrusted code generated by `granite4.1:3b` is written to a temporary host file and mounted read-only into an ephemeral Docker container with `--network none`, `-m 256m`, `--cpus 1.0`, and a 15-second wall-clock timeout.

| Language | Image | Entry |
| :--- | :--- | :--- |
| Python | `python:3.11-slim` | `python /code/solution.py` |
| JavaScript | `node:20-slim` | `node /code/solution.js` |
| C | `gcc:13-slim` | compile then run `/tmp/app` |

- **Interactive re-run:** The React console can edit code and stdin and call `POST /code/run` without re-planning the whole agent task.
- **Error-Feedback Loop:** Container `stderr` is captured and passed into a retry prompt so the coder model can self-correct.
- **Verified State:** Pre-flight distinguishes Docker not installed vs daemon stopped vs permission denied; on Windows the sandbox may auto-launch Docker Desktop and wait.

#### 7. OCR & Multimodal Vision
- **Implementation:** `backend/tools/ocr.py`, `backend/tools/vision.py`
- **Engines:** **Tesseract OCR (`pytesseract`)** for text extraction from images and scanned PDFs; **`gemma3:4b`** for visual question answering on diagrams, photos, and gauges.
- **Functionality:** Extracts text, equipment tags, and sensor readings from inspection sheets. Vision answers are required to say `uncertain` rather than guess.
- **Verified State:** Primary vision pipeline powered by local Ollama multimodal models. PaddleOCR was abandoned on Windows (oneDNN crash) and is not in the live path.

#### 8. Deterministic Calculator & Verifier
- **Implementation:** `backend/tools/calc.py`, `backend/guard/verify.py`
- **Core Principle:** **The LLM is NEVER trusted with arithmetic.**
- **Architecture:** The reasoning model extracts formula parameters (e.g. `current_thickness = 12.5`, `min_thickness = 8.0`, `corrosion_rate = 0.4`). A deterministic Python AST evaluator computes the result and formats verifiable substitution steps.
- **Verification Guard:** `verify_claims()` extracts discrete factual claims from generated documents and verifies each against source excerpts.
- **Verified State:** Unchanged in principle from Phase 8; still the live arithmetic path.

#### 9. Human Approval Gate
- **Implementation:** `backend/guard/approve.py`
- **Functionality:** Intercepts formal document outputs before file creation.
  - Risk Heuristic: Evaluates groundedness and content specificity. Distinguishes honest "missing SOP" notices from ungrounded fabricated specifics.
  - Workflow: Pauses the agent at `status: "awaiting_approval"`. The React `MessageTurn` (and legacy `approval.html`) issues `approve`, `edit`, or `reject` via `POST /approval/{task_id}`.
  - In-Place Editing: Supervisor modifications are merged into the final `.docx` without re-running the LLM.
- **Verified State:** Pending records are held in process memory (`_APPROVAL_RECORDS`) and are lost on server restart. This is a known limitation, not a durable queue.

#### 10. Auth, Persistence & Chat
- **Implementation:** `backend/auth/`, `backend/chat/`, `backend/db/models.py`, Alembic `001_initial_schema` and `002_agent_memory_and_runs`
- **Auth:** Email / password → bcrypt; JWT (HS256, 7 days) in an httpOnly `access_token` cookie (`SameSite=Lax`, `secure=False` for local HTTP). `GET /auth/me` restores the session. Optional `Authorization: Bearer` is also accepted.
- **Roles:** There is **no RBAC**. The `User` table is `id`, `name`, `email`, `password_hash`. “Operator” / “supervisor” is UX language only.
- **Tables:**

| Table | Purpose |
| :--- | :--- |
| `users` | Registered accounts |
| `chats` | Per-user threads, including `agent_memory` JSONB |
| `messages` | User / assistant turns with `meta` JSONB |
| `agent_runs` | `task_id`, `status`, `state_snapshot` for pause / resume |

- **Agent endpoints:** Guests may run `/run` and `/run/stream` without login (no persistence). Logged-in users get chat history and message writes.

#### 11. Shield (Sovereignty Proof) & Audit
- **Implementation:** `backend/shield/firewall.py`, `backend/shield/monitor.py`, `backend/shield/netinfo.py`, `backend/audit/logbook.py`
- **Firewall:** Native Windows `netsh advfirewall` default-deny egress, with loopback and local subnet still reachable. Requires Administrator elevation. APIs: `POST /shield/lockdown`, `POST /shield/unlock`, `GET /shield/status`.
- **Live Monitor:** A background thread classifies TCP/UDP sockets for the KAVACH process tree plus Ollama as localhost / LAN / external. Snapshots stream over `WS /shield/monitor` (~1s) and are also appended to `outputs/sovereignty_session.jsonl`.
- **Audit Trail:** Append-only `outputs/audit_log.jsonl`. Every event records `timestamp`, `task_id`, `event_type`, `actor`, `summary`, `metadata`, and `external_calls`. The log is thread-safe and exception-safe so a write failure never crashes the agent.
- **Verified State:** The package formerly called `backend/sovereignty/` is now `backend/shield/`. The live logbook does **not** implement SHA-256 hash chaining; that claim belonged to an earlier design and is not present in `logbook.py`.

---

## 4. Complete Technology Stack

| Layer | Component | Version / Location | Purpose |
| :--- | :--- | :--- | :--- |
| **Runtime** | Python | 3.11.x (64-bit) | Base language environment |
| **API Server** | FastAPI / Uvicorn | 0.141.1 / 0.52.4 | Async API, SSE, WebSocket, static React `dist/` |
| **Agent Orchestration** | LangGraph / LangChain Core | 1.2.11 / 1.6.1 | Master-plan graph, observe / replan / clarify |
| **Local LLM Engine** | Ollama | Latest Windows Native | Local inference at `:11434` |
| **Reasoning Model** | `gemma3:4b` | 4B Parameters | Planning, drafting, synthesis, verification |
| **Router** | Rule-based keywords | `backend/brain/router.py` | Sub-50ms intent triage; LLM only on ties |
| **Code Model** | `granite4.1:3b` | 3B Parameters | Python / JS / C generation & stderr correction |
| **Vision Model** | `gemma3:4b` | 4B Multimodal | Diagram / photo / gauge analysis |
| **Embedding Model** | `nomic-embed-text:latest` | Local Ollama | Vault chunk embeddings |
| **Vector Database** | FAISS CPU | 1.15.0 | Local similarity search |
| **Persistence** | PostgreSQL 16 + SQLAlchemy 2 + Alembic | Docker host **5434** | Users, chats, messages, agent runs |
| **Auth** | bcrypt + python-jose JWT | 5.0.0 / 3.5.0 | httpOnly cookie sessions |
| **OCR Engine** | Tesseract OCR (`pytesseract`) | 5.3+ / 0.3.13 | On-premises optical character recognition |
| **Code Isolation** | Docker Desktop (WSL2) | Engine 24+ | Locked containers (`--network none`) |
| **Document Engine** | `python-docx` | 1.2.0 | Corporate Word rendering |
| **Frontend (primary)** | React 18.3 + Vite 5 | `frontend-react/` | Operator console; served from `dist/` at `/` |
| **Frontend (legacy)** | Vanilla HTML5 / CSS3 / ES6 | `frontend/` | Fallback at `/vanilla` (no auth, no SSE, no Model Settings) |
| **Shield** | `psutil` + Windows Defender Firewall | 7.2.2 | Live socket classification and lockdown |

### Frontend Design Tokens & Operator Console
Primary UI is the React console (`frontend-react/src/styles/index.css`):
- **Typography:** Inter (UI) + Source Serif 4 (titles), with `system-ui` / Georgia fallbacks.
- **Accent Color System:**
  - `--kavach-accent: #4FA8D8;` (ocean blue)
  - `--kavach-accent-hover: #3B8FBF;`
  - `--kavach-accent-muted: #E8F4FA;`
  - `--bg-page: #FAF9F7;` (warm paper)
  - Sovereignty dots: `--status-safe: #4E9A6B;` / `--status-alert: #C2554D;`
- **Screens (in-app state, no client router):** Chat (`NewTaskScreen`), Knowledge Vault, Audit Log, Model Settings, plus `AuthModal`.
- **Air-gap note:** `frontend-react/index.html` loads Inter and Source Serif 4 from Google Fonts. On a fully isolated host those requests fail and the UI falls back to system fonts. This is an exception to a strict zero-CDN posture, not a runtime dependency.

### Primary HTTP / realtime surface

| Method | Path | Purpose |
| :--- | :--- | :--- |
| POST / GET | `/auth/register` `/login` `/logout` `/me` | Session |
| CRUD | `/chats` and `/chats/{id}/messages` | Persistent chat |
| POST | `/run` | Synchronous agent run (legacy / vanilla) |
| GET | `/run/stream` | SSE live agent progress (React) |
| POST | `/run/{task_id}/reply` | Resume after clarification |
| GET / POST / DELETE | `/models*` | Registry, pull stream, assign, delete |
| POST | `/code/run` | Interactive sandbox re-run |
| GET / POST | `/approval/{task_id}` | Human document gate |
| GET / POST | `/knowledge/list` `/knowledge/upload` | Vault |
| GET | `/audit` `/download/{filename}` `/health` | Audit, artifacts, health |
| GET / POST / WS | `/shield/status` `/lockdown` `/unlock` `/monitor` | Sovereignty |

---

## 5. What is Genuinely Proven vs. Known Limitations

To ensure absolute engineering integrity when presenting to technical evaluators, KAVACH clearly delineates proven features from real-world constraints:

### Genuinely Proven (Empirical Evidence)
1. **Zero External Calls Under Live Monitoring:** The live socket monitor was tested against intentional external connections (`socket.create_connection(("8.8.8.8", 53))`). The monitor immediately caught the violation and logged `external_calls: 1`. In normal agent operation the monitor continuously logs `external_calls: 0` for KAVACH and Ollama PIDs.
2. **Deterministic Anti-Hallucination:** Tested with queries outside the knowledge base. The system refuses to invent procedures, outputs `grounded: False`, alerts the human supervisor, and flags the draft as ungrounded.
3. **Container Isolation & Real Self-Correction:** Tested inside real Docker containers with `--network none`. An intentional zero-division runtime bug was captured via container stderr and corrected by the coding model, producing `exit_code: 0`.
4. **Deterministic Calculation Steps:** Mathematical formulas are calculated via Python AST, guaranteeing arithmetic accuracy.
5. **Master Planner model switching:** Compound tasks (e.g. “write Python, then draft a document”) produce an ordered plan, switch `granite4.1:3b` → `gemma3:4b`, and surface the chain in the React message header.
6. **Clarification resume:** Underspecified tasks pause, persist `agent_runs.state_snapshot`, and continue after `POST /run/{task_id}/reply`.

### Known Limitations & Honest Technical Realities
1. **Firewall Lockdown Privilege:** `netsh advfirewall` requires administrative elevation. Starting the server from a standard non-admin PowerShell prompt prevents rule insertion.
2. **PaddleOCR Windows Incompatibility:** PaddleOCR exhibits a fatal C++ oneDNN DLL crash on Windows. KAVACH uses Tesseract OCR (`pytesseract`) as its primary, fully functioning engine.
3. **Resolution-Dependent OCR:** Degraded or heavily compressed scans yield lower confidence scores (~15–30%). Clear, high-resolution scans achieve 70–95% confidence. Vision is assisted understanding, not certified engineering interpretation.
4. **Audit log is append-only, not hash-chained:** `backend/audit/logbook.py` writes JSONL with `external_calls`. It does **not** currently compute SHA-256 prev-hash chaining.
5. **Approvals are in-memory:** Pending Human Approval Gate records are lost if the FastAPI process restarts.
6. **`GET /models/info` is not air-gapped:** Inspecting Ollama library tags scrapes `https://ollama.com/library/.../tags` when that screen is used. Model pull itself talks only to the local Ollama daemon.
7. **Google Fonts on the React shell:** Offline hosts skip the CDN and use system fonts; the UI still functions.
8. **No user RBAC:** Any registered user (and, for agent/vault/audit/models/shield APIs, even an anonymous browser) can hit those surfaces. Chat history is the only per-user isolation.
9. **LangSmith is disabled, not absent as a dependency:** Tracing env vars are cleared in `main.py`; the `langsmith` package remains in `requirements.txt` via LangGraph.

---

## 6. Build History & Key Architectural Decisions

- **Phase 1 (Engine & Registry):** Established the multi-model architecture. Originally favoured specialized 1.5B–3B models to fit consumer 8GB/16GB VRAM; the live reasoning role has since been upgraded to 7B (see Post–Phase 12).
- **Phase 2 (Agent Brain):** Implemented LangGraph StateGraph with explicit `Plan -> Execute -> Observe -> Revise` topology.
- **Phase 3 (Audit Logbook):** Built append-only JSONL event store. Hash chaining was designed here; it is not present in the live logger.
- **Phase 4 (Knowledge Vault):** Developed local FAISS RAG pipeline with strict ungrounded fallback triggers.
- **Phase 5 (Word Generator & Disguised-Hallucination Bug):** Discovered the model was dressing up ungrounded facts in formal Word templates. Fixed by implementing `is_grounded` parameter passing and template sanitization.
- **Phase 6 (Docker Sandbox):** Enforced `--network none` container isolation and real stderr feedback loops.
- **Phase 7 (OCR & Vision):** Identified the PaddlePaddle oneDNN bug on Windows and successfully pivoted to Tesseract OCR.
- **Phase 8 (Calculator & Verifier):** Enforced the rule that LLMs must never perform arithmetic. Implemented Python AST calculation and automated claim-by-claim verification.
- **Phase 9 (Sovereignty Proof):** Implemented native Windows Defender Firewall manipulation and continuous live socket telemetry monitoring.
- **Phase 10 (Sovereign Frontend):** Built a zero-dependency vanilla web interface with progress, step execution status, and audit viewers.
- **Phase 11 (Human Approval Gate):** Added the supervisory gate for high-stakes documents, distinguishing fabricated specifics from honest missing SOP notices.
- **Phase 12 (Hardening & Regression):** Enforced planner soft ceilings, eliminated prompt example leaks, added live UI elapsed-time tickers, and passed full 7-flow regression testing.

### Post–Phase 12 (live product — not a freeze)
- **React operator console** became the default `GET /` (Vite `dist/` served by FastAPI). Vanilla remains at `/vanilla`.
- **JWT auth + PostgreSQL** persistence: users, chats, messages; later `agent_memory` and `agent_runs` (Alembic `002`, 2026-09-08). Host port moved to **5434** to avoid local Postgres collisions.
- **Master Planner** replaced the single-shot 1–3 step planner; per-step router switches models; key-fact memory is passed across sub-tasks.
- **SSE streaming** (`GET /run/stream` + `event_bus.py`) replaced vanilla’s post-hoc audit polling as the primary live UX.
- **Clarification loop:** observe may pause; `POST /run/{task_id}/reply` resumes from `state_snapshot`.
- **Model Settings:** pull with SSE progress, cancel, assign roles, delete.
- **Multi-language sandbox:** Python, JavaScript, and C; interactive `/code/run` cards in `MessageTurn`.
- **Package rename:** `backend/sovereignty/` → `backend/shield/`; sandbox lives under `backend/tools/sandbox.py`.
- **Model lineup:** reasoning `gemma3:4b`, code `granite4.1:3b`, vision `gemma3:4b`, embeddings `nomic-embed-text:latest`. The dedicated 1.5B router and Moondream are retired.
- **Router rewrite:** keyword scoring first; LLM classify only on ambiguity.

---

## 7. Infrastructure & Presentation Topology

KAVACH is a **host-native FastAPI process** plus local Ollama. Docker Compose runs **PostgreSQL only** (and optionally the Vite frontend). The backend is not containerized because Shield needs host `psutil` and Windows `netsh`.

```
[Laptop 1: Primary Driver / Server]
├── FastAPI Application (Port 8000) — python -m uvicorn backend.main:app
├── Ollama Inference Engine (11434)
├── Docker Desktop Daemon
│     ├── kavach_postgres  (host 5434 → container 5432)
│     └── ephemeral sandbox images (python:3.11-slim, node:20-slim, gcc:13-slim)
├── Optional Vite dev UI (Port 3000)  or  Compose frontend (Port 5173)
└── Production-style UI: React dist served from FastAPI at http://127.0.0.1:8000

[Laptop 2: Hot-Standby Mirror]
├── Identical clone of repo & .venv
├── Pre-pulled Ollama models & Docker images
└── Ready for instantaneous IP switch if hardware fails

[Laptop 3: Live Audit & Evaluator Console]
├── Real-Time Audit Log Terminal (tail -f outputs/audit_log.jsonl)
├── Wireshark / Network Packet Monitor (proving 0 egress packets)
└── Shield WebSocket view in the operator console
```

Operator setup (venv, compose, alembic, models) is documented in `startup.md`. Default database URL: `postgresql://kavach:kavach_secret@127.0.0.1:5434/kavach_db`.

---

## 8. Current State & Readiness

KAVACH is a working **multi-user on-prem operator console**, not a Phase 12 code freeze.

**What evaluators see today:**
- Sign-in / register, persistent chats, live SSE agent traces, clarification cards, document approval, interactive sandbox, Knowledge Vault upload, Audit Log, Model Settings, and a Shield connection bar with lockdown.
- Local models only: gemma3:4b reasoning & vision, granite4.1:3b coder, nomic embeddings.
- Postgres on **5434**, FAISS vault on disk, JSONL audit, Windows Shield monitor.

**Project tree (live):**

```
kavach/
├── backend/
│   ├── auth/            # JWT register / login / cookie session
│   ├── audit/           # Append-only JSONL logbook
│   ├── brain/           # LangGraph agent, router, event_bus, tools_dispatch
│   ├── chat/            # Persistent chat API
│   ├── db/              # SQLAlchemy models & session (Postgres)
│   ├── engine/          # Ollama client & models.json registry
│   ├── guard/           # Claim verify + human approval gate
│   ├── shield/          # Firewall lockdown & live socket monitor
│   ├── tools/           # search, writer, code, sandbox, calc, ocr, vision
│   ├── vault/           # FAISS ingest + retrieve
│   ├── config.py
│   ├── main.py
│   └── models.json
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
├── startup.md           # Current developer quickstart
└── KAVACH_CONTEXT.md    # This document
```

**Not in this product:** public-cloud LLMs, INCOIS / coastal alert pipelines, SMS / FCM, maps, mobile apps, or database-backed RBAC.

---

## 9. Future Extensibility Roadmap

The KAVACH architecture is built to support future enterprise enhancements without structural rewrites:
1. **Role-Based Access Control (RBAC):** User roles in Postgres, gated vault / shield / model / approval APIs, and cryptographic user identity on every audit event.
2. **Durable approval queue:** Persist Human Approval Gate records so a restart does not drop a pending supervisor sign-off.
3. **Hash-chained audit log:** Restore SHA-256 prev-hash linking on `audit_log.jsonl` if evaluators require a tamper-evident chain.
4. **Strict air-gap fonts:** Self-host Inter / Source Serif 4 (or drop the Google Fonts `<link>`) so the React shell makes zero WAN requests.
5. **Hybrid BM25 + Dense Retrieval:** Combining keyword lexical search with dense vector embeddings for highly specialized chemical engineering terms.
6. **Automated Presentation Generator:** Extending the document writer engine to generate `.pptx` slide summaries using `python-pptx`.
7. **Air-Gapped Voice Interface:** Local Whisper transcription and Piper speech synthesis for hands-free field maintenance inspections.

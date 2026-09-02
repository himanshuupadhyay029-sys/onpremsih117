# KAVACH — Master Kickoff Prompt (fresh build)
### Paste this into Antigravity on the SERVER laptop (Himanshu's), in an empty project folder.

**Before you paste:** attach two files to the IDE context — `KAVACH_Finalized_Architecture.md` (or the merged architecture) and `KAVACH_Laptop_Setup_Plan.md`. This is a clean-slate build in a completely empty folder.

**Current machine state (tell the agent this is the starting point):** only the Antigravity IDE and the Ollama app are installed. **Nothing else** — no Python packages, no models pulled, no Docker, no virtual environment. So this first task must NOT assume anything is installed. The agent should create files and folder structure, and give YOU a list of terminal commands to run yourself (installs, model pulls, venv). You run them personally, one at a time, so you can watch each finish. The agent should not attempt large downloads on its own.

---

## THE PROMPT (copy everything below)

```
You are the lead engineer building KAVACH, a sovereign, fully-offline, on-premise
agentic AI workbench for the Smart India Hackathon problem SIH26117 (client: MRPL,
a refinery). The two attached documents — the final architecture and the laptop
setup plan — are the SINGLE SOURCE OF TRUTH. Read both fully before writing any code.

=== ENVIRONMENT (do not deviate) ===
- OS: Windows. Target Python: 3.11 ONLY (not 3.13/3.14 — later OCR libraries require 3.11).
- CURRENT STATE OF THIS MACHINE: only the Antigravity IDE and the Ollama app are installed.
  Nothing else yet — no Python virtual environment, no pip packages, no models pulled, no
  Docker. Do NOT assume any dependency or model is present.
- This machine is the single server: it runs the app, the models, and the demo.
- Local models will be served by Ollama at http://localhost:11434 once pulled. The models
  we will use: qwen2.5:3b-instruct, qwen2.5-coder:3b, qwen2.5-vl:3b, nomic-embed-text.
- ABSOLUTE RULE: no code may ever call the internet or any cloud API. Everything is
  local. Disable all LangChain/LangSmith telemetry (set LANGCHAIN_TRACING_V2=false and
  ensure no tracing/API-key env vars are used).

=== HOW YOU (THE AGENT) AND I (THE USER) DIVIDE THE WORK ===
- YOU create files, folders, and write code.
- I run all terminal commands myself (installs, venv creation, model pulls, running the
  server). Do NOT run large downloads or installs yourself — instead, give me a clearly
  numbered list of exact commands to paste into my terminal, in order, with a one-line note
  of what each does and what I should see when it succeeds. I will run them and report back.

=== LOCKED TECH STACK (use exactly these) ===
- Backend: FastAPI + Uvicorn + Pydantic (async).
- Agent engine: LangGraph (+ langchain-core), tracing disabled.
- Model serving: Ollama, accessed via a thin local HTTP client.
- RAG: FAISS (IndexFlatL2) + nomic-embed-text embeddings.
- Code sandbox: Docker container run with --network none (built in a LATER prompt).
- Documents: python-docx.
- Audit: append-only JSONL file.
- Frontend: a single static HTML page to start (no React yet).

=== SCOPE OF THIS TASK — READ CAREFULLY ===
This is the INITIAL SETUP task only (Phase 0). Goal: create the project skeleton and give
me the commands to prepare my machine. We are NOT finishing the project now — later prompts
add each real feature. Keep this minimal and correct.

DO build now (files/folders only — no downloads):
1. The full folder structure from the architecture (app/agent, app/models, app/routers,
   app/services, app/static, plus scripts/, sample_docs/, test_data/, generated/), with
   empty __init__.py files where needed.
2. requirements.txt (Python 3.11 compatible, versions pinned to known-good combos):
   fastapi, uvicorn[standard], pydantic, httpx, python-multipart, faiss-cpu, numpy,
   langgraph, langchain-core, python-docx, psutil.
3. app/config.py — one central config: Ollama base URL, model_registry.json path, and
   paths for faiss index / outputs / audit log. No hardcoded model names elsewhere.
4. model_registry.json — mapping {"reasoning":"qwen2.5:3b-instruct",
   "code":"qwen2.5-coder:3b","vision":"qwen2.5-vl:3b","fast":"qwen2.5:3b-instruct"}.
5. app/services/model_registry.py — reads the json, supports hot-swap, and a thin Ollama
   client (functions for /api/tags, /api/generate, /api/embeddings). Code only; it will be
   exercised after I pull models.
6. app/services/audit.py — append-only JSONL logger (timestamp, task_type, model_or_tool,
   summary, metadata, external_calls=0); non-blocking / exception-safe.
7. The CONTRACTS as stubs (shapes now, logic later):
   - app/agent/state.py: AgentState TypedDict {task, subtasks, trace(additive), result}.
   - app/agent/tools.py: a Tool base interface {name, description, input_schema, execute()}.
   - app/agent/graph.py: a minimal LangGraph with ONE echo node that puts the task into the
     trace and returns.
8. app/main.py + routers: GET /health -> {"status":"ok"}; GET /models; PUT /models/{task_type};
   POST /generate ({task_type,prompt}); POST /agent/run (runs the echo graph); serve /ui.
9. app/static/ui.html — minimal dark/industrial page: title bar, task input + submit calling
   /generate, an output area, and an empty placeholder panel labelled "Sovereignty Monitor".
10. .gitignore (.venv/, __pycache__/, faiss_index/, outputs/, audit_log.jsonl, *.pyc).
11. A short README.md with the run steps.

DO NOT build now (later prompts — do not start):
- OCR / PyMuPDF / PaddleOCR
- Vision / Qwen2.5-VL integration
- The sovereignty firewall + live network monitor + WebSocket
- FAISS ingestion/retrieval logic beyond empty stubs
- Docker code execution
- Calculation, verification, human-approval gate
- Any real agent reasoning nodes beyond the echo node

=== THE COMMANDS I WILL RUN MYSELF (give me these as a numbered list) ===
After creating the files, produce a clear ordered command list for me to run in my own
terminal (Windows). Include, with a one-line "what this does / what success looks like" for each:
- Creating the Python 3.11 virtual environment and activating it.
- Installing requirements.txt into it.
- Pulling the four Ollama models (qwen2.5:3b-instruct, qwen2.5-coder:3b, qwen2.5-vl:3b,
  nomic-embed-text) — note these are large, run one at a time.
- Setting OLLAMA_HOST=0.0.0.0 and finding my LAN IP (ipconfig).
- Starting the server (uvicorn app.main:app --port 8000).
Do NOT run these yourself. Just give me the list and wait.

=== CONVENTIONS ===
- Small, single-purpose modules. Clear names matching the architecture.
- All paths Windows-safe. All config centralized in app/config.py.
- No model name hardcoded outside model_registry.json.
- Every endpoint writes an audit entry.

=== WHEN DONE — REPORT (do not try to run the app yet) ===
Because nothing is installed yet, you cannot run the server. So instead:
1. Print a table of every file/folder you created with a one-line purpose each.
2. Confirm the code imports are internally consistent (no obvious missing references).
3. Give me the numbered terminal command list described above.
Then STOP and wait. After I run the commands (venv, install, model pulls, start server),
I will report back and THEN we verify these together, showing actual output:
- GET /health returns {"status":"ok"}
- GET /models lists the installed Ollama models
- POST /generate ({"task_type":"reasoning","prompt":"Say hello in one sentence"}) returns
  REAL text from qwen2.5:3b-instruct
- POST /agent/run ({"task":"test"}) returns a trace from the echo node
- /ui loads and audit_log.jsonl has entries
Do not build anything from the "DO NOT build now" list.
```

---

## After this prompt runs

1. The agent gives you: the created files + a **numbered command list**. Nothing is running yet — that's expected.
2. **You run the commands yourself**, one at a time, in your terminal: create the Python 3.11 venv, `pip install -r requirements.txt`, pull the four Ollama models (large — one at a time), set `OLLAMA_HOST=0.0.0.0`, then start the server with `uvicorn app.main:app --port 8000`.
3. Then verify together: `/health`, `/models`, a real `/generate` reply, the echo `/agent/run`, `/ui` loads, and `audit_log.jsonl` has entries.
4. Send me the result. If green, next is **Prompt 2 — the sovereignty proof**. If a command or check fails, tell me which one and we fix it before moving on.
5. Push this foundation to git so Harshit can clone the backup twin.

## Why the prompt is shaped this way
- The agent writes files; **you run the installs and downloads** — so you watch each finish and catch failures early, and the agent never silently burns time on a stalled download.
- It builds only the skeleton + a running foundation, not the whole system — one working slice beats ten half-built modules.
- It locks the folder structure and the "contracts" now, so every later prompt slots in cleanly.
- It explicitly fences off the hard features (OCR, sovereignty, vision) so the agent doesn't half-start them and leave a mess.

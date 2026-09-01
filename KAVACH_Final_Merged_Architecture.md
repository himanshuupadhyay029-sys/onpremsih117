# KAVACH — Final Merged Architecture (built on Alok's working codebase)
### SIH26117 · supersedes the earlier greenfield architecture

**What changed:** the base is no longer a blank repo. **Alok's project is a running skeleton and becomes our foundation.** We keep what already works, and bolt the finale-critical layers on top. This document is the merge map: what to KEEP, what to MODIFY, what to ADD.

**Locked decisions (this session):**
1. **Foundation = Alok's codebase.** It runs. We build on it, not from zero.
2. **Keep LangGraph** (it works). Sovereignty is proven at the network layer (firewall + monitor + physical disconnect), not by avoiding a framework. Disable LangChain tracing explicitly.
3. **One codebase, one IDE driver.** One person implements (Antigravity/Claude Code) from prompts. Other laptops = infra (model serving) + demo-data + testing + rehearsal.
4. **Server = RTX 3050 / 16 GB laptop.** Runs the app + primary Ollama.

---

## 1. The merge map — KEEP / MODIFY / ADD against Alok's real code

### ✅ KEEP AS-IS (already built and good — do not rebuild)
| Component | Alok's file | Why keep |
|---|---|---|
| FastAPI backend + async | `app/main.py`, `app/routers/*` | Working spine. |
| **Model registry with live hot-swap** | `app/services/model_registry.py`, `PUT /models/{task_type}` | *Better than our YAML plan.* API-driven, atomic writes, reads Ollama `/api/tags`. Directly satisfies the PS "add models without redesign" — and it's demoable live in the UI. Adopt this, drop the YAML idea. |
| FAISS RAG (ingest + retrieve + grounded prompt) | `app/services/ingest.py`, `retrieval.py` | Working vector search with strict grounding + source citation. Keep FAISS; drop ChromaDB from the old doc. |
| **Docker sandbox** | `app/services/code_execution.py` | Already hardened: `--network none`, 128 MB cap, 10s timeout, read-only mount, temp cleanup. This was a top risk in our doc — Alok solved it. Keep exactly. |
| LangGraph agent + Thought→Action→Observation trace | `app/agent/graph.py`, `nodes.py`, `state.py` | Real planner→router→execute→trace, persisted to audit. This IS your "it's really an agent" evidence. |
| docx generation (styled) | `app/services/docx_generation.py` | Professional formatting already done. |
| Audit log (JSONL, non-blocking) | `app/services/audit.py` | Keep; we extend the schema (below). |
| Working UI + `/generate` tester | `app/static/ui.html`, `/models`, `/generate` | Himanshu's frontend starting point — already wired. Extend it, don't rewrite (vanilla HTML is faster than a React rewrite; React only if time allows). |

### 🔧 MODIFY (exists, but must change for the PS)
| Component | Change needed | Why |
|---|---|---|
| Ingestion (`ingest.py`) | Accept **PDFs and images**, routing them through the new OCR service — not just `.md`/`.txt` | PS demands scanned docs; Alok only ingests clean text. |
| Model lineup | Default `reasoning` to **`qwen2.5:3b-instruct`** for demo speed (keep `7b-instruct` as a hot-swap option); **add `qwen2.5-vl:3b`** for vision | 7B on 4 GB VRAM is the latency risk; the hot-swap registry makes this a one-click choice. Vision model is net-new. |
| Planner node (`nodes.py`) | Detect image/scanned input and add an OCR/vision subtask type; add `calculation` and `verify` subtask types | Current planner only knows retrieval/code/draft. |
| Audit schema (`audit.py`) | Add `external_calls: 0` (fed by the network monitor) per task | Turns the audit log into sovereignty evidence. |
| LangChain config | Explicitly disable tracing (`LANGCHAIN_TRACING_V2=false`, no LangSmith keys); verify with the monitor | Removes the only realistic egress path from the framework. |

### ➕ ADD (net-new — these are the finale-critical layers Alok's code is missing)
| New component | New file(s) | Priority |
|---|---|---|
| **Sovereignty proof** — OS firewall default-deny + `psutil` live network monitor + `/network/monitor` WebSocket + physical-disconnect demo | `app/security/firewall_setup.(sh\|ps1)`, `app/services/network_monitor.py` | **P0 — #1 graded item** |
| **OCR pipeline** — PyMuPDF (render/text-detect) + PaddleOCR (text + confidence + tables) | `app/services/ocr.py` | **P0 — PS multimodal** |
| **Vision** — Qwen2.5-VL via Ollama for drawings/photos (assisted understanding) | `app/services/vision.py` (or a `vision` task_type in the registry) | **P0 — PS multimodal** |
| **Calculation-with-steps** — LLM extracts formula+vars → **Python computes** → returns steps | `app/services/calculation.py` + a `calculation_node` | P1 — PS "calculations with steps" |
| **Verification** — citation-presence check (claims map to retrieved sources) | `app/services/verification.py` + a `verify_node` | P1 — differentiator |
| **Human-approval gate** — high-risk tasks pause for approve/reject | approval state in agent + UI modal | P1 — differentiator for PSU/defence |
| **UI panels** — Sovereignty monitor (live), Agent Progress (live trace), Knowledge Vault (upload + indexed state), Approval modal, Output/download | extend `ui.html` | P0/P1 |
| File-upload task path + `/knowledge/ingest` for arbitrary docs | `app/routers/agent.py`, `rag.py` | P0 |

**The headline:** Alok's code gives you the *agent + RAG + sandbox + docx + registry + UI* for free. The two things you must build that he doesn't have — and that the PS grades hardest — are **the sovereignty proof** and **multimodal (OCR/vision)**. That's where your build energy goes.

---

## 2. Final locked tech stack (reconciled)

| Layer | Choice (final) | Source |
|---|---|---|
| Backend | FastAPI + Uvicorn + Pydantic | Alok (keep) |
| Agent engine | **LangGraph** + langchain-core, tracing disabled | Alok (keep) |
| Model serving | Ollama on the RTX 3050 server, LAN-exposed (`OLLAMA_HOST=0.0.0.0`) | Alok (keep) |
| Models | `qwen2.5:3b-instruct` (reasoning default) · `qwen2.5-coder:3b` (code) · **`qwen2.5-vl:3b` (vision — NEW)** · `nomic-embed-text` (embed) · `qwen2.5:7b-instruct` hot-swap option | merged |
| RAG / vectors | **FAISS** (IndexFlatL2) + grounded prompt + citations | Alok (keep; drop ChromaDB) |
| Model registry | **API hot-swap** (`PUT /models/{task_type}`) | Alok (keep; drop YAML) |
| OCR / Vision | **PyMuPDF + PaddleOCR + Qwen2.5-VL** | NEW |
| Sandbox | **Docker `--network none`**, 128 MB, 10s, ro mount | Alok (keep) |
| Deliverables | python-docx (keep) + openpyxl/calc (add) | merged |
| Sovereignty proof | **OS firewall default-deny + psutil monitor + physical disconnect** | NEW |
| Audit | JSONL append-only + `external_calls` field | Alok (modify) |
| Frontend | Extend Alok's vanilla HTML UI (React only if time) | Alok (keep/extend) |

---

## 3. How the team actually works (single codebase + infra laptops)

```
        ┌──────────────────────────────────────────────────────┐
        │  DRIVER (1 person) — one IDE agent, one codebase      │
        │  Antigravity / Claude Code, implementing the prompts  │
        │  Runs the app on the RTX 3050 server laptop           │
        └───────────────────────────┬──────────────────────────┘
                                    │ calls over LAN
        ┌───────────────────────────▼──────────────────────────┐
        │  INFRA LAPTOPS (the other 3)                          │
        │  • Run Ollama, pull + serve models over LAN           │
        │  • Prep demo data (sample scanned reports, SOPs)      │
        │  • Test each feature on unseen input                  │
        │  • Own demo rehearsal + Q&A prep                      │
        └───────────────────────────────────────────────────────┘
```

- **Himanshu (you):** relay prompts to the driver, own integration + the demo narrative + which features ship. You hold the whole picture.
- **The driver:** one person, one IDE, implements prompt-by-prompt so the codebase stays coherent.
- **Harshit:** owns the RTX 3050 server — Ollama, model pulls, the firewall + network-monitor setup, and validating the sovereignty proof physically.
- **Sara / Mokshit:** prep the demo corpus (real-looking refinery SOPs, scanned inspection reports, a P&ID/drawing sample), test OCR/RAG/sandbox on unseen inputs, run the 20× rehearsal.

Only the RTX 3050 must serve the big models. Other laptops can pull a small model each as backups, but the demo runs off the server.

---

## 4. The finale-critical additions, explained (what Alok's code lacks)

**4.1 Sovereignty proof (P0, #1 graded).** Three layers: (A) physical disconnect — server runs WiFi-off / cable-out, visible on screen, hotspot-only for clients; (B) OS firewall default-deny egress applied before Ollama starts (`iptables` on Linux / Windows Defender Firewall outbound-block); (C) `psutil.net_connections()` polled every 500 ms, classifying localhost/subnet/external, streamed to a live UI panel (green = safe) and appended to a session log. The audit log records `external_calls: 0` per task. *This is the difference between "we say it's offline" and "we prove it."*

**4.2 OCR + vision (P0, the biggest net-new).** PyMuPDF opens the PDF, extracts embedded text if present, else renders pages to 300 DPI PNG → PaddleOCR (text + confidence + tables). For drawings/photos, the page image goes to Qwen2.5-VL with structured questions ("list equipment tags"). Honest scope: assisted understanding, confidence shown, low-confidence flagged for human. This feeds the modified `ingest.py` and a new OCR/vision agent node. **This is the largest and riskiest addition — start it early.**

**4.3 Calculation-with-steps (P1).** The LLM identifies the formula and variables; **Python does the arithmetic**; output shows formula → inputs → steps → result. Fold a refinery calc (corrosion rate → remaining life, or pressure loss) into the flagship for domain fit.

**4.4 Verification (P1).** After a draft, check each key claim maps to a retrieved FAISS source; flag unsupported claims. A light, real hallucination check — not the enterprise "firewall."

**4.5 Human-approval gate (P1).** High-risk tasks (approval notes, financial) pause with a UI modal (risk/confidence/evidence + Approve/Reject). Cheap, and it resonates hard with a PSU/defence panel: the AI never auto-issues a consequential document.

---

## 5. Updated system architecture

```text
┌───────────────────────────────────────────────────────────────┐
│ UI (extend Alok's ui.html): Task+upload · Agent Progress(live) │
│ · Sovereignty monitor(live) · Knowledge Vault · Approval · Out │
└───────────────────────────┬───────────────────────────────────┘
                            │ REST + WS (LAN only)
┌───────────────────────────▼───────────────────────────────────┐
│ FASTAPI (Alok) — /agent/run /ask /models /generate            │
│                  + /tasks(upload) /knowledge/ingest /network(WS)│
└───────────────────────────┬───────────────────────────────────┘
                            │
┌───────────────────────────▼───────────────────────────────────┐
│ LANGGRAPH AGENT (Alok) — planner → router → nodes → trace      │
│  nodes: retrieval · code_exec · docx  (KEEP)                   │
│       + ocr/vision · calculation · verify · approval  (ADD)    │
└───┬───────────────┬───────────────┬───────────────┬───────────┘
    ▼               ▼               ▼               ▼
┌────────┐   ┌──────────────┐  ┌──────────┐  ┌──────────────────┐
│ MODEL  │   │ OCR/VISION   │  │ FAISS    │  │ DOCKER SANDBOX   │
│REGISTRY│   │ PyMuPDF+     │  │ RAG      │  │ --network none   │
│hot-swap│   │ PaddleOCR+   │  │ (Alok)   │  │ (Alok)           │
│(Alok)  │   │ Qwen-VL (NEW)│  │          │  │                  │
└───┬────┘   └──────────────┘  └──────────┘  └──────────────────┘
    ▼ Ollama (RTX 3050 server, LAN)
┌────────────────────────────────────────────────────────────────┐
│ VERIFICATION (NEW) · AUDIT JSONL +external_calls (Alok+mod)     │
├────────────────────────────────────────────────────────────────┤
│ SOVEREIGNTY (NEW): firewall default-deny + psutil monitor +     │
│ physical disconnect  →  proven 0 external                       │
└────────────────────────────────────────────────────────────────┘
```

---

## 6. Build order (given a working base already exists)

Because Alok's spine runs, you're not building bottom-up — you're **hardening + extending**.

1. **Get Alok's project running on the RTX 3050 server**, models pulled, `/agent/run` working end-to-end (RAG + code + docx). Confirm the baseline before touching anything. *(infra + driver)*
2. **Sovereignty proof** — firewall + psutil monitor + physical disconnect + `external_calls` in audit. Validate the #1 graded claim first. *(Harshit + driver)*
3. **OCR + vision** — `ocr.py`, `vision.py`, modify `ingest.py` and the planner to handle scanned/image input. The biggest net-new; start early. *(driver + Sara/Mokshit test)*
4. **Flagship end-to-end on a scanned report** — upload scan → OCR → FAISS retrieve (cited) → findings → calc-with-steps → docx, all via the agent, watchable live.
5. **Calculation + verification + approval gate.** *(driver)*
6. **UI panels** — Sovereignty (live), Agent Progress (live trace), Knowledge Vault, Approval, Output/download. Extend `ui.html`. *(driver, Himanshu owns look)*
7. **Freeze + rehearse 20×** on unseen input; assign Q&A. *(Sara/Mokshit)*

---

## 7. The one honest risk

Two things carry the finale and neither exists in Alok's code yet: **the sovereignty proof** and **multimodal OCR/vision**. Everything else you're mostly inheriting. So do not let the comfort of a working skeleton lull you into polishing what already works — put your scarce build time on those two. And PaddleOCR is the install most likely to eat a day: pull it on an infra laptop first thing and confirm it reads a sample scan before the driver wires it in.

---

## 8. What's next

You said you'll ask after this — the natural next step is a **sequenced set of implementation prompts** for the IDE driver: prompt 1 (stand up Alok's base on the server), prompt 2 (sovereignty proof), prompt 3 (OCR/vision), prompt 4 (flagship wiring), etc. — each written so the driver can paste it into Antigravity/Claude Code and build one verified slice at a time.

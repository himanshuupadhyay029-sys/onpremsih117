# KAVACH — Finalized System Architecture & Implementation Plan
### SIH26117: Sovereign On-Premise Agentic AI Workbench (MRPL)

**Status:** This is the merged, decision-locked architecture, synthesized from all three team drafts (Team Lead's spec, KAVACH_Final, sovereign_workbench, Antigravity) and the finale-readiness review. Where the drafts disagreed, the conflict is resolved here with the reasoning stated, so it can be defended in Q&A. Hand this to the coding agent as build context.

**Product name:** **KAVACH** (कवच = "shield/armour"). Fits the sovereignty/defence framing and the Indian-PSU audience. "Antigravity" was a working codename — retire it. Backronym for the pitch: **K**nowledge-grounded · **A**ir-gapped · **V**erifiable · **A**gentic · **C**onfidential · **H**ybrid-intelligence workbench.

**Positioning (use verbatim in the PPT):**
> KAVACH is not a local ChatGPT. It is a secure on-premise AI workforce that reads confidential documents, selects the right local model for the task, plans and executes multi-step work with real tools, verifies its own output, produces real Word/Excel/code deliverables, and *proves* — live, at the kernel level — that the data never left the building.

---

## 0. The single most important discipline in this document: BUILT vs ROADMAP

You have been rejected twice at the prototype/PPT stage. The most common way that happens is **overclaiming** — a slide says "RBAC + data classification + hybrid retrieval + hallucination firewall" and a judge asks to see one of them and it isn't there. From that moment the panel distrusts every other claim.

So every capability below is tagged:
- **[BUILT]** — must be working and demoable on unseen input by the finale. Claim it freely.
- **[ROADMAP]** — the architecture *supports* it, we have the hook, we did not build it. Say exactly that: *"the architecture supports it; for the prototype we scoped it out deliberately."* That sentence is a strength, not a weakness — it signals engineering judgment.

Never blur the line. A judge respects "we chose not to build X in 48 hours" far more than a broken X.

---

## 1. Non-negotiable constraints (locked)

1. **Zero external network calls** during inference, OCR, RAG, tool execution, or file generation. This is the single most-graded requirement. Enforced at the OS/kernel level, not in application code, and proven live. **[BUILT]**
2. No cloud APIs anywhere in the pipeline (no OpenAI/Anthropic/cloud-OCR/cloud-vector-DB/cloud-telemetry). **[BUILT]**
3. Runs on the team's real hardware: one RTX 3050 (4 GB VRAM) + 16 GB RAM laptop as the server. No server-grade assumption. **[BUILT]**
4. Nothing hardcoded to a specific test file — every stage generalizes to unseen input at demo time. **[BUILT]**
5. Single-machine-deployable. The whole stack runs on one box; other laptops are just browsers. This directly answers the PS's "demonstrable on a single workstation." **[BUILT]**

---

## 2. Deployment topology (locked) — "one machine is the server"

This resolves the multi-node fragility flagged in the review. **Do not distribute models across 4 GB laptops.** Concentrate compute on one machine.

| Machine | Role | Runs |
|---|---|---|
| **Server (RTX 3050, 4 GB VRAM, 16 GB RAM)** | Everything | Ollama, FastAPI backend, agent orchestrator, all tools, Docker sandbox, ChromaDB, network monitor, audit DB |
| **Laptops 2–4** | Thin clients | A browser pointed at `http://<server-lan-ip>:8000`. Nothing else. |

**Why single-server:** avoids live LAN failures (a node dropping off wifi mid-demo), concentrates the scarce VRAM, and matches the PS's "single workstation" framing. Sequential model loading (Ollama handles this) means only one LLM occupies the GPU at a time; the embedding model stays on CPU.

**OS decision (important — none of the drafts caught this):** the kernel-level network proof (`iptables`) and clean Docker only work on **Linux**. Your RTX 3050 laptop is almost certainly Windows.
- **Preferred:** dedicate the server laptop to **Ubuntu 22.04** for the demo. Makes iptables, Docker, and the network monitor clean and the sovereignty story airtight. Set this up on Day 1 if you commit to it.
- **Fallback (if Linux setup risks eating your 2 days):** stay on Windows — use **Windows Defender Firewall** outbound-block rules, a **cross-platform `psutil`-based** network monitor (works on both OSes), and the subprocess sandbox fallback (§9). You lose kernel-purity but keep the proof via physical disconnect + firewall + monitor.
- **Universal, OS-independent, do-this-regardless:** on demo day the server runs with **WiFi off and ethernet unplugged**, visibly, on screen. If clients need the UI, the server hosts a local WiFi hotspot whose subnet has no internet route. Physical disconnect is the most visceral proof a judge understands instantly.

---

## 3. Full system architecture

```text
┌───────────────────────────────────────────────────────────────┐
│ CLIENT LAYER — browsers on laptops 2–4 (LAN/hotspot only)      │
│ Task input · Agent Progress · Deliverables · Knowledge Vault   │
│ · SOVEREIGNTY / Network Monitor panel (always visible)         │
└───────────────────────────┬───────────────────────────────────┘
                            │ REST + WebSocket, localhost/LAN only
┌───────────────────────────▼───────────────────────────────────┐
│ FASTAPI BACKEND (async) — no public exposure                   │
└───────────────────────────┬───────────────────────────────────┘
                            │
┌───────────────────────────▼───────────────────────────────────┐
│ INTELLIGENCE LAYER                                             │
│  ┌─────────────────┐        ┌──────────────────────────────┐   │
│  │ TASK ROUTER     │──────▶ │ AGENT ORCHESTRATOR (ReAct)   │   │
│  │ rule-based,     │        │ Plan → Act → Observe → Iterate│   │
│  │ <50ms, no LLM;  │        │ AgentState · self-correction  │   │
│  │ LLM fallback    │        │ up to 10 steps · full log     │   │
│  │ for ambiguity   │        └───────────────┬──────────────┘   │
│  └─────────────────┘                        │                  │
└─────────────────────────────────────────────┼──────────────────┘
                                              │
┌──────────────────────────────────────────────▼─────────────────┐
│ TOOL LAYER (typed, schema-validated, policy-gated)             │
│ read_file · write_file · ocr_document · analyze_image ·         │
│ search_kb · execute_code · calculate · generate_docx/xlsx/pptx │
└───┬───────────────┬───────────────┬───────────────┬────────────┘
    ▼               ▼               ▼               ▼
┌────────┐   ┌──────────────┐  ┌──────────┐  ┌──────────────────┐
│ MODEL  │   │ OCR / VISION │  │ LOCAL    │  │ DELIVERABLE      │
│ SERVING│   │ PyMuPDF +    │  │ RAG      │  │ FACTORY          │
│ Ollama │   │ PaddleOCR +  │  │ ChromaDB │  │ struct JSON →    │
│ (regis-│   │ Qwen-VL      │  │ + nomic  │  │ python-docx/     │
│ try)   │   │              │  │ + MMR    │  │ openpyxl/pptx    │
└────────┘   └──────────────┘  └──────────┘  └──────────────────┘
    │
    ▼
┌────────────────────────────────────────────────────────────────┐
│ VERIFICATION (light-but-real): code tests · deterministic calc │
│ · citation-presence check                                      │
└───────────────────────────┬────────────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────────────┐
│ GOVERNANCE: Autonomy Governor (low→auto / med→review /          │
│ high→mandatory human approval) + approval UI gate               │
└───────────────────────────┬────────────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────────────┐
│ SECURITY & AUDIT: OS firewall default-deny egress (enforcement) │
│ + psutil network monitor (visibility) + SQLite audit log        │
└────────────────────────────────────────────────────────────────┘

Underneath everything: HOST IS AIR-GAPPED. External calls = 0. Provable.
```

---

## 4. Model layer — exact lineup, rationale, and extensibility

### 4.1 The lineup (three distinct models + embeddings)

This resolves the "one model vs three" conflict. The PS's *own* example of model auto-selection is "a coding request handled differently from a document summary request," so the coding task should visibly use a **different model** — otherwise your answer to "show me model selection across task types" is weak. Three models = unambiguous compliance.

**Demo default (optimised for your 4 GB machine — reliability over raw quality):**

| Role | Model (Ollama tag) | ~Size Q4 | Device | Why |
|---|---|---|---|---|
| Reasoning / documents | `qwen2.5:3b-instruct-q4_K_M` (or `qwen3:4b`) | ~2–2.6 GB | GPU (active) | Strong instruction-following & structured JSON output; small enough to load fast and reduce swap latency |
| Coding | `qwen2.5-coder:3b-q4_K_M` | ~2 GB | GPU (active) | Coding-specialised; distinct model for the coding task = clean model-selection story |
| Vision / multimodal | `qwen2.5-vl:3b-q4_K_M` | ~2.5–3 GB | GPU (active) | Genuinely reads tables, layouts, drawings — not just captions. Handles the multimodal requirement |
| Embeddings | `nomic-embed-text:v1.5` | ~0.3 GB | **CPU, always loaded** | 768-dim, good on technical English; tiny; must always be available for RAG |

**Quality-upgrade config (if the venue gives you a better GPU):** swap the 3B tags for `qwen2.5:7b-instruct-q4_K_M`, `qwen2.5-coder:7b`, `qwen2.5-vl:7b`. **This is a one-line change per model in the registry (§4.2) — no code change.** That swap is itself a live demonstration of the extensibility requirement.

> **Action this week:** benchmark BOTH 3B and 7B on the actual server laptop for tokens/sec, first-token latency, and VRAM. Pick the largest lineup that keeps a full approval-note generation under ~30 s. Sequential loading means one LLM on GPU at a time; Ollama offloads overflow layers to the 16 GB RAM automatically.

### 4.2 Model Registry — the extensibility mechanism [BUILT]

The PS explicitly requires: *"New open weight models should be addable later without redesigning the system."* Most teams miss this. You answer it **architecturally**, not by promise, with a YAML registry the router reads:

```yaml
# models.yaml — single source of truth. Add a model = add a block. No code change.
models:
  reasoning:
    ollama_tag: qwen2.5:3b-instruct-q4_K_M
    task_types: [document_analysis, summarization, drafting, general, calculation]
    context_window: 8192
    device: gpu
  coding:
    ollama_tag: qwen2.5-coder:3b-q4_K_M
    task_types: [code_generation, debugging, script]
    context_window: 8192
    device: gpu
  vision:
    ollama_tag: qwen2.5-vl:3b-q4_K_M
    task_types: [image_understanding, drawing_analysis, complex_ocr]
    context_window: 4096
    device: gpu
  embedding:
    ollama_tag: nomic-embed-text:v1.5
    always_loaded: true
    device: cpu
```

A generic model adapter exposes `generate()`, `stream()`, `embed()`, `vision()` so the rest of the system never knows which inference engine is behind it. **Demo move:** during Q&A, add a fourth model block live, restart, and show it appear in the model registry UI. That is the extensibility requirement, proven.

---

## 5. Network sovereignty — the #1 graded claim, done for real [BUILT]

The review's top finding: the original "🔒 offline" badge was decorative. It is now **three layers: enforcement + proof + visibility.** All three are shown live.

**Layer A — Physical air-gap (universal proof).** Server runs WiFi-off, ethernet-unplugged, on screen. If clients need access, server hosts a local hotspot with no internet uplink. A judge sees the machine is physically disconnected and the whole system still works. This alone is most of the proof.

**Layer B — OS firewall default-deny egress (enforcement).** Applied *before* Ollama starts, so even a rogue dependency cannot phone home.
- Linux: `iptables -P OUTPUT DROP`, then ACCEPT loopback and local subnet only.
  ```bash
  iptables -P OUTPUT DROP
  iptables -A OUTPUT -o lo -j ACCEPT
  iptables -A OUTPUT -d 192.168.0.0/16 -j ACCEPT   # local subnet only
  ```
- Windows fallback: Windows Defender Firewall outbound rule blocking all programs except loopback/subnet (`netsh advfirewall`).

**Layer C — Live network monitor (visibility).** A small process using **`psutil.net_connections()`** (cross-platform — works on Windows *and* Linux, unlike `/proc/net/tcp` which is Linux-only) polls every 500 ms, classifies every active connection as localhost (green) / local-subnet (green) / external (red), and streams it over a WebSocket to the UI's Sovereignty panel. Every snapshot is appended to a log file → at demo end you show "0 external connections across the entire session." The audit log (§11) independently records `external_calls: 0` per task.

**Q&A-killer answer:** *"The badge isn't the proof. The proof is: the machine is physically disconnected, the kernel firewall drops all egress, and this independent monitor shows zero external connections — and here's the session log."* That is enforcement + proof + a paper trail. No other team will likely have all three.

---

## 6. Task Router — rule-based primary + LLM fallback [BUILT]

Resolves the "rule-based vs LLM" conflict between the review and Antigravity. **Antigravity was right for the default path**; the review's LLM-classifier is kept only as an ambiguity fallback.

**Primary path — deterministic, <50 ms, no model call, fully auditable:**
Reads signals: attachment MIME type; whether a PDF is image-heavy vs text-heavy (via PyMuPDF page analysis); explicit task keywords ("draft", "calculate", "code", "summarize", "extract"). Emits a `RoutingDecision` (which model to activate, which tools to pre-stage).

```text
image / image-heavy PDF        → vision model + OCR/analyze_image tools
code signals present           → coding model + execute_code tool
document/drafting signals       → reasoning model + search_kb + generate_docx
calculation signals             → reasoning model + calculate tool
plain question                 → reasoning model + search_kb (if KB populated)
```

**Fallback — only when the primary path is ambiguous (no attachment, mixed signals):** one cheap classification call to the reasoning model returning a single word (`CODE` / `DOCUMENT` / `CALC` / `SEARCH`). This is *not* circular (it only fires on genuine ambiguity) and gives you a clean answer to "what if the request is unclear?"

**Why not LLM-first:** an LLM call to route to another LLM is slow, wastes a model load, and is harder to audit. Rule-first is faster, deterministic, and — critically for a sovereignty product — every routing decision is logged and explainable.

**Demo of E2 (model auto-selection across ≥2 task types):** run three tasks back-to-back — a document task (badge: *Reasoning*), a scanned-image task (badge: *Vision*), a coding task (badge: *Coder*). Three task types, three models, visibly auto-selected. Unambiguous compliance.

---

## 7. Agent Orchestrator — real ReAct loop with self-correction [BUILT]

Resolves the review's #2 gap ("agentic is actually a linear pipeline"). This is a **genuine Plan→Act→Observe→Iterate loop**, not a fixed pipeline with a spinner. Custom-built (~300 lines), **no LangGraph/LangChain** — deliberately, because a sovereignty product must audit every call and frameworks hide HTTP calls you can't see. That rejection is itself a strong Q&A answer.

**The loop:**
1. **PLAN** — orchestrator sends task + routing decision + available tool schemas to the LLM; LLM returns an ordered plan as JSON (each step = a tool + inputs). Logged and shown in UI immediately.
2. **EXECUTE** — run the current step's tool; capture typed output (text / file path / structured / error).
3. **OBSERVE** — feed the tool output back into the growing LLM context; ask: proceed, revise the plan, or complete? → `Continue` / `Revise` / `Complete`.
4. **ITERATE** — Continue → next step; Revise → LLM produces an updated plan from current state; Complete → synthesis. Hard cap of 10 steps prevents infinite loops.
5. **SYNTHESIZE** — assemble intermediate outputs into the requested deliverable (hand structured content to the Deliverable Factory, §10).

**AgentState (serializable → this IS your audit trail):**
```python
AgentState:
    task_id: str
    original_task: str
    routing_decision: RoutingDecision
    plan: list[PlanStep]
    current_step_index: int
    tool_outputs: list[ToolOutput]
    llm_context: list[Message]      # grows every iteration — the model reads its own prior work
    audit_log: list[AuditEntry]
    status: Enum[PLANNING, EXECUTING, REVISING, COMPLETE, FAILED]
```

**Failure handling — classified, not blind-retry** (from sovereign_workbench; better than "retry 4 times"):
```text
syntax/exec error → regenerate code with the error in context
invalid data/schema → inspect, repair inputs
tool failure → retry tool once, then choose alternate
repeated failure → escalate to human (Autonomy Governor)
```

**The bulletproof "is this really agentic?" showpiece = the coding self-correction loop:** generate code → run in sandbox → it fails → the error is fed back → model diagnoses and repairs → re-run → passes. You can point to 5–8 distinct logged steps with timestamps, tool calls, and a real plan revision. That cannot be faked with one clever prompt. **Make this your agentic proof moment**, because the flagship doc flow (§13) is naturally more linear.

---

## 8. OCR & Vision pipeline [BUILT], with honest scoping

Resolves the review's #6 gap (handwriting/drawings overclaimed).

**Scanned PDFs:** PyMuPDF opens the file and checks each page for embedded text. Digital PDF → extract text directly (fast, accurate, no OCR). Scanned/image page → render to 300 DPI PNG (OCR accuracy collapses below 300 DPI) → **PaddleOCR** (chosen over Tesseract: better layout analysis, table handling, rotated text — which real inspection forms have). Output: text blocks with bounding boxes + **confidence scores**, reassembled in reading order; tables reconstructed as structured data.

**Engineering drawings / P&IDs:** pure OCR is insufficient (spatial relationships matter). PaddleOCR extracts the text annotations, then the full page image goes to **Qwen2.5-VL** with structured questions ("list equipment items and tag numbers"). Position it honestly: **assisted extraction and understanding, not certified engineering interpretation.**

**Handwriting:** PaddleOCR attempts it and **shows confidence scores**. Do **not** claim perfect handwriting recognition. The honest, auditable line — *"the system attempts it locally and surfaces confidence; low-confidence blocks are flagged for human review"* — is defensible and ties into the Autonomy Governor. Use reasonably legible samples in the demo.

**Multimodal demo (E5):** the scanned inspection report doubles as the multimodal task. To show real *vision understanding* (not just OCR of clean text), include one deliberate visual-reasoning moment — e.g., ask Qwen-VL to read a gauge/table value or identify a stamped/annotated region — rehearsed to work.

---

## 9. Secure code sandbox [BUILT] with a fallback

Resolves the review's #5 gap ("sandbox undefined").

**Primary: Docker container, `--network none`.** No network interface; read-only filesystem except a temp dir; CPU + memory limits; 30 s timeout; container destroyed after each run. Returns stdout/stderr/exit code.
```text
CPU: 2 cores · RAM: 2 GB · Network: NONE · Timeout: 30s · FS: temp-only, destroyed after run
```

**Fallback (if Docker Desktop/WSL2 eats your time): restricted subprocess** — separate process, dedicated temp working directory, hard timeout, resource caps. Less isolated than Docker, **but the host firewall's default-deny egress (§5) already guarantees executed code cannot reach the internet** — which is the sovereignty-relevant property. So even the fallback is defensible on the graded axis.

**Never** call raw `exec()`/`eval()` in-process a "sandbox." That is the answer that loses the room.

---

## 10. Deliverable Factory [BUILT] — structured JSON → real files

From sovereign_workbench (more reliable than asking an LLM to emit a binary). The LLM produces **structured content**, a rendering service turns it into the file:

```json
{ "title": "Inspection Approval Note", "addressee": "...", "summary": "...",
  "findings": [{"severity":"Critical","text":"...","source":"SOP-INS-004 p.17"}],
  "calculations": [{"name":"Remaining life","formula":"...","inputs":{},"steps":[],"result":"..."}],
  "recommendations": ["..."], "references": ["..."] }
```

| Deliverable | Library | Status |
|---|---|---|
| Word approval note (flagship) | `python-docx`, industrial template w/ headers, page numbers | **[BUILT] — top priority** |
| Excel analysis / calc table | `openpyxl` | **[BUILT] — second** |
| Verified code file | write to workspace | **[BUILT]** |
| PowerPoint briefing | `python-pptx` | **[ROADMAP]** — build only if flagship+coding are rock-solid; don't claim it otherwise |
| PDF | `reportlab` | **[ROADMAP]** |

**Engineering calculation with steps [BUILT]** (PS: "calculations with steps shown"; review gap #8): the **Calculation tool** does NOT let the LLM be the calculator. LLM extracts variables + formula → **Python computes deterministically** → output shows formula, inputs, units, intermediate steps, result, assumptions. Fold a real refinery calc into the flagship (e.g., corrosion rate → remaining life, or pressure-loss), which strengthens both the deliverable coverage AND domain fit.

---

## 11. Verification, Governance & Audit — thin but real (the differentiators)

Keep the *concepts* from KAVACH_Final; build only the light, demoable versions. These are what separate you from "offline chatbot" teams.

**Verification (Generate→Verify→Repair, light) [BUILT]:**
- Code: verified by actually running tests/execution in the sandbox (already in the loop).
- Calculations: verified by deterministic Python recomputation (§10).
- RAG claims: **citation-presence check** — key claims in a drafted note must map to a retrieved source; unsupported claims are flagged (a light "hallucination check," not a full firewall). Show this in the UI.

**Autonomy Governor + Human-in-the-loop [BUILT — thin]:** risk tag per task type → `low → auto` / `medium → human review` / `high → mandatory approval`. The "draft approval note" (high-stakes) task hits a visible **approval gate**: *"Risk: HIGH · Confidence: 88% · Evidence: 4 sources · [Review] [Approve] [Reject]."* Cheap to build, and for a PSU/defence audience it's a strong differentiator — *the AI never auto-issues a consequential document; a human signs off.*

**Audit log (SQLite) [BUILT]:** every task, routing decision, plan (JSON), tool call (inputs/outputs/duration/success), model used, deliverable, and `external_calls: 0` — queryable. *"Here is every single thing the system did, in order, with timestamps"* is a production-readiness signal most demo projects lack.

**[ROADMAP] — say "architecture supports, not built":** full RBAC, 5-level data classification, hybrid retrieval (BM25 + reranker), Qdrant, provenance hashing, multi-user. The registry/policy hooks exist; we scoped these out for the 48-hour prototype **on purpose**.

---

## 12. Local RAG — "Knowledge Vault" [BUILT]

- **Store:** ChromaDB (embedded, local, no server). (Qdrant/hybrid = roadmap.)
- **Ingestion:** document → extract (PyMuPDF/OCR) → **512-token chunks, 64-token overlap** (overlap keeps boundary-spanning sentences intact) → embed (nomic-embed, CPU) → store with metadata (document, page, section).
- **Retrieval:** embed query → top-8 by cosine → MMR re-rank to drop redundancy → top-4 into LLM context, labelled as retrieved.
- **Source-cited answer cards:** answer + `Source: SOP-Confined-Space-Entry-v2.pdf, §3.2` + expandable exact retrieved passage. This is your strongest "real grounded retrieval, not an LLM wrapper" evidence — make it visually unmistakable.
- **Knowledge Vault tab:** shows what's indexed ("3 SOPs · 1 manual · updated today"). Elevate RAG to a named, separately-demoable USP, not a buried chat feature.

---

## 13. Flagship demo flow — end to end (the golden scenario)

**User:** uploads a scanned inspection report and types *"Extract key findings from this inspection report, perform the required calculation, and draft a formal approval note as a Word document, per our SOP."*

1. **Router:** image-heavy PDF + "draft/Word" → vision model for extraction, reasoning model for synthesis; stage OCR + search_kb + calculate + generate_docx. *(badge: Vision → Reasoning)*
2. **Plan (agent):** ① OCR the report ② retrieve inspection SOP + approval-note format ③ extract & categorise findings (Critical/Major/Minor) ④ perform required calculation ⑤ draft note ⑥ verify citations ⑦ generate .docx. *(plan shown live)*
3. **OCR:** PyMuPDF renders → PaddleOCR extracts text + confidence + tables.
4. **RAG:** ChromaDB returns relevant SOP clauses + past approval-note template, with sources.
5. **Findings:** reasoning model → structured JSON findings, each tagged with severity and a source.
6. **Calculation:** calculate tool computes deterministically, shows steps.
7. **Draft:** reasoning model → structured approval-note content grounded in retrieved SOP.
8. **Verify:** citation-presence check; any unsupported claim flagged/revised (a real OBSERVE→Revise iteration if it fires).
9. **Governance:** high-risk → human approval gate shown.
10. **Deliverable:** generate_docx → downloadable, properly formatted Word file.
11. **Throughout:** Sovereignty panel green, external connections 0; audit log shows ~7 timestamped steps.

**Then the coding showpiece (agentic proof):** *"write a script to compute pipe pressure loss and run it"* → code → sandbox run → (induce/allow a failure) → self-correct → pass → verified output. This is where "agentic, not pipeline" is proven.

**Then sovereignty close:** show the physical disconnect, the firewall rules, the live monitor, and the zero-external session log side by side.

---

## 14. Build priority order (realistic for a 6-person AI-assisted team, ~2 days to college round)

Build in this order; each item must work on **unseen input** before moving on.

**P0 — must work for the college round (do these first, in order):**
1. Ollama + reasoning model serving via localhost; verify.
2. **Sovereignty proof end-to-end** (physical disconnect + firewall + psutil monitor + log) — validate the graded claim *before* writing agent code.
3. Flagship pipeline rough: OCR → RAG → findings → **.docx**, on unseen input.
4. Real ReAct loop wrapping the flagship (plan/act/observe/iterate visible + logged).
5. Coding task → Docker (or subprocess) sandbox → **self-correction loop** → verified output.
6. Task router (rule-based) + model badges showing auto-selection across the 3 task types.
7. Audit log (SQLite) writing every step.

**P1 — strong additions (finale-critical, after P0 is stable):**
8. Model registry YAML wired to the router (+ live add-a-model demo).
9. Calculation tool with steps shown; fold into flagship.
10. Verification (citation check) + Autonomy Governor approval gate.
11. Knowledge Vault tab with source-cited cards + indexed-state panel.

**P2 — polish (only if P0+P1 solid):**
12. Excel deliverable; reasoning-trace timeline UI; model-badge styling.
13. PPTX (roadmap unless time is abundant).

**Cut first under time pressure:** PPTX, hybrid retrieval, any RBAC/data-classification build, UI animations. A working terminal/API demo beats a broken pretty UI.

---

## 15. Demo-day risk register & mitigations

| Risk | Mitigation |
|---|---|
| Network monitor looks fake / goes dark | Physical disconnect (visceral) + firewall + real psutil monitor + session log. Never rely on the badge alone. |
| OCR garbage on judge-supplied scan | 300 DPI render, PaddleOCR layout mode, show confidence, flag low-confidence for human; rehearse on varied scans; keep a clean typed-PDF path. |
| Model latency → dead air | Default to 3–4B models; pre-warm before demo; stream tokens; mask waits with the live plan/step UI; keep outputs short. |
| Model-swap thrash between task types | Group demo task order to minimise swaps; Ollama keep-alive; accept one visible "loading model" moment framed as normal. |
| Docker fails on the day | Subprocess fallback (still egress-blocked by host firewall). Test both before demo. |
| Cold-start failures | Pre-pull all models, pre-index the KB, written startup checklist run before judges arrive. |
| Multi-machine LAN flakiness | Single-server design already removes most of this; static IP / hotspot; clients are just browsers. |
| Overclaiming caught in Q&A | The BUILT vs ROADMAP discipline (§0). Rehearse the honest lines. |

---

## 16. Q&A defence prep (rehearse these — this is where you've lost before)

- **"Prove no data leaves."** → Physical disconnect (visible), kernel/OS firewall default-deny egress applied before Ollama starts, independent psutil monitor showing 0 external, and the session log. Enforcement + proof + paper trail.
- **"How does the router pick a model?"** → Deterministic rule-based on MIME + task signals, <50 ms, fully logged; ambiguous cases fall back to a one-word LLM classification. Not circular, fully auditable.
- **"Is this actually agentic or just a pipeline?"** → Show the audit log: plan JSON, N timestamped tool calls, and a live self-correction (code fail → repair → pass). Context grows each iteration; the model reads its own prior work.
- **"How do you add a new model?"** → Show `models.yaml`; add a block; restart; it appears in the registry. No code change. (Do it live.)
- **"What's your sandbox?"** → Docker `--network none`, temp-only FS, CPU/mem/time limits, destroyed after run; and the host firewall blocks egress regardless.
- **"Does it hallucinate citations?"** → RAG returns source + page; citation-presence check flags unsupported claims; expand any citation to see the exact retrieved passage.
- **"What about handwriting / P&IDs?"** → Attempted locally with confidence scores; low-confidence flagged for human review; drawings are assisted understanding via the vision model, not certified interpretation. Honest and auditable.
- **"Will it run on our actual server?"** → Single-machine design; sequential loading on constrained VRAM; one-line registry swap to larger models on better hardware.
- **"What's real vs slideware?"** → Point to the BUILT vs ROADMAP table. We chose not to build RBAC/classification in 48 hours; the hooks are there.
- **"Why not just use a cloud model offline?"** → Confidentiality policy forbids cloud; open-weight + air-gapped + auditable + model-agnostic is the only compliant answer, and we prove the air-gap live.

---

## 17. Technology stack (final)

| Layer | Choice |
|---|---|
| Frontend | React + TypeScript + Tailwind (+ shadcn/ui if time); keep it functional/industrial |
| Backend | Python, FastAPI (async), WebSockets, Pydantic |
| Agent | Custom ReAct loop (no LangGraph/LangChain — auditability) |
| Model serving | Ollama (localhost:11434), adapter interface |
| Models | Qwen2.5-3B-Instruct / Qwen2.5-Coder-3B / Qwen2.5-VL-3B / nomic-embed-text (7B variants = config upgrade) |
| OCR/Vision | PyMuPDF + PaddleOCR + Qwen2.5-VL; OpenCV/Pillow for preprocessing |
| RAG | ChromaDB + nomic-embed + MMR (hybrid/reranker = roadmap) |
| Sandbox | Docker `--network none` (subprocess fallback) |
| Deliverables | python-docx, openpyxl, python-pptx (roadmap), reportlab (roadmap) |
| Network proof | OS firewall default-deny (iptables/Windows Firewall) + psutil monitor |
| Audit / state | SQLite |
| DB | SQLite for the prototype (PostgreSQL = roadmap) |

---

## 18. Repository structure

```text
kavach/
├── frontend/                    # React + TS: Task, Agent Progress, Output, Sovereignty, Knowledge Vault panels
├── backend/
│   ├── api/                     # FastAPI routes: /tasks /knowledge /models /network /audit
│   ├── orchestrator/            # planner.py, react_loop.py, state.py
│   ├── router/                  # rule_router.py (+ llm_fallback.py)
│   ├── models/                  # registry.py (reads models.yaml), adapter.py
│   ├── tools/                   # read_file, write_file, ocr, analyze_image, search_kb,
│   │                            #   execute_code, calculate, generate_docx/xlsx/pptx
│   ├── knowledge/               # ingestion.py, retrieval.py (Chroma + MMR), embeddings.py
│   ├── verification/            # citations.py, calculations.py
│   ├── governance/              # autonomy.py (risk tags), approval.py
│   ├── security/                # firewall_setup.(sh|ps1), network_monitor.py (psutil)
│   └── audit/                   # logger.py (SQLite)
├── sandbox/                     # Docker context for code execution
├── models.yaml                  # model registry — the extensibility surface
├── knowledge_base/              # synthetic SOPs / manuals for the demo
├── test_data/                   # sample scanned reports, drawings (public/synthetic only)
├── generated/                   # output deliverables
└── README.md                    # + startup checklist
```

---

## 19. What we deliberately did NOT build, and why (say this out loud)

Full RBAC, multi-level data classification, hybrid BM25+reranker retrieval, Qdrant, PostgreSQL, provenance hashing, multi-agent supervisor, PPTX/PDF generation. **The architecture has the hooks for all of them** (policy gate on every tool call, the registry pattern, the modular monolith). We scoped them out of the 48-hour prototype on purpose to make the graded core — sovereignty proof, agentic execution, model selection, multimodal, real deliverables — rock-solid instead of shipping ten half-features. Presenting this as a *decision* is what a national panel expects from a team that understands its own system.

---

## 20. One-line summary for the team

Build the **golden flagship** (scan → OCR → RAG → findings → calc-with-steps → verified Word note) and the **coding self-correction loop**, wrap both in a **real ReAct agent** with a **rule-based router + 3-model registry**, and prove sovereignty with **physical disconnect + OS firewall + live psutil monitor + audit log** — then stop, polish, and rehearse 20 times. Everything else is roadmap you can defend without building.
```

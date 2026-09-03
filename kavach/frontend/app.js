/* KAVACH — Phase 10 frontend. Wired to the real FastAPI backend (Phases 1-9). */

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const MODEL_LABELS = {
  reasoning: "Reasoning model",
  code: "Code model",
  vision: "Vision model",
  embedding: "Embedding model",
};

const TOOL_LABELS = {
  llm: "Reasoning",
  search: "Knowledge Vault search",
  calc: "Calculation",
  code: "Code sandbox",
  ocr: "Document OCR",
  vision: "Image analysis",
  document: "Document writer",
};

/* ------------------------------------------------------- sidebar toggle */
const appRoot = document.getElementById("app-root");
let sidebarCollapsed = localStorage.getItem("kavach_sidebar_collapsed") === "1";

function applySidebarState() {
  appRoot.classList.toggle("sidebar-collapsed", sidebarCollapsed);
}
$("sidebar-toggle").addEventListener("click", () => {
  sidebarCollapsed = !sidebarCollapsed;
  localStorage.setItem("kavach_sidebar_collapsed", sidebarCollapsed ? "1" : "0");
  applySidebarState();
});
applySidebarState();

/* --------------------------------------------------- rotating greeting */
const GREETINGS = [
  "Where should we begin?",
  "Ready when you are.",
  "What's the task at hand?",
  "SOPs, a calculation, or a report?",
  "How can I help, Operator?",
];
const greetingText = $("greeting-text");
if (greetingText) {
  greetingText.textContent = GREETINGS[Math.floor(Math.random() * GREETINGS.length)];
}

/* ------------------------------------------------------------ navigation */

document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    const target = btn.dataset.screen;
    document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("is-active", b === btn));
    ["task", "vault", "audit"].forEach((name) => {
      $(`screen-${name}`).hidden = name !== target;
    });
    if (target === "vault") loadDocuments();
    if (target === "audit") loadAuditEvents();
  });
});

/* -------------------------------------------------- sovereignty monitor */

function renderSovereignty(externalCount) {
  const dot = $("sov-dot");
  const safe = externalCount === 0;
  dot.classList.toggle("is-safe", safe);
  dot.classList.toggle("is-alert", !safe);
  $("sov-text").textContent = `Air-gapped · ${externalCount} external connection${externalCount === 1 ? "" : "s"}`;
}

function connectMonitor() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  let socket;
  try {
    socket = new WebSocket(`${proto}//${location.host}/shield/monitor`);
  } catch {
    setTimeout(connectMonitor, 3000);
    return;
  }
  socket.onmessage = (event) => {
    try {
      renderSovereignty(JSON.parse(event.data).external_count);
    } catch { /* ignore malformed frame */ }
  };
  socket.onclose = () => {
    $("sov-dot").className = "dot";
    $("sov-text").textContent = "Monitor disconnected";
    setTimeout(connectMonitor, 3000);
  };
}

/* ------------------------------------------------------- lockdown toggle */

let lockdownOn = false;

function renderLockdown() {
  $("lock-toggle").classList.toggle("is-on", lockdownOn);
  $("lock-label").textContent = lockdownOn ? "Lockdown on" : "Lockdown off";
}

function showNote(message) {
  const note = $("inline-note");
  note.textContent = message;
  note.hidden = false;
  clearTimeout(showNote.timer);
  showNote.timer = setTimeout(() => { note.hidden = true; }, 9000);
}

async function refreshShieldStatus() {
  try {
    const data = await (await fetch("/shield/status")).json();
    lockdownOn = Boolean(data.firewall?.active);
    renderLockdown();
  } catch { /* monitor WS already surfaces connectivity problems */ }
}

$("lock-toggle").addEventListener("click", async () => {
  const endpoint = lockdownOn ? "/shield/unlock" : "/shield/lockdown";
  $("lock-label").textContent = lockdownOn ? "Unlocking…" : "Locking down…";
  try {
    const response = await fetch(endpoint, { method: "POST" });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      const detail = String(body.detail || "");
      showNote(detail.includes("elevated") || response.status === 403
        ? "Requires starting the server as Administrator."
        : `Could not change lockdown: ${detail || response.statusText}`);
    } else {
      lockdownOn = !lockdownOn;
    }
  } catch (err) {
    showNote(`Could not reach the shield endpoint: ${err.message}`);
  }
  renderLockdown();
});

/* -------------------------------------------------------- task composer */

const input = $("task-input");
let attachedPath = null;

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 220)}px`;
  $("send-btn").disabled = input.value.trim() === "";
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    if (!$("send-btn").disabled) runTask();
  }
});

$("attach-btn").addEventListener("click", () => $("file-input").click());

$("file-input").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  $("attachment-name").textContent = `Uploading ${file.name}…`;
  $("attachment").hidden = false;
  try {
    // ingest=false: the composer only needs the file on disk for the ocr/vision tools.
    const result = await uploadFile(file, false);
    attachedPath = result.file_path;
    $("attachment-name").textContent = result.filename;
  } catch (err) {
    $("attachment-name").textContent = `Upload failed: ${err.message}`;
    attachedPath = null;
  }
  event.target.value = "";
});

$("attachment-clear").addEventListener("click", () => {
  attachedPath = null;
  $("attachment").hidden = true;
});

$("send-btn").addEventListener("click", runTask);

/* ----------------------------------------------------- suggestion chips */
document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    input.value = chip.dataset.prefill;
    input.dispatchEvent(new Event("input"));
    input.focus();
    const len = input.value.length;
    input.setSelectionRange(len, len);
  });
});

/* -------------------------------------------------------------- the run */

function renderSteps(steps, activeIndex, finished) {
  if (!steps?.length) { $("steps").innerHTML = ""; return; }
  $("steps").innerHTML = steps.map((step, i) => {
    let state = "is-pending";
    if (step.status === "done") state = "is-done";
    else if (step.status === "failed") state = "is-failed";
    else if (!finished && i === activeIndex) state = "is-running";
    return `
      <div class="step ${state}">
        <span class="step-marker"><span class="ring"></span></span>
        <div class="step-body">
          <div class="step-tool">${esc(TOOL_LABELS[step.tool] || step.tool)}</div>
          <div class="step-input">${esc(step.input)}</div>
        </div>
      </div>`;
  }).join("");
}

/** Derives live progress from the real audit trail for this task_id. */
function applyAuditEvents(events) {
  const planIndex = events.map((e) => e.event_type).lastIndexOf("plan");
  if (planIndex === -1) return;

  const steps = (events[planIndex].metadata?.steps || []).map((s) => ({ ...s, status: "pending" }));
  const after = events.slice(planIndex + 1);

  for (const event of after) {
    if (event.event_type !== "step") continue;
    const step = steps.find((s) => s.step_num === event.metadata?.step_num);
    if (step) step.status = event.metadata?.error ? "failed" : "done";
  }

  const finished = after.some((e) => e.event_type === "complete" || e.event_type === "error");
  const activeIndex = steps.findIndex((s) => s.status === "pending");
  renderSteps(steps, activeIndex === -1 ? steps.length : activeIndex, finished);

  const route = events.find((e) => e.event_type === "route");
  if (route) {
    const role = route.metadata?.model_role;
    $("run-meta").innerHTML =
      `<span>${esc(MODEL_LABELS[role] || role || "Model")}</span>` +
      `<span class="sep">·</span><span>${esc(route.metadata?.model_tag || "")}</span>`;
  }

  const revisions = after.filter((e) => e.event_type === "observe" && e.metadata?.decision === "revise").length;
  if (revisions > 0) {
    currentStatusText = `Self-correcting after an error (revision ${revisions})…`;
  } else if (activeIndex !== -1 && activeIndex < steps.length) {
    const cur = steps[activeIndex];
    const toolLabel = TOOL_LABELS[cur.tool] || cur.tool;
    currentStatusText = `Step ${activeIndex + 1}/${steps.length}: Running ${toolLabel}…`;
  } else if (finished) {
    currentStatusText = "Finalizing output…";
  } else if (steps.some((s) => s.status !== "pending")) {
    currentStatusText = "Working through steps…";
  } else {
    currentStatusText = "Planning steps…";
  }
  updateThinkingDisplay();
}

function renderApprovalCard(data) {
  const taskId = data.task_id;
  const approval = data.approval || {};
  const risk = (approval.risk || "medium").toLowerCase();
  const conf = approval.confidence !== undefined ? Math.round(approval.confidence * 100) : 50;
  const reasoning = approval.reasoning || "Document generation paused for human review.";
  const draft = data.draft_content || {};
  const title = draft.title || "Document Draft";
  const sections = draft.sections || [];
  const draftSources = draft.sources || data.sources || [];
  const sourceNames = [...new Set(draftSources.map((s) => (typeof s === "string" ? s : s?.filename)).filter(Boolean))];

  return `
    <div class="card approval-card risk-is-${risk}" id="approval-card-${taskId}">
      <p class="section-label">Human Approval Gate</p>
      <div class="approval-meta">
        <span class="risk-text-${risk}">Risk: ${esc(risk.toUpperCase())}</span>
        <span class="approval-conf">&middot; Confidence: ${conf}%</span>
      </div>
      <div class="approval-reasoning">${esc(reasoning)}</div>

      <div class="approval-preview-box">
        <div class="approval-draft-title">${esc(title)}</div>
        ${sourceNames.length ? `
          <div class="approval-sources-line">
            <span class="doc-sources-label">Sources:</span>
            <span class="doc-sources-names">${sourceNames.map(esc).join(", ")}</span>
          </div>
        ` : ""}
        ${sections.map((s, idx) => `
          <div class="approval-sec">
            <div class="approval-sec-heading">${esc(s.heading || `Section ${idx + 1}`)}</div>
            <p class="approval-sec-body">${esc(s.body || "")}</p>
          </div>
        `).join("")}
      </div>

      <div class="approval-actions" id="approval-actions-${taskId}">
        <button class="btn btn-primary" onclick="handleApprovalAction('${taskId}', 'approve')">
          <svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M20 6L9 17l-5-5"/></svg>
          <span>Approve</span>
        </button>
        <button class="btn btn-secondary" onclick="toggleApprovalEdit('${taskId}')">
          <svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
          <span>Edit</span>
        </button>
        <button class="btn btn-danger-quiet" onclick="handleApprovalAction('${taskId}', 'reject')">
          <svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12"/></svg>
          <span>Reject</span>
        </button>
      </div>

      <div class="approval-edit-wrap" id="approval-edit-${taskId}" hidden>
        <label class="approval-edit-label">Document Title</label>
        <input class="approval-input" id="edit-title-${taskId}" value="${esc(title)}">
        <label class="approval-edit-label">Sections Content (JSON)</label>
        <textarea class="approval-textarea" id="edit-sections-${taskId}" rows="6">${esc(JSON.stringify(sections, null, 2))}</textarea>
        <div class="approval-edit-actions">
          <button class="btn btn-primary" onclick="submitApprovalEdit('${taskId}')">
            <span>Submit with Edits</span>
          </button>
          <button class="btn btn-secondary" onclick="toggleApprovalEdit('${taskId}')">
            <span>Cancel</span>
          </button>
        </div>
      </div>

      <div id="approval-outcome-${taskId}"></div>
    </div>
  `;
}

window.toggleApprovalEdit = function(taskId) {
  const wrap = document.getElementById(`approval-edit-${taskId}`);
  if (wrap) wrap.hidden = !wrap.hidden;
};

window.handleApprovalAction = async function(taskId, decision) {
  const actions = document.getElementById(`approval-actions-${taskId}`);
  const outcome = document.getElementById(`approval-outcome-${taskId}`);
  if (actions) actions.style.display = "none";
  if (outcome) outcome.innerHTML = `<div class="approval-notice">Processing ${decision}…</div>`;

  try {
    const res = await fetch(`/approval/${encodeURIComponent(taskId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision: decision }),
    });
    const data = await res.json();
    if (decision === "reject") {
      outcome.innerHTML = `<p class="error-note" style="margin-top: 12px;">Document rejected. Generation cancelled with zero files created.</p>`;
    } else {
      outcome.innerHTML = `
        <div class="approval-notice" style="margin: 12px 0;">Document approved successfully!</div>
        <a class="download-btn" href="/download/${encodeURIComponent(data.filename)}" download>
          <svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M12 4v12M7 13l5 5 5-5"/><path d="M4 20h16"/></svg>
          <span>Download ${esc(data.title || data.filename)}</span>
        </a>
      `;
    }
  } catch (err) {
    if (actions) actions.style.display = "flex";
    if (outcome) outcome.innerHTML = `<p class="error-note">Action failed: ${esc(err.message)}</p>`;
  }
};

window.submitApprovalEdit = async function(taskId) {
  const title = document.getElementById(`edit-title-${taskId}`).value.trim();
  const sectionsRaw = document.getElementById(`edit-sections-${taskId}`).value.trim();
  const actions = document.getElementById(`approval-actions-${taskId}`);
  const editWrap = document.getElementById(`approval-edit-${taskId}`);
  const outcome = document.getElementById(`approval-outcome-${taskId}`);

  let parsed = [];
  try {
    parsed = JSON.parse(sectionsRaw);
    if (!Array.isArray(parsed)) parsed = [{ heading: "Summary", body: sectionsRaw }];
  } catch {
    parsed = [{ heading: "Summary", body: sectionsRaw }];
  }

  if (actions) actions.style.display = "none";
  if (editWrap) editWrap.hidden = true;
  if (outcome) outcome.innerHTML = `<div class="approval-notice">Rendering edited document…</div>`;

  try {
    const res = await fetch(`/approval/${encodeURIComponent(taskId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision: "edit", edited_content: { title, sections: parsed } }),
    });
    const data = await res.json();
    outcome.innerHTML = `
      <div class="approval-notice" style="margin: 12px 0;">Document updated and rendered with your edits!</div>
      <a class="download-btn" href="/download/${encodeURIComponent(data.filename)}" download>
        <svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M12 4v12M7 13l5 5 5-5"/><path d="M4 20h16"/></svg>
        <span>Download ${esc(data.title || data.filename)}</span>
      </a>
    `;
  } catch (err) {
    if (editWrap) editWrap.hidden = false;
    if (outcome) outcome.innerHTML = `<p class="error-note">Edit submission failed: ${esc(err.message)}</p>`;
  }
};

function renderCodeCard(run) {
  const lang = (run.language || "python").toLowerCase();
  const langLabels = { python: "Python", javascript: "JavaScript", c: "C" };
  const langName = langLabels[lang] || lang.toUpperCase();
  const isErr = (run.exit_code !== 0 && run.exit_code !== undefined) || run.error;
  const duration = run.duration_seconds !== undefined ? `${run.duration_seconds}s` : "";
  const exitText = run.exit_code !== undefined ? `exit ${run.exit_code}` : "";
  const metaText = [exitText, duration].filter(Boolean).join(" · ");
  const code = run.code || "";
  const stdout = run.stdout || "";
  const stderr = run.stderr || "";

  return `
    <div class="card code-card">
      <div class="code-header">
        <div class="code-badges">
          <span class="section-label" style="margin:0;">Generated Code</span>
          <span class="code-lang-badge">${esc(langName)}</span>
        </div>
        ${metaText ? `<span class="code-meta-badge ${isErr ? "is-error" : ""}">${esc(metaText)}</span>` : ""}
      </div>

      <div class="code-wrap">
        <button class="copy-code-btn" onclick="copyCodeText(this)" data-code="${esc(code)}" title="Copy code">
          <svg class="icon" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
          <span>Copy</span>
        </button>
        <pre class="code-content"><code>${esc(code)}</code></pre>
      </div>

      ${(stdout || stderr) ? `
        <div class="code-output-box">
          <div class="code-output-label">Terminal Output</div>
          ${stdout ? `<pre class="code-stdout">${esc(stdout)}</pre>` : ""}
          ${stderr ? `<pre class="code-stderr">${esc(stderr)}</pre>` : ""}
        </div>
      ` : ""}
    </div>
  `;
}

window.copyCodeText = function(btn) {
  const code = btn.getAttribute("data-code") || "";
  navigator.clipboard.writeText(code).then(() => {
    const span = btn.querySelector("span");
    if (span) {
      const orig = span.textContent;
      span.textContent = "Copied!";
      setTimeout(() => { span.textContent = orig; }, 2000);
    }
  }).catch(() => {});
};

function renderResult(data) {
  const parts = [];

  if (data.status === "awaiting_approval") {
    parts.push(renderApprovalCard(data));
  } else if (data.result) {
    parts.push(`<div class="card"><div class="answer">${esc(data.result)}</div></div>`);
  }

  const rawSources = data.sources || [];
  const sourceNames = [...new Set(rawSources.map((s) => (typeof s === "string" ? s : s?.filename)).filter(Boolean))];
  if (sourceNames.length) {
    parts.push(`<div class="card sources-card">
      <p class="section-label">Referenced Sources</p>
      <div class="sources-list">${sourceNames.map((name) => `
        <div class="source-item">
          <svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5z"/><path d="M14 3v5h5"/></svg>
          <span class="source-name">${esc(name)}</span>
        </div>`).join("")}</div></div>`);
  }

  for (const run of data.code_runs || []) {
    if (!run.code) continue;
    parts.push(renderCodeCard(run));
  }

  for (const file of data.generated_files || []) {
    if (!file.filename) continue;
    const fileSources = [...new Set((file.sources || rawSources).map((s) => (typeof s === "string" ? s : s?.filename)).filter(Boolean))];
    parts.push(`<div class="card">
      <p class="section-label">Generated document</p>
      <a class="download-btn" href="/download/${encodeURIComponent(file.filename)}" download>
        <svg class="icon icon-sm" viewBox="0 0 24 24"><path d="M12 4v12M7 13l5 5 5-5"/><path d="M4 20h16"/></svg>
        <span>${esc(file.title || file.filename)}</span>
      </a>
      ${fileSources.length ? `
        <div class="doc-sources-meta">
          <span class="doc-sources-label">Sources cited in file:</span>
          <span class="doc-sources-names">${fileSources.map(esc).join(", ")}</span>
        </div>
      ` : ""}
    </div>`);
  }

  if (data.status === "failed") {
    parts.push(`<p class="error-note">The agent finished with errors — see the steps above.</p>`);
  }

  $("result").innerHTML = parts.join("");
}

let currentStatusText = "Planning steps…";
let runStartTime = Date.now();

function updateThinkingDisplay() {
  const elapsed = Math.floor((Date.now() - runStartTime) / 1000);
  const el = $("thinking-text");
  if (el) {
    el.textContent = `${currentStatusText} (${elapsed}s)`;
  }
}

async function runTask() {
  const task = input.value.trim();
  if (!task) return;

  const taskId = crypto.randomUUID();
  const fullTask = attachedPath ? `${task}\n\nAttached file: ${attachedPath}` : task;

  runStartTime = Date.now();
  currentStatusText = "Planning steps…";

  input.value = "";
  input.style.height = "auto";
  $("send-btn").disabled = true;
  $("greeting-wrap").classList.add("is-compact");
  $("screen-task").classList.add("has-run");
  $("wordmark").classList.add("is-thinking");
  $("run").hidden = false;
  $("thinking").hidden = false;
  updateThinkingDisplay();
  $("steps").innerHTML = "";
  $("result").innerHTML = "";
  $("run-meta").textContent = "";

  const ticker = setInterval(updateThinkingDisplay, 1000);

  const poll = setInterval(async () => {
    try {
      const data = await (await fetch(`/audit?task_id=${encodeURIComponent(taskId)}`)).json();
      applyAuditEvents(data.events || []);
    } catch { /* transient — the run request is the source of truth */ }
  }, 1000);

  try {
    const response = await fetch("/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task: fullTask, task_id: taskId }),
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const data = await response.json();

    clearInterval(poll);
    clearInterval(ticker);
    const audit = await (await fetch(`/audit?task_id=${encodeURIComponent(taskId)}`)).json();
    applyAuditEvents(audit.events || []);
    renderResult(data);
  } catch (err) {
    clearInterval(poll);
    clearInterval(ticker);
    $("result").innerHTML = `<p class="error-note">The task could not complete: ${esc(err.message)}</p>`;
  } finally {
    // Guaranteed cleanup regardless of success/failure — the mark returns to
    // its static resting state the instant the task finishes, one way or another.
    clearInterval(ticker);
    clearInterval(poll);
    $("thinking").hidden = true;
    $("wordmark").classList.remove("is-thinking");
  }

  attachedPath = null;
  $("attachment").hidden = true;
}

/* ------------------------------------------------------- knowledge vault */

async function uploadFile(file, ingest) {
  const form = new FormData();
  form.append("file", file);
  form.append("ingest", String(ingest));
  const response = await fetch("/knowledge/upload", { method: "POST", body: form });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || response.statusText);
  return body;
}

async function loadDocuments() {
  const list = $("doc-list");
  try {
    const data = await (await fetch("/knowledge/list")).json();
    if (!data.documents?.length) {
      list.innerHTML = `<p class="empty">No documents indexed yet.</p>`;
      return;
    }
    list.innerHTML = data.documents.map((doc) => `
      <div class="doc-row">
        <svg class="icon" viewBox="0 0 24 24"><path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5z"/><path d="M14 3v5h5"/></svg>
        <span class="doc-name">${esc(doc.filename)}</span>
        <span class="doc-chunks">${doc.chunk_count} chunk${doc.chunk_count === 1 ? "" : "s"}</span>
      </div>`).join("");
  } catch (err) {
    list.innerHTML = `<p class="empty">Could not load documents: ${esc(err.message)}</p>`;
  }
}

async function ingestFile(file) {
  const text = $("dropzone-text");
  text.textContent = `Indexing ${file.name}… this can take a moment.`;
  try {
    const result = await uploadFile(file, true);
    text.textContent = `Indexed ${result.filename} — ${result.chunk_count} chunks.`;
    loadDocuments();
  } catch (err) {
    text.textContent = `Could not index that file: ${err.message}`;
  }
  setTimeout(() => { text.textContent = "Drop a document here, or click to choose"; }, 6000);
}

const dropzone = $("dropzone");
dropzone.addEventListener("click", () => $("vault-file-input").click());
$("vault-file-input").addEventListener("change", (event) => {
  if (event.target.files[0]) ingestFile(event.target.files[0]);
  event.target.value = "";
});
["dragenter", "dragover"].forEach((type) =>
  dropzone.addEventListener(type, (e) => { e.preventDefault(); dropzone.classList.add("is-over"); }));
["dragleave", "drop"].forEach((type) =>
  dropzone.addEventListener(type, (e) => { e.preventDefault(); dropzone.classList.remove("is-over"); }));
dropzone.addEventListener("drop", (event) => {
  if (event.dataTransfer.files[0]) ingestFile(event.dataTransfer.files[0]);
});

/* ------------------------------------------------------------ audit log */

let auditEvents = [];

function renderAuditEvents() {
  const typeFilter = $("audit-type-filter").value;
  const rows = auditEvents
    .filter((e) => !typeFilter || e.event_type === typeFilter)
    .slice(-250)
    .reverse();

  $("events").innerHTML = rows.length
    ? rows.map((event) => `
        <div class="event">
          <span class="event-time">${esc((event.timestamp || "").slice(11, 19))}</span>
          <span class="event-type">${esc(event.event_type)}</span>
          <span class="event-summary">${esc(event.summary)}</span>
          <span class="event-calls">${event.external_calls} external</span>
        </div>`).join("")
    : `<p class="empty">No events match that filter.</p>`;
}

async function loadAuditEvents() {
  const taskId = $("audit-task-filter").value.trim();
  const url = taskId ? `/audit?task_id=${encodeURIComponent(taskId)}` : "/audit";
  try {
    const data = await (await fetch(url)).json();
    auditEvents = data.events || [];

    const select = $("audit-type-filter");
    const current = select.value;
    const types = [...new Set(auditEvents.map((e) => e.event_type))].sort();
    select.innerHTML = `<option value="">All event types</option>` +
      types.map((t) => `<option value="${esc(t)}">${esc(t)}</option>`).join("");
    select.value = current;

    renderAuditEvents();
  } catch (err) {
    $("events").innerHTML = `<p class="empty">Could not load the audit log: ${esc(err.message)}</p>`;
  }
}

$("audit-task-filter").addEventListener("input", () => {
  clearTimeout(loadAuditEvents.timer);
  loadAuditEvents.timer = setTimeout(loadAuditEvents, 350);
});
$("audit-type-filter").addEventListener("change", renderAuditEvents);

/* ---------------------------------------------------------------- boot */

connectMonitor();
refreshShieldStatus();

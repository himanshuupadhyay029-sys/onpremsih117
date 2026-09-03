import React, { useState, useRef, useEffect, useMemo } from 'react';

const MODEL_LABELS = {
  reasoning: 'Reasoning model',
  code: 'Code model',
  vision: 'Vision model',
  embedding: 'Embedding model',
};

const TOOL_LABELS = {
  llm: 'Reasoning',
  search: 'Knowledge Vault search',
  calc: 'Calculation',
  code: 'Code sandbox',
  ocr: 'Document OCR',
  vision: 'Image analysis',
  document: 'Document writer',
};

export default function NewTaskScreen({ setIsThinking }) {
  const [taskInput, setTaskInput] = useState('');
  const [attachedFile, setAttachedFile] = useState(null);
  const [uploadingAttachment, setUploadingAttachment] = useState(false);

  // Execution state
  const [hasRun, setHasRun] = useState(false);
  const [running, setRunning] = useState(false);
  const [modelMeta, setModelMeta] = useState('');
  const [statusText, setStatusText] = useState('Planning steps…');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [steps, setSteps] = useState([]);
  const [resultData, setResultData] = useState(null);
  const [errorMsg, setErrorMsg] = useState('');

  // Approval state
  const [approvalOutcome, setApprovalOutcome] = useState({});
  const [editingApproval, setEditingApproval] = useState({});
  const [editTitle, setEditTitle] = useState('');
  const [editSections, setEditSections] = useState('');

  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const pollTimerRef = useRef(null);
  const tickerRef = useRef(null);
  const startTimeRef = useRef(0);

  // Adjust textarea height
  const handleInputChange = (e) => {
    setTaskInput(e.target.value);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(
        textareaRef.current.scrollHeight,
        220
      )}px`;
    }
  };

  // Handle file attachment
  const handleFileChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setUploadingAttachment(true);
    setAttachedFile({ name: `Uploading ${file.name}…`, path: null });

    const formData = new FormData();
    formData.append('file', file);
    formData.append('ingest', 'false');

    try {
      const res = await fetch('/knowledge/upload', {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || res.statusText);
      setAttachedFile({ name: data.filename, path: data.file_path });
    } catch (err) {
      setAttachedFile({ name: `Upload failed: ${err.message}`, path: null });
    } finally {
      setUploadingAttachment(false);
      e.target.value = '';
    }
  };

  // Live audit event parser for progress
  const applyAuditEvents = (events) => {
    const planIndex = events.map((e) => e.event_type).lastIndexOf('plan');
    if (planIndex === -1) return;

    const rawSteps = (events[planIndex].metadata?.steps || []).map((s) => ({
      ...s,
      status: 'pending',
    }));
    const after = events.slice(planIndex + 1);

    for (const event of after) {
      if (event.event_type !== 'step') continue;
      const step = rawSteps.find((s) => s.step_num === event.metadata?.step_num);
      if (step) step.status = event.metadata?.error ? 'failed' : 'done';
    }

    const finished = after.some(
      (e) => e.event_type === 'complete' || e.event_type === 'error'
    );
    const activeIndex = rawSteps.findIndex((s) => s.status === 'pending');

    setSteps(rawSteps);

    const route = events.find((e) => e.event_type === 'route');
    if (route) {
      const role = route.metadata?.model_role;
      setModelMeta(
        `${MODEL_LABELS[role] || role || 'Model'} · ${
          route.metadata?.model_tag || ''
        }`
      );
    }

    const revisions = after.filter(
      (e) => e.event_type === 'observe' && e.metadata?.decision === 'revise'
    ).length;

    if (revisions > 0) {
      setStatusText(`Self-correcting after an error (revision ${revisions})…`);
    } else if (activeIndex !== -1 && activeIndex < rawSteps.length) {
      const cur = rawSteps[activeIndex];
      const toolLabel = TOOL_LABELS[cur.tool] || cur.tool;
      setStatusText(
        `Step ${activeIndex + 1}/${rawSteps.length}: Running ${toolLabel}…`
      );
    } else if (finished) {
      setStatusText('Finalizing output…');
    } else if (rawSteps.some((s) => s.status !== 'pending')) {
      setStatusText('Working through steps…');
    } else {
      setStatusText('Planning steps…');
    }
  };

  // Run task execution
  const runTask = async () => {
    const task = taskInput.trim();
    if (!task || running) return;

    const taskId = crypto.randomUUID();
    const fullTask = attachedFile?.path
      ? `${task}\n\nAttached file: ${attachedFile.path}`
      : task;

    setHasRun(true);
    setRunning(true);
    setIsThinking(true);
    setResultData(null);
    setErrorMsg('');
    setSteps([]);
    setModelMeta('');
    setStatusText('Planning steps…');
    setElapsedSeconds(0);
    startTimeRef.current = Date.now();

    setTaskInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    // Ticker for elapsed seconds
    tickerRef.current = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startTimeRef.current) / 1000));
    }, 1000);

    // Audit poll for live progress
    pollTimerRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/audit?task_id=${encodeURIComponent(taskId)}`);
        const data = await res.json();
        applyAuditEvents(data.events || []);
      } catch {
        // ignore poll errors
      }
    }, 1000);

    try {
      const response = await fetch('/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task: fullTask, task_id: taskId }),
      });
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      const data = await response.json();

      clearInterval(pollTimerRef.current);
      clearInterval(tickerRef.current);

      const auditRes = await fetch(
        `/audit?task_id=${encodeURIComponent(taskId)}`
      );
      const auditData = await auditRes.json();
      applyAuditEvents(auditData.events || []);

      setResultData(data);
      if (data.draft_content) {
        setEditTitle(data.draft_content.title || '');
        setEditSections(
          JSON.stringify(data.draft_content.sections || [], null, 2)
        );
      }
    } catch (err) {
      clearInterval(pollTimerRef.current);
      clearInterval(tickerRef.current);
      setErrorMsg(`The task could not complete: ${err.message}`);
    } finally {
      clearInterval(pollTimerRef.current);
      clearInterval(tickerRef.current);
      setRunning(false);
      setIsThinking(false);
      setAttachedFile(null);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (taskInput.trim() && !running) runTask();
    }
  };

  // Handle human approval actions
  const handleApprovalAction = async (taskId, decision) => {
    setApprovalOutcome((prev) => ({
      ...prev,
      [taskId]: { loading: true, message: `Processing ${decision}…` },
    }));

    try {
      const res = await fetch(`/approval/${encodeURIComponent(taskId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision }),
      });
      const data = await res.json();

      if (decision === 'reject') {
        setApprovalOutcome((prev) => ({
          ...prev,
          [taskId]: {
            loading: false,
            rejected: true,
            message: 'Document rejected. Generation cancelled with zero files created.',
          },
        }));
      } else {
        setApprovalOutcome((prev) => ({
          ...prev,
          [taskId]: {
            loading: false,
            approved: true,
            filename: data.filename,
            title: data.title || data.filename,
          },
        }));
      }
    } catch (err) {
      setApprovalOutcome((prev) => ({
        ...prev,
        [taskId]: { loading: false, error: err.message },
      }));
    }
  };

  const handleApprovalEditSubmit = async (taskId) => {
    let parsedSections = [];
    try {
      parsedSections = JSON.parse(editSections);
      if (!Array.isArray(parsedSections)) {
        parsedSections = [{ heading: 'Summary', body: editSections }];
      }
    } catch {
      parsedSections = [{ heading: 'Summary', body: editSections }];
    }

    setEditingApproval((prev) => ({ ...prev, [taskId]: false }));
    setApprovalOutcome((prev) => ({
      ...prev,
      [taskId]: { loading: true, message: 'Rendering edited document…' },
    }));

    try {
      const res = await fetch(`/approval/${encodeURIComponent(taskId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          decision: 'edit',
          edited_content: { title: editTitle, sections: parsedSections },
        }),
      });
      const data = await res.json();
      setApprovalOutcome((prev) => ({
        ...prev,
        [taskId]: {
          loading: false,
          approved: true,
          filename: data.filename,
          title: data.title || data.filename,
        },
      }));
    } catch (err) {
      setApprovalOutcome((prev) => ({
        ...prev,
        [taskId]: { loading: false, error: err.message },
      }));
    }
  };

  // Copy code handler
  const handleCopyCode = (code, btn) => {
    navigator.clipboard.writeText(code).then(() => {
      btn.textContent = 'Copied!';
      setTimeout(() => {
        btn.textContent = 'Copy';
      }, 2000);
    });
  };

  // Extract all unique sources from resultData (root sources, step_outputs, and text annotations)
  const sourceNames = useMemo(() => {
    if (!resultData) return [];
    const collected = [];

    // 1. Root sources
    for (const s of resultData.sources || []) {
      const name = typeof s === 'string' ? s : s?.filename || s?.source_filename || s?.name;
      if (name) collected.push(name);
    }

    // 2. Step outputs sources
    for (const step of resultData.step_outputs || []) {
      for (const s of step.sources || []) {
        const name = typeof s === 'string' ? s : s?.filename || s?.source_filename || s?.name;
        if (name) collected.push(name);
      }
    }

    // 3. Generated files sources
    for (const f of resultData.generated_files || []) {
      for (const s of f.sources || []) {
        const name = typeof s === 'string' ? s : s?.filename || s?.source_filename || s?.name;
        if (name) collected.push(name);
      }
    }

    // 4. Fallback: Parse [Sources: ...] or [Source: ...] if present in text
    const textToScan = [
      resultData.result,
      ...(resultData.step_outputs || []).map((s) => s.output),
    ]
      .filter(Boolean)
      .join('\n');
    const match = textToScan.match(/\[Sources?:\s*([^\]]+)\]/i);
    if (match && match[1]) {
      const parsed = match[1]
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      collected.push(...parsed);
    }

    return [...new Set(collected.filter(Boolean))];
  }, [resultData]);

  // Clean answer text without raw trailing [Sources: ...] tag
  const cleanAnswer = useMemo(() => {
    if (!resultData?.result) return '';
    return resultData.result
      .replace(/\n*\[Sources?:\s*[^\]]+\]\s*$/i, '')
      .trim();
  }, [resultData]);

  return (
    <section className="screen">
      <div className={`greeting-wrap ${hasRun ? 'is-compact' : ''}`}>
        <h1 className="greeting">Where should we begin?</h1>
      </div>

      <div className="composer">
        <textarea
          ref={textareaRef}
          rows={1}
          placeholder="Ask about an SOP, run a calculation, or draft a report…"
          value={taskInput}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          disabled={running}
        />

        {attachedFile && (
          <div className="attachment">
            <svg className="icon icon-sm" viewBox="0 0 24 24">
              <path d="M14 4l-7.5 7.5a3 3 0 004.2 4.2L18 8.5" />
            </svg>
            <span>{attachedFile.name}</span>
            <button
              onClick={() => setAttachedFile(null)}
              title="Remove attachment"
            >
              <svg className="icon icon-sm" viewBox="0 0 24 24">
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </div>
        )}

        <div className="composer-bar">
          <button
            className="ghost-btn"
            onClick={() => fileInputRef.current?.click()}
            disabled={running || uploadingAttachment}
          >
            <svg className="icon icon-sm" viewBox="0 0 24 24">
              <path d="M14 4l-7.5 7.5a3 3 0 004.2 4.2L18 8.5" />
            </svg>
            <span>Attach</span>
          </button>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            hidden
          />

          <div className="composer-spacer" />

          <button
            className="send-btn"
            onClick={runTask}
            disabled={!taskInput.trim() || running}
            title="Run task"
          >
            <svg className="icon" viewBox="0 0 24 24">
              <path d="M12 19V5M6 11l6-6 6 6" />
            </svg>
          </button>
        </div>
      </div>

      {hasRun && (
        <div className="run">
          {modelMeta && <div className="run-meta">{modelMeta}</div>}

          {running && (
            <div className="thinking">
              <span className="pulse" />
              <span>{`${statusText} (${elapsedSeconds}s)`}</span>
            </div>
          )}

          {steps.length > 0 && (
            <div className="steps">
              {steps.map((step, idx) => {
                const isRunning =
                  running &&
                  step.status === 'pending' &&
                  (idx === 0 || steps[idx - 1].status === 'done');
                const stateClass = isRunning
                  ? 'is-running'
                  : step.status === 'done'
                  ? 'is-done'
                  : step.status === 'failed'
                  ? 'is-failed'
                  : 'is-pending';

                return (
                  <div key={idx} className={`step ${stateClass}`}>
                    <span className="step-marker" />
                    <div className="step-body">
                      <div className="step-tool">
                        {TOOL_LABELS[step.tool] || step.tool}
                      </div>
                      <div className="step-input">{step.input}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* Phase 11 Approval Card */}
          {resultData?.status === 'awaiting_approval' && (
            <div
              className={`card approval-card risk-is-${(
                resultData.approval?.risk || 'medium'
              ).toLowerCase()}`}
            >
              <p className="section-label">Human Approval Gate</p>
              <div className="approval-meta">
                <span
                  className={`risk-text-${(
                    resultData.approval?.risk || 'medium'
                  ).toLowerCase()}`}
                >
                  Risk: {(resultData.approval?.risk || 'medium').toUpperCase()}
                </span>
                <span className="approval-conf">
                  · Confidence:{' '}
                  {resultData.approval?.confidence !== undefined
                    ? Math.round(resultData.approval.confidence * 100)
                    : 50}
                  %
                </span>
              </div>
              <div className="approval-reasoning">
                {resultData.approval?.reasoning ||
                  'Document generation paused for human review.'}
              </div>

              <div className="approval-preview-box">
                <div className="approval-draft-title">
                  {resultData.draft_content?.title || 'Document Draft'}
                </div>
                {sourceNames.length > 0 && (
                  <div className="approval-sources-line">
                    <span className="doc-sources-label">Sources:</span>
                    <span className="doc-sources-names">
                      {sourceNames.join(', ')}
                    </span>
                  </div>
                )}
                {(resultData.draft_content?.sections || []).map((s, sIdx) => (
                  <div key={sIdx} className="approval-sec">
                    <div className="approval-sec-heading">
                      {s.heading || `Section ${sIdx + 1}`}
                    </div>
                    <p className="approval-sec-body">{s.body || ''}</p>
                  </div>
                ))}
              </div>

              {!approvalOutcome[resultData.task_id] && (
                <div className="approval-actions">
                  <button
                    className="btn btn-primary"
                    onClick={() =>
                      handleApprovalAction(resultData.task_id, 'approve')
                    }
                  >
                    <svg className="icon icon-sm" viewBox="0 0 24 24">
                      <path d="M20 6L9 17l-5-5" />
                    </svg>
                    <span>Approve</span>
                  </button>
                  <button
                    className="btn btn-secondary"
                    onClick={() =>
                      setEditingApproval((prev) => ({
                        ...prev,
                        [resultData.task_id]: !prev[resultData.task_id],
                      }))
                    }
                  >
                    <svg className="icon icon-sm" viewBox="0 0 24 24">
                      <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                      <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
                    </svg>
                    <span>Edit</span>
                  </button>
                  <button
                    className="btn btn-danger-quiet"
                    onClick={() =>
                      handleApprovalAction(resultData.task_id, 'reject')
                    }
                  >
                    <svg className="icon icon-sm" viewBox="0 0 24 24">
                      <path d="M18 6L6 18M6 6l12 12" />
                    </svg>
                    <span>Reject</span>
                  </button>
                </div>
              )}

              {editingApproval[resultData.task_id] &&
                !approvalOutcome[resultData.task_id] && (
                  <div className="approval-edit-wrap">
                    <label className="approval-edit-label">Document Title</label>
                    <input
                      className="approval-input"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                    />
                    <label className="approval-edit-label">
                      Sections Content (JSON)
                    </label>
                    <textarea
                      className="approval-textarea"
                      rows={6}
                      value={editSections}
                      onChange={(e) => setEditSections(e.target.value)}
                    />
                    <div className="approval-actions" style={{ marginTop: '8px' }}>
                      <button
                        className="btn btn-primary"
                        onClick={() =>
                          handleApprovalEditSubmit(resultData.task_id)
                        }
                      >
                        <span>Submit with Edits</span>
                      </button>
                      <button
                        className="btn btn-secondary"
                        onClick={() =>
                          setEditingApproval((prev) => ({
                            ...prev,
                            [resultData.task_id]: false,
                          }))
                        }
                      >
                        <span>Cancel</span>
                      </button>
                    </div>
                  </div>
                )}

              {approvalOutcome[resultData.task_id] && (
                <div style={{ marginTop: '12px' }}>
                  {approvalOutcome[resultData.task_id].loading && (
                    <div className="approval-notice">
                      {approvalOutcome[resultData.task_id].message}
                    </div>
                  )}
                  {approvalOutcome[resultData.task_id].rejected && (
                    <p className="error-note">
                      {approvalOutcome[resultData.task_id].message}
                    </p>
                  )}
                  {approvalOutcome[resultData.task_id].approved && (
                    <div>
                      <div
                        className="approval-notice"
                        style={{ marginBottom: '10px' }}
                      >
                        Document approved successfully!
                      </div>
                      <a
                        className="download-btn"
                        href={`/download/${encodeURIComponent(
                          approvalOutcome[resultData.task_id].filename
                        )}`}
                        download
                      >
                        <svg className="icon icon-sm" viewBox="0 0 24 24">
                          <path d="M12 4v12M7 13l5 5 5-5" />
                          <path d="M4 20h16" />
                        </svg>
                        <span>
                          Download{' '}
                          {approvalOutcome[resultData.task_id].title}
                        </span>
                      </a>
                    </div>
                  )}
                  {approvalOutcome[resultData.task_id].error && (
                    <p className="error-note">
                      Action failed:{' '}
                      {approvalOutcome[resultData.task_id].error}
                    </p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Standard Text Answer */}
          {resultData?.result && (
            <div className="card">
              <div className="answer">{cleanAnswer || resultData.result}</div>
            </div>
          )}

          {/* Referenced Sources Card */}
          {sourceNames.length > 0 &&
            resultData?.status !== 'awaiting_approval' && (
              <div className="card sources-card">
                <p className="section-label">Referenced Sources</p>
                <div className="sources-list">
                  {sourceNames.map((name, i) => (
                    <div key={i} className="source-item">
                      <svg className="icon icon-sm" viewBox="0 0 24 24">
                        <path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5z" />
                        <path d="M14 3v5h5" />
                      </svg>
                      <span className="source-name">{name}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

          {/* Generated Code Execution Cards */}
          {(resultData?.code_runs || []).map((run, cIdx) => {
            if (!run.code) return null;
            const langName =
              run.language === 'c'
                ? 'C'
                : run.language === 'javascript'
                ? 'JavaScript'
                : 'Python';
            const isErr = run.exit_code !== 0 || run.error;
            const duration =
              run.duration_seconds !== undefined
                ? `${run.duration_seconds}s`
                : '';
            const exitText =
              run.exit_code !== undefined ? `exit ${run.exit_code}` : '';
            const meta = [exitText, duration].filter(Boolean).join(' · ');

            return (
              <div key={cIdx} className="card code-card">
                <div className="code-header">
                  <div className="code-badges">
                    <span className="section-label" style={{ margin: 0 }}>
                      Generated Code
                    </span>
                    <span className="code-lang-badge">{langName}</span>
                  </div>
                  {meta && (
                    <span
                      className={`code-meta-badge ${
                        isErr ? 'is-error' : ''
                      }`}
                    >
                      {meta}
                    </span>
                  )}
                </div>

                <div className="code-wrap">
                  <button
                    className="copy-code-btn"
                    onClick={(e) => handleCopyCode(run.code, e.currentTarget)}
                    title="Copy code"
                  >
                    <svg className="icon" viewBox="0 0 24 24">
                      <rect x="9" y="9" width="13" height="13" rx="2" />
                      <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                    </svg>
                    <span>Copy</span>
                  </button>
                  <pre className="code-content">
                    <code>{run.code}</code>
                  </pre>
                </div>

                {(run.stdout || run.stderr) && (
                  <div className="code-output-box">
                    <div className="code-output-label">Terminal Output</div>
                    {run.stdout && (
                      <pre className="code-stdout">{run.stdout}</pre>
                    )}
                    {run.stderr && (
                      <pre className="code-stderr">{run.stderr}</pre>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {/* Generated Documents */}
          {(resultData?.generated_files || []).map((file, fIdx) => {
            if (!file.filename) return null;
            const fileSources = [
              ...new Set(
                (file.sources || rawSources)
                  .map((s) => (typeof s === 'string' ? s : s?.filename))
                  .filter(Boolean)
              ),
            ];

            return (
              <div key={fIdx} className="card">
                <p className="section-label">Generated document</p>
                <a
                  className="download-btn"
                  href={`/download/${encodeURIComponent(file.filename)}`}
                  download
                >
                  <svg className="icon icon-sm" viewBox="0 0 24 24">
                    <path d="M12 4v12M7 13l5 5 5-5" />
                    <path d="M4 20h16" />
                  </svg>
                  <span>{file.title || file.filename}</span>
                </a>
                {fileSources.length > 0 && (
                  <div className="doc-sources-meta">
                    <span className="doc-sources-label">
                      Sources cited in file:
                    </span>
                    <span className="doc-sources-names">
                      {fileSources.join(', ')}
                    </span>
                  </div>
                )}
              </div>
            );
          })}

          {errorMsg && <p className="error-note">{errorMsg}</p>}
          {resultData?.status === 'failed' && (
            <p className="error-note">
              The agent finished with errors — see the steps above.
            </p>
          )}
        </div>
      )}
    </section>
  );
}

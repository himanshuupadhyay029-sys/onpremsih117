import React, { useState, useMemo } from 'react';
import EvaluationPanel from './EvaluationPanel.jsx';

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
  excel: 'Spreadsheet builder',
  ppt: 'Presentation designer',
};

export default function MessageTurn({
  turn,
  user,
  onApprovalAction,
  onApprovalEditSubmit,
  onClarifyReply,
  onRetry,
}) {
  const [copiedCodeIdx, setCopiedCodeIdx] = useState(null);
  const [editingApproval, setEditingApproval] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editSections, setEditSections] = useState('');
  const [clarifyInput, setClarifyInput] = useState('');
  const [showReasoning, setShowReasoning] = useState(false);
  const [showThoughts, setShowThoughts] = useState(false);
  const [copiedAnswer, setCopiedAnswer] = useState(false);

  // Extract turn properties whether from live streaming or persisted DB record
  const isUser = turn.role === 'user';
  const isStreaming = turn.is_streaming;
  const isError = turn.is_error || turn.status === 'failed';
  const meta = turn.meta || {};

  // Extract steps
  const steps = useMemo(() => {
    if (turn.steps && turn.steps.length > 0) return turn.steps;
    if (meta.steps && meta.steps.length > 0) return meta.steps;
    return [];
  }, [turn.steps, meta.steps]);

  // Extract model metadata
  const modelMeta = useMemo(() => {
    if (turn.modelMeta) return turn.modelMeta;
    if (meta.models_used && meta.models_used.length > 1) {
      return `Models · ${meta.models_used.join(' → ')}`;
    }
    const distinctStepModels = Array.from(
      new Set(
        steps
          .map((s) => s.model)
          .filter((m) => m && !m.endsWith('_tool') && m !== 'vault_search')
      )
    );
    if (distinctStepModels.length > 1) {
      return `Models · ${distinctStepModels.join(' → ')}`;
    }
    if (meta.model_used) return `Model · ${meta.model_used}`;
    if (distinctStepModels.length === 1) return `Model · ${distinctStepModels[0]}`;
    if (meta.routing_decision?.model_role) {
      const role = meta.routing_decision.model_role;
      return `${MODEL_LABELS[role] || role} · ${meta.routing_decision.model_tag || ''}`;
    }
    return '';
  }, [turn.modelMeta, meta, steps]);


  // Extract code executions
  const codeRuns = useMemo(() => {
    if (turn.code_runs && turn.code_runs.length > 0) return turn.code_runs;
    if (meta.code_runs && meta.code_runs.length > 0) return meta.code_runs;
    return [];
  }, [turn.code_runs, meta.code_runs]);

  // Extract generated files
  const generatedFiles = useMemo(() => {
    if (turn.generated_files && turn.generated_files.length > 0) return turn.generated_files;
    if (meta.generated_files && meta.generated_files.length > 0) return meta.generated_files;
    return [];
  }, [turn.generated_files, meta.generated_files]);

  // Extract approval info
  const approval = useMemo(() => {
    return turn.approval || meta.approval || meta.approval_info || null;
  }, [turn.approval, meta.approval, meta.approval_info]);

  const draftContent = useMemo(() => {
    return turn.draft_content || meta.draft_content || null;
  }, [turn.draft_content, meta.draft_content]);

  const approvalOutcome = useMemo(() => {
    const fromTurn = turn.approvalOutcome || {};
    const tid = turn.task_id || meta.task_id;
    if (tid && fromTurn[tid]) return fromTurn;
    if (tid && meta.approval_outcome) {
      return {
        ...fromTurn,
        [tid]: meta.approval_outcome,
      };
    }
    return fromTurn;
  }, [turn.approvalOutcome, turn.task_id, meta.task_id, meta.approval_outcome]);

  // Extract all referenced sources
  const sourceNames = useMemo(() => {
    const collected = [];

    // 1. Root sources
    for (const s of turn.sources || meta.sources || []) {
      const name = typeof s === 'string' ? s : s?.filename || s?.source_filename || s?.name;
      if (name) collected.push(name);
    }

    // 2. Step outputs sources
    for (const step of turn.step_outputs || meta.step_outputs || []) {
      for (const s of step.sources || []) {
        const name = typeof s === 'string' ? s : s?.filename || s?.source_filename || s?.name;
        if (name) collected.push(name);
      }
    }

    // 3. Generated files sources
    for (const f of generatedFiles) {
      for (const s of f.sources || []) {
        const name = typeof s === 'string' ? s : s?.filename || s?.source_filename || s?.name;
        if (name) collected.push(name);
      }
    }

    // 4. Fallback text parsing [Sources: ...]
    const textToScan = [
      turn.content,
      turn.result,
      ...(turn.step_outputs || meta.step_outputs || []).map((s) => s.output),
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
  }, [turn, meta, generatedFiles]);

  // Clean answer text without raw trailing [Sources: ...] tag
  const cleanAnswer = useMemo(() => {
    const raw = turn.result || turn.content || '';
    return raw.replace(/\n*\[Sources?:\s*[^\]]+\]\s*$/i, '').trim();
  }, [turn.result, turn.content]);

  // Copy code handler
  const handleCopy = (code, idx) => {
    navigator.clipboard.writeText(code).then(() => {
      setCopiedCodeIdx(idx);
      setTimeout(() => setCopiedCodeIdx(null), 2000);
    });
  };

  const handleStartEdit = () => {
    if (draftContent) {
      setEditTitle(draftContent.title || '');
      setEditSections(JSON.stringify(draftContent.sections || [], null, 2));
    }
    setEditingApproval(true);
  };

  const handleSaveEdit = () => {
    if (onApprovalEditSubmit) {
      onApprovalEditSubmit(turn.task_id || meta.task_id, editTitle, editSections);
    }
    setEditingApproval(false);
  };

  const handleCopyAnswer = () => {
    if (!cleanAnswer) return;
    navigator.clipboard.writeText(cleanAnswer).then(() => {
      setCopiedAnswer(true);
      setTimeout(() => setCopiedAnswer(false), 2000);
    }).catch(() => {});
  };

  // -------------------------------------------------------------------------
  // USER TURN (Right-aligned bubble matching Claude)
  // -------------------------------------------------------------------------
  if (isUser) {
    let userAttachments = [];
    if (Array.isArray(turn.attachments) && turn.attachments.length > 0) {
      userAttachments = turn.attachments;
    } else if (Array.isArray(meta.attachments) && meta.attachments.length > 0) {
      userAttachments = meta.attachments;
    } else if (turn.content && turn.content.includes("Attached file:")) {
      const lines = turn.content.split("\n");
      const matched = lines
        .filter((l) => l.trim().startsWith("Attached file:"))
        .map((l) => {
          const rawPath = l.replace("Attached file:", "").trim();
          const name = rawPath.split(/[\\/]/).pop();
          return { name, path: rawPath };
        });
      if (matched.length > 0) userAttachments = matched;
    } else if (turn.attachedFile?.name || meta.filename || meta.attachment_name) {
      userAttachments = [{ name: turn.attachedFile?.name || meta.filename || meta.attachment_name }];
    }

    let userText = turn.content || '';
    if (userText.includes("\n\nAttached file:")) {
      userText = userText.split("\n\nAttached file:")[0];
    } else if (userText.includes("Attached file:")) {
      userText = userText.replace(/Attached file:[^\n]+(\n|$)/g, '').trim();
    }
    const vaultFiles = turn.vault_files || meta.vault_files || [];

    return (
      <div className="chat-msg-row chat-msg-row-user" id={`turn-${turn.id}`}>
        <div className="chat-msg chat-msg-user">
          {/* Multi-File Attached Files Tray */}
          {userAttachments.length > 0 && (
            <div className="chat-user-attachments-tray">
              {userAttachments.map((att, idx) => (
                <div className="chat-user-attachment-badge" key={idx} title={att.name || att.path}>
                  <svg className="icon icon-sm" viewBox="0 0 24 24">
                    <path d="M14 4l-7.5 7.5a3 3 0 004.2 4.2L18 8.5" />
                  </svg>
                  <span>{att.name || (att.path ? att.path.split(/[\\/]/).pop() : 'Attached File')}</span>
                </div>
              ))}
            </div>
          )}

          {/* Tagged Knowledge Vault Documents */}
          {Array.isArray(vaultFiles) && vaultFiles.length > 0 && (
            <div className="chat-user-vault-tags">
              {vaultFiles.map((vf) => (
                <div key={vf} className="chat-user-vault-chip" title="Knowledge Vault Document">
                  <svg className="icon icon-sm" viewBox="0 0 24 24">
                    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                  </svg>
                  <span>{vf}</span>
                </div>
              ))}
            </div>
          )}

          <div className="chat-msg-content">{userText}</div>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // ASSISTANT TURN (Left-aligned full-width matching Claude)
  // -------------------------------------------------------------------------
  return (
    <div className="chat-msg-row chat-msg-row-assistant" id={`turn-${turn.id}`}>
      <div className={`chat-msg chat-msg-assistant ${isStreaming ? 'is-streaming' : ''}`}>
        <div className="chat-msg-avatar">
          <svg className="icon" viewBox="0 0 24 24">
            <path d="M12 3l7 3v5.5c0 4.2-2.9 8.1-7 9.5-4.1-1.4-7-5.3-7-9.5V6l7-3z" />
          </svg>
        </div>

        <div className="chat-msg-body">
          <div className="chat-msg-header">
            <span className="chat-msg-role">KAVACH</span>
            {modelMeta && <span className="run-meta-pill">{modelMeta}</span>}
          </div>

          {/* Collapsible Thought Process (Steps & Reasoning) */}
          {(steps.length > 0 || ((turn.trace || meta.trace || []).length > 0) || isStreaming) && (
            <div className="thought-accordion">
              <button
                type="button"
                className="thought-toggle-btn"
                onClick={() => setShowThoughts(!showThoughts)}
                title="Toggle thought process and execution steps"
              >
                <svg className="icon-sparkle" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M12 2L9.5 8.5L3 11L9.5 13.5L12 20L14.5 13.5L21 11L14.5 8.5L12 2Z" />
                </svg>
                <span>
                  {isStreaming
                    ? (turn.statusText || 'Thinking…')
                    : `Thought process (${steps.length > 0 ? `${steps.length} step${steps.length === 1 ? '' : 's'}` : 'reasoning'})`}
                </span>
                <svg
                  className="chevron"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  style={{ transform: (isStreaming || showThoughts || (!cleanAnswer && !approval && deliverables.length === 0)) ? 'rotate(180deg)' : 'rotate(0deg)' }}
                >
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </button>

              {(isStreaming || showThoughts || (!cleanAnswer && !approval && deliverables.length === 0)) && (
                <div className="thought-content-box">
                  {isStreaming && (
                    <div className="thinking" style={{ marginBottom: '6px' }}>
                      <span className="pulse" />
                      <span>{turn.statusText || 'Planning steps…'}</span>
                    </div>
                  )}

                  {steps.length > 0 && (
                    <div className="steps">
                      {steps.map((step, idx) => {
                        const isRunning =
                          isStreaming &&
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
                              <div className="step-tool-row">
                                <div className="step-tool">
                                  {TOOL_LABELS[step.tool] || step.tool}
                                </div>
                                {(step.model || step.model_role) && (
                                  <span
                                    className="step-model-tag"
                                    title={`Executed with model: ${step.model || step.model_role}`}
                                  >
                                    <svg className="icon icon-xs" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                      <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        strokeWidth="2"
                                        d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"
                                      />
                                    </svg>
                                    <span>{step.model || step.model_role}</span>
                                  </span>
                                )}
                              </div>
                              <div className="step-input">{step.input}</div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {((turn.trace || meta.trace || []).length > 0) && (
                    <div style={{ marginTop: '8px', fontSize: '0.8rem', fontFamily: 'monospace' }}>
                      {(turn.trace || meta.trace || []).map((tr, tIdx) => (
                        <div key={tIdx} style={{ margin: '4px 0', color: tr.role === 'thought' ? '#38bdf8' : (tr.role === 'action' ? '#c084fc' : 'var(--text-secondary)') }}>
                          <strong style={{ textTransform: 'uppercase', marginRight: '6px' }}>[{tr.role}]:</strong>
                          <span>{tr.content}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

        {/* Human Approval Gate Card */}
        {approval && (
          <div className={`card approval-card risk-is-${(approval.risk || 'medium').toLowerCase()}`}>
            <p className="section-label">Human Approval Gate</p>
            <div className="approval-meta">
              <span className={`risk-text-${(approval.risk || 'medium').toLowerCase()}`}>
                Risk: {(approval.risk || 'medium').toUpperCase()}
              </span>
              <span className="approval-conf">
                · Confidence:{' '}
                {approval.confidence !== undefined ? Math.round(approval.confidence * 100) : 50}%
              </span>
            </div>
            <div className="approval-reasoning">
              {approval.reasoning || 'Document generation paused for human review.'}
            </div>

            {draftContent && (
              <div className="approval-preview-box">
                <div className="approval-draft-title">{draftContent.title || 'Document Draft'}</div>
                {sourceNames.length > 0 && (
                  <div className="approval-sources-line">
                    <span className="doc-sources-label">Sources:</span>
                    <span className="doc-sources-names">{sourceNames.join(', ')}</span>
                  </div>
                )}
                {(draftContent.sections || []).map((s, sIdx) => (
                  <div key={sIdx} className="approval-sec">
                    <div className="approval-sec-heading">{s.heading || `Section ${sIdx + 1}`}</div>
                    <p className="approval-sec-body">{s.body || ''}</p>
                  </div>
                ))}
              </div>
            )}

            {!approvalOutcome[turn.task_id || meta.task_id] && !editingApproval && (
              <div className="approval-actions">
                <button
                  className="btn btn-primary"
                  onClick={() => onApprovalAction && onApprovalAction(turn.task_id || meta.task_id, 'approve')}
                >
                  <svg className="icon icon-sm" viewBox="0 0 24 24">
                    <path d="M20 6L9 17l-5-5" />
                  </svg>
                  <span>Approve</span>
                </button>
                <button className="btn btn-secondary" onClick={handleStartEdit}>
                  <svg className="icon icon-sm" viewBox="0 0 24 24">
                    <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                    <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                  <span>Edit</span>
                </button>
                <button
                  className="btn btn-danger-quiet"
                  onClick={() => onApprovalAction && onApprovalAction(turn.task_id || meta.task_id, 'reject')}
                >
                  <svg className="icon icon-sm" viewBox="0 0 24 24">
                    <path d="M18 6L6 18M6 6l12 12" />
                  </svg>
                  <span>Reject</span>
                </button>
              </div>
            )}

            {editingApproval && (
              <div className="approval-edit-wrap">
                <label className="approval-edit-label">Document Title</label>
                <input
                  className="approval-input"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                />
                <label className="approval-edit-label">Sections Content (JSON)</label>
                <textarea
                  className="approval-textarea"
                  rows={6}
                  value={editSections}
                  onChange={(e) => setEditSections(e.target.value)}
                />
                <div className="approval-actions" style={{ marginTop: '8px' }}>
                  <button className="btn btn-primary" onClick={handleSaveEdit}>
                    <span>Submit with Edits</span>
                  </button>
                  <button className="btn btn-secondary" onClick={() => setEditingApproval(false)}>
                    <span>Cancel</span>
                  </button>
                </div>
              </div>
            )}

            {approvalOutcome[turn.task_id || meta.task_id] && (
              <div style={{ marginTop: '12px' }}>
                {approvalOutcome[turn.task_id || meta.task_id].loading && (
                  <div className="approval-notice">
                    {approvalOutcome[turn.task_id || meta.task_id].message}
                  </div>
                )}
                {approvalOutcome[turn.task_id || meta.task_id].rejected && (
                  <p className="error-note">
                    {approvalOutcome[turn.task_id || meta.task_id].message}
                  </p>
                )}
                {approvalOutcome[turn.task_id || meta.task_id].approved && (
                  <div>
                    <div className="approval-notice" style={{ marginBottom: '10px' }}>
                      Document approved successfully!
                    </div>
                    <a
                      className="download-btn"
                      href={`/download/${encodeURIComponent(
                        approvalOutcome[turn.task_id || meta.task_id].filename
                      )}`}
                      download
                    >
                      <svg className="icon icon-sm" viewBox="0 0 24 24">
                        <path d="M12 4v12M7 13l5 5 5-5" />
                        <path d="M4 20h16" />
                      </svg>
                      <span>Download {approvalOutcome[turn.task_id || meta.task_id].title}</span>
                    </a>
                  </div>
                )}
                {approvalOutcome[turn.task_id || meta.task_id].error && (
                  <p className="error-note">
                    Action failed: {approvalOutcome[turn.task_id || meta.task_id].error}
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {/* Interactive Clarification Request from Agent */}
        {(turn.clarify_question || meta.clarify_question) && (
          <div className="card clarify-card" style={{ borderLeft: '3px solid #f59e0b', background: 'rgba(245, 158, 11, 0.06)', padding: '16px', borderRadius: '8px', marginBottom: '16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#f59e0b', fontWeight: 600, marginBottom: '8px' }}>
              <svg className="icon icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <circle cx="12" cy="12" r="10" strokeWidth="2" />
                <path d="M12 16v-4M12 8h.01" strokeWidth="2" strokeLinecap="round" />
              </svg>
              <span>Operator Clarification Needed</span>
            </div>
            <p style={{ margin: '0 0 12px 0', fontSize: '0.95rem', color: 'var(--text-primary, #e2e8f0)' }}>
              {turn.clarify_question || meta.clarify_question}
            </p>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                className="input"
                placeholder="Type your response to continue workflow..."
                value={clarifyInput}
                onChange={(e) => setClarifyInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && clarifyInput.trim()) {
                    if (onClarifyReply) onClarifyReply(turn.task_id || meta.task_id, clarifyInput);
                    setClarifyInput('');
                  }
                }}
                style={{ flex: 1, padding: '8px 12px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.15)', background: 'rgba(0,0,0,0.25)', color: '#fff' }}
              />
              <button
                className="btn btn-primary"
                onClick={() => {
                  if (clarifyInput.trim()) {
                    if (onClarifyReply) onClarifyReply(turn.task_id || meta.task_id, clarifyInput);
                    setClarifyInput('');
                  }
                }}
              >
                Send Answer
              </button>
            </div>
          </div>
        )}

        {/* Standard Text Answer */}
        {cleanAnswer && (
          <div className="answer">
            {cleanAnswer}
          </div>
        )}

        {/* Action Bar (Copy / Regenerate) */}
        {!isStreaming && cleanAnswer && (
          <div className="chat-msg-actions">
            <button
              type="button"
              className={`chat-action-btn ${copiedAnswer ? 'is-copied' : ''}`}
              onClick={handleCopyAnswer}
              title={copiedAnswer ? 'Copied to clipboard' : 'Copy response'}
            >
              {copiedAnswer ? (
                <>
                  <svg className="icon icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  <span>Copied</span>
                </>
              ) : (
                <>
                  <svg className="icon icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                  </svg>
                  <span>Copy</span>
                </>
              )}
            </button>
            {onRetry && (
              <button
                type="button"
                className="chat-action-btn"
                onClick={() => onRetry(turn.retryPrompt || turn.content)}
                title="Regenerate response"
              >
                <svg className="icon icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="1 4 1 10 7 10" />
                  <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
                </svg>
                <span>Regenerate</span>
              </button>
            )}
          </div>
        )}

        {/* Referenced Sources Card */}
        {sourceNames.length > 0 && !approval && (
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

        <EvaluationPanel evaluation={turn.evaluation || meta.evaluation} />

        {/* Generated Code Execution Cards (Consolidated & Interactive) */}
        {codeRuns.map((run, cIdx) => (
          <InteractiveCodeCard key={cIdx} run={run} cIdx={cIdx} />
        ))}

        {/* Generated Documents & Real Deliverables (Word, Excel, PowerPoint) */}
        {generatedFiles.map((file, fIdx) => {
          if (!file.filename) return null;
          const fn = file.filename.toLowerCase();
          const isXlsx = fn.endsWith('.xlsx') || fn.endsWith('.csv') || file.file_type === 'excel';
          const isPptx = fn.endsWith('.pptx') || file.file_type === 'ppt';
          const isDocx = fn.endsWith('.docx') || file.file_type === 'document' || (!isXlsx && !isPptx);

          const cardClass = isXlsx
            ? 'deliverable-card deliverable-xlsx'
            : isPptx
            ? 'deliverable-card deliverable-pptx'
            : 'deliverable-card deliverable-docx';

          const tagClass = isXlsx ? 'tag-xlsx' : isPptx ? 'tag-pptx' : 'tag-docx';
          const tagLabel = isXlsx
            ? '📊 EXCEL SPREADSHEET (.xlsx)'
            : isPptx
            ? '📽️ PRESENTATION DECK (.pptx)'
            : '📘 FORMAL REPORT (.docx)';

          const btnClass = isXlsx ? 'btn-xlsx' : isPptx ? 'btn-pptx' : 'btn-docx';

          const fileSources = [
            ...new Set(
              (file.sources || turn.sources || meta.sources || [])
                .map((s) => (typeof s === 'string' ? s : s?.filename))
                .filter(Boolean)
            ),
          ];

          return (
            <div key={fIdx} className={`card ${cardClass}`}>
              <div className="deliverable-header">
                <span className={`deliverable-tag ${tagClass}`}>{tagLabel}</span>
                {isXlsx && file.total_rows && (
                  <span className="code-lang-badge" style={{ background: 'rgba(16, 185, 129, 0.15)', color: '#34d399' }}>
                    {file.total_rows} data rows · formulas active
                  </span>
                )}
                {isPptx && file.slides_count && (
                  <span className="code-lang-badge" style={{ background: 'rgba(249, 115, 22, 0.15)', color: '#fb923c' }}>
                    {file.slides_count} slides · 16:9 widescreen
                  </span>
                )}
              </div>

              <div>
                <a
                  className={`download-btn ${btnClass}`}
                  href={`/download/${encodeURIComponent(file.filename)}`}
                  download
                >
                  {isXlsx ? (
                    <svg className="icon icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                      <rect x="3" y="3" width="18" height="18" rx="2" strokeWidth="2" />
                      <path d="M3 9h18M3 15h18M9 3v18M15 3v18" strokeWidth="1.5" />
                    </svg>
                  ) : isPptx ? (
                    <svg className="icon icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                      <rect x="2" y="3" width="20" height="14" rx="2" strokeWidth="2" />
                      <path d="M8 21h8M12 17v4" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                  ) : (
                    <svg className="icon icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" strokeWidth="2" />
                      <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                  )}
                  <span>Download {file.title || file.filename}</span>
                </a>
              </div>

              {isXlsx && file.sheets && file.sheets.length > 0 && (
                <div className="deliverable-meta-details">
                  <span className="deliverable-meta-item">
                    <strong>Sheets:</strong> {file.sheets.join(', ')}
                  </span>
                </div>
              )}

              {isDocx && fileSources.length > 0 && (
                <div className="doc-sources-meta">
                  <span className="doc-sources-label">Sources cited in file:</span>
                  <span className="doc-sources-names">{fileSources.join(', ')}</span>
                </div>
              )}
            </div>
          );
        })}

        {/* Error Note & Retry Button */}
        {isError && (
          <div className="error-turn-box">
            <p className="error-note">
              {turn.errorMsg || 'The task encountered an error during execution.'}
            </p>
            {onRetry && turn.retryPrompt && (
              <button className="btn btn-secondary retry-btn" onClick={() => onRetry(turn.retryPrompt)}>
                <svg className="icon icon-sm" viewBox="0 0 24 24">
                  <path d="M1 4v6h6M23 20v-6h-6" />
                  <path d="M20.49 9A9 9 0 005.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 013.51 15" />
                </svg>
                <span>Retry</span>
              </button>
            )}
          </div>
        )}
      </div>
    </div>
    </div>
  );
}

function InteractiveCodeCard({ run, cIdx }) {
  const [copied, setCopied] = useState(false);
  const [selectedAttemptIdx, setSelectedAttemptIdx] = useState(-1);
  const [isEditing, setIsEditing] = useState(false);
  const [code, setCode] = useState(run.code || '');
  const [userInput, setUserInput] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [executionResult, setExecutionResult] = useState(null);
  const [showInputDrawer, setShowInputDrawer] = useState(false);

  React.useEffect(() => {
    setCode(run.code || '');
    setExecutionResult(null);
  }, [run.code]);

  const allAttempts = useMemo(() => {
    const prev = run.revisions || [];
    return [...prev, run];
  }, [run]);

  const hasRevisions = allAttempts.length > 1;
  const isViewingHistorical = selectedAttemptIdx >= 0 && selectedAttemptIdx < allAttempts.length - 1;
  const currentItem = isViewingHistorical ? allAttempts[selectedAttemptIdx] : null;

  const displayCode = currentItem ? currentItem.code : code;
  const displayLang = (currentItem ? currentItem.language : run.language) || 'python';
  const langName = displayLang === 'c' ? 'C' : displayLang === 'javascript' ? 'JavaScript' : 'Python';

  const activeData = executionResult || currentItem || run;
  const isErr = activeData.exit_code !== 0 || activeData.error;
  const duration = activeData.duration_seconds !== undefined ? `${activeData.duration_seconds}s` : '';
  const exitText = activeData.exit_code !== undefined ? `exit ${activeData.exit_code}` : '';
  const metaStr = [exitText, duration].filter(Boolean).join(' · ');

  const handleCopy = () => {
    navigator.clipboard.writeText(displayCode).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleRunInSandbox = async () => {
    try {
      setIsRunning(true);
      const res = await fetch('/code/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: displayCode,
          language: displayLang,
          stdin: userInput || null,
        }),
      });
      if (!res.ok) throw new Error(`Server returned HTTP ${res.status}`);
      const data = await res.json();
      setExecutionResult(data);
    } catch (err) {
      setExecutionResult({
        success: false,
        stdout: '',
        stderr: `Execution failed: ${err.message}`,
        exit_code: -1,
        duration_seconds: 0.0,
      });
    } finally {
      setIsRunning(false);
    }
  };

  return (
    <div className="card code-card interactive-code-card">
      <div className="code-header">
        <div className="code-badges">
          <span className="section-label" style={{ margin: 0 }}>Generated Code</span>
          <span className="code-lang-badge">{langName}</span>
          {hasRevisions && (
            <span className="revision-pill">
              Attempt {isViewingHistorical ? selectedAttemptIdx + 1 : allAttempts.length} of {allAttempts.length}
            </span>
          )}
        </div>
        <div className="code-header-right">
          {metaStr && (
            <span className={`code-meta-badge ${isErr ? 'is-error' : 'is-success'}`}>
              {metaStr}
            </span>
          )}
        </div>
      </div>

      {/* Revision Switcher Tabs if multiple attempts occurred */}
      {hasRevisions && (
        <div className="code-revision-tabs">
          <span className="revision-tabs-label">Revisions:</span>
          {allAttempts.map((att, aIdx) => {
            const isLast = aIdx === allAttempts.length - 1;
            const isSelected = isLast ? (!isViewingHistorical) : (selectedAttemptIdx === aIdx);
            const label = isLast
              ? `Latest (Attempt ${aIdx + 1})`
              : `Attempt ${aIdx + 1} (${att.exit_code === 0 ? 'Passed' : 'Failed'})`;
            return (
              <button
                key={aIdx}
                type="button"
                className={`rev-tab-btn ${isSelected ? 'active' : ''} ${att.exit_code !== 0 ? 'had-error' : ''}`}
                onClick={() => {
                  setSelectedAttemptIdx(isLast ? -1 : aIdx);
                  setIsEditing(false);
                  setExecutionResult(null);
                }}
              >
                {label}
              </button>
            );
          })}
        </div>
      )}

      {/* Code Editor or Viewer */}
      <div className="code-wrap">
        <div className="code-actions-bar">
          <button
            type="button"
            className="code-action-btn"
            onClick={() => setIsEditing(!isEditing)}
            title={isEditing ? "View code" : "Edit code"}
          >
            <svg className="icon" viewBox="0 0 24 24" width="13" height="13" stroke="currentColor" fill="none">
              <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <span>{isEditing ? "Done Editing" : "Edit"}</span>
          </button>
          <button
            type="button"
            className="code-action-btn"
            onClick={handleCopy}
            title="Copy code"
          >
            <svg className="icon" viewBox="0 0 24 24" width="13" height="13">
              <rect x="9" y="9" width="13" height="13" rx="2" />
              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
            </svg>
            <span>{copied ? "Copied!" : "Copy"}</span>
          </button>
        </div>

        {isEditing ? (
          <textarea
            className="code-editor-textarea"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            rows={Math.max(6, Math.min(22, code.split('\n').length + 1))}
            spellCheck="false"
          />
        ) : (
          <pre className="code-content">
            <code>{displayCode}</code>
          </pre>
        )}
      </div>

      {/* Interactive Controls & Stdin Drawer Toggle */}
      <div className="code-interactive-controls">
        <div className="controls-left">
          <button
            type="button"
            className={`btn-toggle-stdin ${showInputDrawer || userInput ? 'active' : ''}`}
            onClick={() => setShowInputDrawer(!showInputDrawer)}
          >
            <svg className="icon" viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" fill="none">
              <polyline points="4 17 10 11 4 5" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              <line x1="12" y1="19" x2="20" y2="19" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            <span>{showInputDrawer ? "Hide Terminal Input (stdin)" : (userInput ? "Terminal Input (stdin): Active" : "Provide Input (stdin)")}</span>
          </button>
        </div>

        <div className="controls-right">
          <button
            type="button"
            className="btn btn-sm btn-run-sandbox"
            onClick={handleRunInSandbox}
            disabled={isRunning}
          >
            {isRunning ? (
              <>
                <span className="spinner-micro"></span>
                <span>Executing in Docker...</span>
              </>
            ) : (
              <>
                <svg className="icon" viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                  <polygon points="5 3 19 12 5 21 5 3"/>
                </svg>
                <span>Run in Sandbox</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Stdin Drawer */}
      {showInputDrawer && (
        <div className="stdin-drawer">
          <div className="stdin-header">
            <span className="stdin-title">Standard Input (stdin passed to script):</span>
          </div>
          <textarea
            className="stdin-textarea"
            placeholder="Type input values here (e.g. name, values, lines of text to send to input())..."
            value={userInput}
            onChange={(e) => setUserInput(e.target.value)}
            rows={2}
          />
        </div>
      )}

      {/* Terminal Output */}
      {(activeData.stdout || activeData.stderr) && (
        <div className="code-output-box">
          <div className="code-output-header">
            <span className="code-output-label">Terminal Output</span>
            {activeData.duration_seconds !== undefined && (
              <span className="output-time-tag">{activeData.duration_seconds}s</span>
            )}
          </div>
          {activeData.stdout && <pre className="code-stdout">{activeData.stdout}</pre>}
          {activeData.stderr && <pre className="code-stderr">{activeData.stderr}</pre>}
        </div>
      )}
    </div>
  );
}



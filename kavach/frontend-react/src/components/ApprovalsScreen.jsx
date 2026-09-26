import React, { useState, useEffect, useCallback, useMemo } from 'react';

export default function ApprovalsScreen({ user, onShowAuth, onSelectChat }) {
  const [activeTab, setActiveTab] = useState('pending'); // 'pending' | 'history'
  const [pendingList, setPendingList] = useState([]);
  const [historyList, setHistoryList] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [deptFilter, setDeptFilter] = useState('all');
  const [riskFilter, setRiskFilter] = useState('all');

  // Expanded card IDs
  const [expandedCards, setExpandedCards] = useState({});

  // Action states
  const [processingTaskId, setProcessingTaskId] = useState(null);
  const [actionSuccess, setActionSuccess] = useState(null);

  // Edit Modal State
  const [editingTask, setEditingTask] = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const [editSectionsJson, setEditSectionsJson] = useState('');
  const [editError, setEditError] = useState('');

  // Reject Modal State
  const [rejectingTask, setRejectingTask] = useState(null);
  const [rejectReason, setRejectReason] = useState('');

  // View Diff Modal State
  const [diffViewTask, setDiffViewTask] = useState(null);

  // Fetch pending approvals
  const fetchPending = useCallback(async () => {
    if (!user) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch('/approvals/pending', { credentials: 'include' });
      if (!res.ok) {
        throw new Error(`Failed to load pending approvals: ${res.statusText}`);
      }
      const data = await res.json();
      setPendingList(data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [user]);

  // Fetch approval history
  const fetchHistory = useCallback(async () => {
    if (!user) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch('/approvals/history', { credentials: 'include' });
      if (!res.ok) {
        throw new Error(`Failed to load approval history: ${res.statusText}`);
      }
      const data = await res.json();
      setHistoryList(data || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [user]);

  useEffect(() => {
    if (activeTab === 'pending') {
      fetchPending();
    } else {
      fetchHistory();
    }
  }, [activeTab, fetchPending, fetchHistory]);

  const toggleExpand = (taskId) => {
    setExpandedCards((prev) => ({ ...prev, [taskId]: !prev[taskId] }));
  };

  // Direct Approve
  const handleApprove = async (taskId) => {
    setProcessingTaskId(taskId);
    setActionSuccess(null);
    try {
      const res = await fetch(`/approval/${encodeURIComponent(taskId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ decision: 'approve' }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.message || 'Failed to approve task.');
      }
      setActionSuccess(`Task ${taskId.slice(0, 8)} approved successfully. Deliverable generated!`);
      fetchPending();
    } catch (err) {
      alert(`Approval error: ${err.message}`);
    } finally {
      setProcessingTaskId(null);
    }
  };

  // Open Edit Modal
  const handleOpenEdit = (task) => {
    setEditingTask(task);
    const content = task.document_content || {};
    setEditTitle(content.title || task.task_prompt || 'Technical Document');
    const sections = content.sections || [];
    setEditSectionsJson(JSON.stringify(sections, null, 2));
    setEditError('');
  };

  // Submit Edit & Approve
  const handleSubmitEdit = async () => {
    if (!editingTask) return;
    let parsedSections = [];
    try {
      parsedSections = JSON.parse(editSectionsJson);
      if (!Array.isArray(parsedSections)) {
        throw new Error('Sections must be a JSON array of objects.');
      }
    } catch (err) {
      setEditError(`Invalid JSON: ${err.message}`);
      return;
    }

    setProcessingTaskId(editingTask.task_id);
    setActionSuccess(null);
    try {
      const payload = {
        decision: 'edit',
        edited_content: {
          title: editTitle,
          sections: parsedSections,
          sources: editingTask.document_content?.sources || [],
        },
      };

      const res = await fetch(`/approval/${encodeURIComponent(editingTask.task_id)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.message || 'Failed to submit edits.');
      }
      setActionSuccess(`Task ${editingTask.task_id.slice(0, 8)} approved with supervisory modifications!`);
      setEditingTask(null);
      fetchPending();
    } catch (err) {
      setEditError(err.message);
    } finally {
      setProcessingTaskId(null);
    }
  };

  // Open Reject Modal
  const handleOpenReject = (task) => {
    setRejectingTask(task);
    setRejectReason('');
  };

  // Submit Rejection
  const handleSubmitReject = async () => {
    if (!rejectingTask) return;
    setProcessingTaskId(rejectingTask.task_id);
    setActionSuccess(null);
    try {
      const res = await fetch(`/approval/${encodeURIComponent(rejectingTask.task_id)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          decision: 'reject',
          edited_content: rejectReason ? { rejection_reason: rejectReason } : null,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || data.message || 'Failed to reject task.');
      }
      setActionSuccess(`Task ${rejectingTask.task_id.slice(0, 8)} rejected. Execution aborted.`);
      setRejectingTask(null);
      fetchPending();
    } catch (err) {
      alert(`Rejection error: ${err.message}`);
    } finally {
      setProcessingTaskId(null);
    }
  };

  // Filtered lists
  const filteredList = useMemo(() => {
    const list = activeTab === 'pending' ? pendingList : historyList;
    return list.filter((item) => {
      // Dept filter
      if (deptFilter !== 'all' && item.department !== deptFilter) return false;
      // Risk filter
      if (riskFilter !== 'all' && (item.risk_level || 'medium').toLowerCase() !== riskFilter) return false;
      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchTitle = (item.document_content?.title || '').toLowerCase().includes(q);
        const matchPrompt = (item.task_prompt || '').toLowerCase().includes(q);
        const matchReq = (item.requester_name || '').toLowerCase().includes(q);
        const matchEmail = (item.requester_email || '').toLowerCase().includes(q);
        const matchId = (item.task_id || '').toLowerCase().includes(q);
        if (!matchTitle && !matchPrompt && !matchReq && !matchEmail && !matchId) return false;
      }
      return true;
    });
  }, [activeTab, pendingList, historyList, deptFilter, riskFilter, searchQuery]);

  return (
    <section className="screen approvals-screen">
      {/* Screen Header */}
      <div className="screen-head approvals-head">
        <div className="approvals-title-group">
          <div className="approvals-icon-wrap">
            <svg className="icon" viewBox="0 0 24 24" width="24" height="24">
              <path d="M9 11l3 3L22 4" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <h2 className="screen-title">Supervisory Approval Center</h2>
            <p className="screen-sub">
              Human-in-the-loop oversight, safety backstops, and regulatory release gate for industrial procedures.
            </p>
          </div>
        </div>

        {/* Tab Switcher */}
        <div className="approvals-tabs">
          <button
            className={`approvals-tab-btn ${activeTab === 'pending' ? 'active' : ''}`}
            onClick={() => setActiveTab('pending')}
          >
            <span>Pending Review</span>
            {pendingList.length > 0 && (
              <span className="approvals-badge-count">{pendingList.length}</span>
            )}
          </button>
          <button
            className={`approvals-tab-btn ${activeTab === 'history' ? 'active' : ''}`}
            onClick={() => setActiveTab('history')}
          >
            <span>Decision History</span>
            {historyList.length > 0 && (
              <span className="approvals-badge-neutral">{historyList.length}</span>
            )}
          </button>
        </div>
      </div>

      {/* Success Banner */}
      {actionSuccess && (
        <div className="approvals-alert-success">
          <svg className="icon" viewBox="0 0 24 24" width="16" height="16">
            <path d="M20 6L9 17l-5-5" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>{actionSuccess}</span>
          <button className="alert-close-btn" onClick={() => setActionSuccess(null)}>×</button>
        </div>
      )}

      {/* Filter / Search Bar */}
      <div className="approvals-toolbar">
        <div className="approvals-search-box">
          <svg className="icon search-icon" viewBox="0 0 24 24" width="14" height="14">
            <circle cx="11" cy="11" r="8" stroke="currentColor" fill="none" strokeWidth="2" />
            <path d="M21 21l-4.35-4.35" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <input
            type="text"
            className="input approvals-search-input"
            placeholder="Search by requester, prompt, document title, or task ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="approvals-filters">
          <select
            className="input select-filter"
            value={deptFilter}
            onChange={(e) => setDeptFilter(e.target.value)}
          >
            <option value="all">All Departments</option>
            <option value="maintenance">Maintenance</option>
            <option value="process">Process Engineering</option>
            <option value="hse">HSE / Safety</option>
            <option value="general">General Plant</option>
          </select>

          <select
            className="input select-filter"
            value={riskFilter}
            onChange={(e) => setRiskFilter(e.target.value)}
          >
            <option value="all">All Risk Levels</option>
            <option value="high">High Risk</option>
            <option value="medium">Medium Risk</option>
            <option value="low">Low Risk</option>
          </select>

          <button
            className="btn btn-secondary btn-refresh"
            onClick={activeTab === 'pending' ? fetchPending : fetchHistory}
            disabled={isLoading}
            title="Refresh items"
          >
            <svg className={`icon ${isLoading ? 'spinner-micro' : ''}`} viewBox="0 0 24 24" width="14" height="14">
              <path d="M23 4v6h-6M1 20v-6h6" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="approvals-content-wrap">
        {isLoading && (
          <div className="approvals-loading">
            <div className="spinner-micro"></div>
            <span>Loading {activeTab === 'pending' ? 'pending sign-offs' : 'decision history'}…</span>
          </div>
        )}

        {error && (
          <div className="approvals-error-box">
            <svg className="icon" viewBox="0 0 24 24" width="16" height="16">
              <circle cx="12" cy="12" r="10" stroke="currentColor" fill="none" strokeWidth="2" />
              <path d="M12 8v4M12 16h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <span>{error}</span>
          </div>
        )}

        {!isLoading && filteredList.length === 0 && (
          <div className="approvals-empty-state">
            <div className="empty-icon-wrap">
              <svg className="icon" viewBox="0 0 24 24" width="32" height="32">
                <path d="M9 12l2 2 4-4" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                <rect x="3" y="4" width="18" height="18" rx="2" stroke="currentColor" fill="none" strokeWidth="2" />
              </svg>
            </div>
            <h3>No {activeTab === 'pending' ? 'Pending Tasks' : 'Records Found'}</h3>
            <p>
              {activeTab === 'pending'
                ? 'All industrial procedure drafts and gated tasks have been reviewed. Safe operations intact!'
                : 'No historical approvals match your current filter settings.'}
            </p>
          </div>
        )}

        {/* PENDING APPROVAL CARDS */}
        {activeTab === 'pending' && filteredList.map((item) => {
          const isExpanded = !!expandedCards[item.task_id];
          const riskLower = (item.risk_level || 'medium').toLowerCase();
          const docContent = item.document_content || {};
          const sections = docContent.sections || [];
          const isProcessing = processingTaskId === item.task_id;

          return (
            <div key={item.task_id} className={`card approval-inbox-card risk-is-${riskLower}`}>
              {/* Card Header */}
              <div className="inbox-card-header">
                <div className="requester-info">
                  <div className="requester-avatar">
                    {(item.requester_name || 'U')[0].toUpperCase()}
                  </div>
                  <div>
                    <div className="requester-name-line">
                      <span className="requester-name">{item.requester_name}</span>
                      <span className="badge-dept">{item.department || 'general'}</span>
                      <span className={`risk-badge risk-${riskLower}`}>
                        RISK: {(item.risk_level || 'medium').toUpperCase()}
                      </span>
                    </div>
                    <div className="requester-sub-line">
                      <span>{item.requester_email || 'System User'}</span>
                      <span className="meta-dot">·</span>
                      <span>Requested: {item.requested_at ? new Date(item.requested_at).toLocaleString() : 'Just now'}</span>
                    </div>
                  </div>
                </div>

                <div className="inbox-card-conf">
                  <div className="conf-value">{Math.round((item.confidence || 0.5) * 100)}%</div>
                  <div className="conf-label">Grounded Confidence</div>
                </div>
              </div>

              {/* Task Prompt Box */}
              <div className="inbox-task-prompt-box">
                <div className="prompt-label">Operator Request Prompt:</div>
                <div className="prompt-text">“{item.task_prompt || 'Draft procedure document.'}”</div>
              </div>

              {/* Risk Reasoning Callout */}
              <div className="inbox-risk-callout">
                <div className="risk-callout-header">
                  <svg className="icon" viewBox="0 0 24 24" width="14" height="14">
                    <path d="M12 2L2 7l10 5 10-5-10-5z" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M2 17l10 5 10-5" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M2 12l10 5 10-5" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span>Safety Backstop Assessment:</span>
                </div>
                <p className="risk-callout-body">{item.reasoning}</p>
              </div>

              {/* Document Draft Preview Accordion */}
              <div className="inbox-draft-box">
                <div className="draft-box-header" onClick={() => toggleExpand(item.task_id)}>
                  <div className="draft-box-title">
                    <svg className="icon" viewBox="0 0 24 24" width="14" height="14">
                      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="currentColor" fill="none" strokeWidth="2" />
                      <path d="M14 2v6h6" stroke="currentColor" fill="none" strokeWidth="2" />
                      <line x1="16" y1="13" x2="8" y2="13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                      <line x1="16" y1="17" x2="8" y2="17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                    <strong>Draft Title:</strong> {docContent.title || 'Technical Document'}
                  </div>
                  <button type="button" className="btn-expand-preview">
                    {isExpanded ? 'Collapse Preview ▲' : `Preview Draft (${sections.length} sections) ▼`}
                  </button>
                </div>

                {isExpanded && (
                  <div className="draft-box-body">
                    {sections.length === 0 && (
                      <p className="empty-sections-text">No structured sections in preview.</p>
                    )}
                    {sections.map((sec, sIdx) => (
                      <div key={sIdx} className="draft-section-item">
                        <div className="sec-heading">{sec.heading || `Section ${sIdx + 1}`}</div>
                        <p className="sec-body">{sec.body || ''}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Action Controls */}
              <div className="inbox-card-actions">
                <button
                  type="button"
                  className="btn btn-primary btn-action-approve"
                  onClick={() => handleApprove(item.task_id)}
                  disabled={isProcessing}
                >
                  <svg className="icon" viewBox="0 0 24 24" width="14" height="14">
                    <path d="M20 6L9 17l-5-5" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span>Approve & Release</span>
                </button>

                <button
                  type="button"
                  className="btn btn-secondary btn-action-edit"
                  onClick={() => handleOpenEdit(item)}
                  disabled={isProcessing}
                >
                  <svg className="icon" viewBox="0 0 24 24" width="14" height="14">
                    <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span>Edit & Sign Off</span>
                </button>

                <button
                  type="button"
                  className="btn btn-danger-quiet btn-action-reject"
                  onClick={() => handleOpenReject(item)}
                  disabled={isProcessing}
                >
                  <svg className="icon" viewBox="0 0 24 24" width="14" height="14">
                    <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                  <span>Reject</span>
                </button>
              </div>
            </div>
          );
        })}

        {/* DECISION HISTORY TABLE / CARDS */}
        {activeTab === 'history' && filteredList.map((item) => {
          const dec = (item.decision || item.status || 'approved').toLowerCase();
          const docContent = item.document_content || {};

          return (
            <div key={item.task_id} className="card history-item-card">
              <div className="history-card-top">
                <div className="history-status-group">
                  {dec === 'approved' && <span className="status-pill pill-approved">✓ Approved</span>}
                  {dec === 'edited' && <span className="status-pill pill-edited">✎ Approved with Edits</span>}
                  {dec === 'reject' || dec === 'rejected' ? <span className="status-pill pill-rejected">✕ Rejected</span> : null}
                  <span className="badge-dept">{item.department || 'general'}</span>
                  <span className="history-task-id">ID: {item.task_id.slice(0, 8)}</span>
                </div>

                <div className="history-timestamp">
                  Resolved: {item.decided_at ? new Date(item.decided_at).toLocaleString() : 'N/A'}
                </div>
              </div>

              <div className="history-card-body">
                <div className="history-doc-title">
                  {docContent.title || item.task_prompt || 'Industrial Deliverable'}
                </div>
                <div className="history-prompt-text">
                  “{item.task_prompt || ''}”
                </div>

                <div className="history-meta-row">
                  <div>
                    <span className="meta-label">Requester:</span> <strong>{item.requester_name}</strong> ({item.requester_email || 'engineer'})
                  </div>
                  <div>
                    <span className="meta-label">Decided By:</span> <strong>{item.approver_name || 'Plant Supervisor'}</strong>
                  </div>
                </div>
              </div>

              <div className="history-card-actions">
                {item.download_url && (
                  <a
                    href={item.download_url}
                    download
                    className="btn btn-primary btn-sm btn-download-history"
                  >
                    <svg className="icon" viewBox="0 0 24 24" width="13" height="13">
                      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      <polyline points="7 10 12 15 17 10" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      <line x1="12" y1="15" x2="12" y2="3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                    <span>Download {item.filename || '.docx'}</span>
                  </a>
                )}

                {item.diff && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setDiffViewTask(item)}
                  >
                    <svg className="icon" viewBox="0 0 24 24" width="13" height="13">
                      <path d="M16 16v1a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h1" stroke="currentColor" fill="none" strokeWidth="2" />
                      <rect x="8" y="2" width="15" height="14" rx="2" stroke="currentColor" fill="none" strokeWidth="2" />
                    </svg>
                    <span>View Diff</span>
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* EDIT MODAL */}
      {editingTask && (
        <div className="modal-backdrop" onClick={() => setEditingTask(null)}>
          <div className="modal-card edit-approval-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h3>Supervisor Modification & Sign-Off</h3>
              <button className="modal-close" onClick={() => setEditingTask(null)}>×</button>
            </div>

            <div className="modal-body">
              <p className="modal-description">
                You are modifying this generated draft before authorizing release. Your modifications will be recorded with a cryptographic unified diff in the audit trail.
              </p>

              {editError && <div className="edit-error-banner">{editError}</div>}

              <div className="form-group">
                <label className="form-label">Document Title</label>
                <input
                  type="text"
                  className="input edit-modal-input"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label className="form-label">Sections Content (JSON Array)</label>
                <textarea
                  className="input edit-modal-textarea"
                  rows={14}
                  value={editSectionsJson}
                  onChange={(e) => setEditSectionsJson(e.target.value)}
                  spellCheck="false"
                />
              </div>
            </div>

            <div className="modal-foot">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setEditingTask(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleSubmitEdit}
                disabled={processingTaskId === editingTask.task_id}
              >
                {processingTaskId === editingTask.task_id ? 'Saving & Generating...' : 'Save & Authorize Release'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* REJECT MODAL */}
      {rejectingTask && (
        <div className="modal-backdrop" onClick={() => setRejectingTask(null)}>
          <div className="modal-card reject-approval-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h3>Confirm Task Rejection</h3>
              <button className="modal-close" onClick={() => setRejectingTask(null)}>×</button>
            </div>

            <div className="modal-body">
              <p className="modal-description">
                Rejecting this task will abort deliverable generation. The requesting engineer will be notified that this procedure was not approved for release.
              </p>

              <div className="form-group">
                <label className="form-label">Reason for Rejection (Optional but Recommended)</label>
                <textarea
                  className="input reject-reason-textarea"
                  rows={4}
                  placeholder="e.g. Missing dual barrier isolation permit; violates plant safety regulation 4.1."
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                />
              </div>
            </div>

            <div className="modal-foot">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setRejectingTask(null)}
              >
                Back
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={handleSubmitReject}
                disabled={processingTaskId === rejectingTask.task_id}
              >
                Confirm Rejection
              </button>
            </div>
          </div>
        </div>
      )}

      {/* VIEW DIFF MODAL */}
      {diffViewTask && (
        <div className="modal-backdrop" onClick={() => setDiffViewTask(null)}>
          <div className="modal-card diff-viewer-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h3>Unified Diff: Supervisory Modifications</h3>
              <button className="modal-close" onClick={() => setDiffViewTask(null)}>×</button>
            </div>

            <div className="modal-body">
              <p className="diff-meta-desc">
                Task ID: <code>{diffViewTask.task_id}</code> · Requester: <strong>{diffViewTask.requester_name}</strong> · Approved by: <strong>{diffViewTask.approver_name}</strong>
              </p>
              <pre className="diff-code-box">
                {diffViewTask.diff.split('\n').map((line, idx) => {
                  let cls = 'diff-line';
                  if (line.startsWith('+') && !line.startsWith('+++')) cls += ' diff-add';
                  else if (line.startsWith('-') && !line.startsWith('---')) cls += ' diff-del';
                  else if (line.startsWith('@')) cls += ' diff-hunk';
                  return (
                    <div key={idx} className={cls}>
                      {line}
                    </div>
                  );
                })}
              </pre>
            </div>

            <div className="modal-foot">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setDiffViewTask(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

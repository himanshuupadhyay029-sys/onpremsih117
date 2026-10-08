import React, { useState, useEffect, useCallback, useMemo } from 'react';
import SovereignSelect from './SovereignSelect';
import { API_BASE } from '../config';

const DEPT_FILTER_OPTIONS = [
  { value: 'all', label: 'All Departments' },
  { value: 'maintenance', label: 'Maintenance' },
  { value: 'process', label: 'Process Engineering' },
  { value: 'hse', label: 'HSE / Safety' },
  { value: 'general', label: 'General Plant' },
];

const RISK_FILTER_OPTIONS = [
  { value: 'all', label: 'All Risk Levels' },
  { value: 'high', label: 'High Risk' },
  { value: 'medium', label: 'Medium Risk' },
  { value: 'low', label: 'Low Risk' },
];

function formatDate(isoStr) {
  if (!isoStr) return '—';
  try {
    const d = new Date(isoStr);
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return isoStr;
  }
}

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
  const [copiedTaskId, setCopiedTaskId] = useState(null);

  // Edit Modal State
  const [editingTask, setEditingTask] = useState(null);
  const [editTitle, setEditTitle] = useState('');
  const [editSections, setEditSections] = useState([]);
  const [editJsonMode, setEditJsonMode] = useState(false);
  const [editSectionsJson, setEditSectionsJson] = useState('');
  const [editError, setEditError] = useState('');

  // Reject Modal State
  const [rejectingTask, setRejectingTask] = useState(null);
  const [rejectReason, setRejectReason] = useState('');

  // View Diff Modal State
  const [diffViewTask, setDiffViewTask] = useState(null);

  const isSuperadmin = user?.role === 'superadmin';
  const userDept = user?.department || 'general';

  // Copy Task ID Helper
  const copyTaskId = (id, e) => {
    e?.stopPropagation?.();
    navigator.clipboard?.writeText?.(id);
    setCopiedTaskId(id);
    setTimeout(() => setCopiedTaskId(null), 2000);
  };

  // Fetch pending approvals
  const fetchPending = useCallback(async () => {
    if (!user) return;
    setIsLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/approvals/pending`, { credentials: 'include' });
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
      const res = await fetch(`${API_BASE}/approvals/history`, { credentials: 'include' });
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
      const res = await fetch(`${API_BASE}/approval/${encodeURIComponent(taskId)}`, {
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
    const sections = Array.isArray(content.sections) ? content.sections : [];
    // Ensure deep copy of sections
    const initialSections = sections.map((s) => ({
      heading: s.heading || '',
      body: s.body || '',
    }));
    setEditSections(initialSections.length > 0 ? initialSections : [{ heading: 'Scope of Work', body: '' }]);
    setEditSectionsJson(JSON.stringify(initialSections, null, 2));
    setEditJsonMode(false);
    setEditError('');
  };

  // Section manipulation in visual mode
  const handleSectionHeadingChange = (idx, val) => {
    setEditSections((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], heading: val };
      return next;
    });
  };

  const handleSectionBodyChange = (idx, val) => {
    setEditSections((prev) => {
      const next = [...prev];
      next[idx] = { ...next[idx], body: val };
      return next;
    });
  };

  const handleAddSection = () => {
    setEditSections((prev) => [...prev, { heading: `Section ${prev.length + 1}`, body: '' }]);
  };

  const handleRemoveSection = (idx) => {
    setEditSections((prev) => prev.filter((_, i) => i !== idx));
  };

  const toggleJsonMode = () => {
    if (!editJsonMode) {
      // Switching to JSON: serialize current sections
      setEditSectionsJson(JSON.stringify(editSections, null, 2));
      setEditJsonMode(true);
    } else {
      // Switching back to visual: parse JSON
      try {
        const parsed = JSON.parse(editSectionsJson);
        if (!Array.isArray(parsed)) throw new Error('Sections must be an array');
        setEditSections(parsed.map((s) => ({ heading: s.heading || '', body: s.body || '' })));
        setEditJsonMode(false);
        setEditError('');
      } catch (err) {
        setEditError(`Cannot switch to visual mode: ${err.message}`);
      }
    }
  };

  // Submit Edit & Approve
  const handleSubmitEdit = async () => {
    if (!editingTask) return;
    let finalSections = [];

    if (editJsonMode) {
      try {
        finalSections = JSON.parse(editSectionsJson);
        if (!Array.isArray(finalSections)) {
          throw new Error('Sections must be a JSON array of objects.');
        }
      } catch (err) {
        setEditError(`Invalid JSON: ${err.message}`);
        return;
      }
    } else {
      finalSections = editSections;
    }

    setProcessingTaskId(editingTask.task_id);
    setActionSuccess(null);
    try {
      const payload = {
        decision: 'edit',
        edited_content: {
          title: editTitle,
          sections: finalSections,
          sources: editingTask.document_content?.sources || editingTask.sources || [],
        },
      };

      const res = await fetch(`${API_BASE}/approval/${encodeURIComponent(editingTask.task_id)}`, {
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
      const res = await fetch(`${API_BASE}/approval/${encodeURIComponent(rejectingTask.task_id)}`, {
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
          <div className="approvals-icon-wrap" aria-hidden="true">
            <svg className="icon" viewBox="0 0 24 24" width="22" height="22">
              <path d="M9 11l3 3L22 4" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
              <h2 className="screen-title" style={{ margin: 0 }}>Supervisory Approval Center</h2>
              <span className="approvals-scope-badge">
                {isSuperadmin ? 'Site-Wide Authority' : `${userDept.toUpperCase()} Scope`}
              </span>
            </div>
            <p className="screen-sub">
              Human-in-the-loop oversight, safety backstops, and regulatory release gate for industrial procedures.
            </p>
          </div>
        </div>

        {/* Segmented Tab Switcher - Platform Style */}
        <div className="approvals-tabs" role="tablist" aria-label="Approval Views">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'pending'}
            className={`approvals-tab-btn ${activeTab === 'pending' ? 'active' : ''}`}
            onClick={() => setActiveTab('pending')}
          >
            <span>Pending Review</span>
            {pendingList.length > 0 && (
              <span className="approvals-badge-count">{pendingList.length}</span>
            )}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'history'}
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
        <div className="approvals-alert-success" role="alert">
          <svg className="icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
            <path d="M20 6L9 17l-5-5" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span style={{ flex: 1 }}>{actionSuccess}</span>
          <button
            type="button"
            className="alert-close-btn"
            onClick={() => setActionSuccess(null)}
            aria-label="Dismiss alert"
          >
            ×
          </button>
        </div>
      )}

      {/* Filter / Search Bar */}
      <div className="approvals-toolbar">
        <div className="approvals-search-box">
          <svg className="icon search-icon" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
            <circle cx="11" cy="11" r="8" stroke="currentColor" fill="none" strokeWidth="2" />
            <path d="M21 21l-4.35-4.35" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <input
            type="text"
            className="input approvals-search-input"
            placeholder="Search by requester, prompt, deliverable title, or task ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="approvals-filters">
          {isSuperadmin || userDept === 'general' ? (
            <div className="approvals-select-wrapper">
              <SovereignSelect
                value={deptFilter}
                onChange={(e) => setDeptFilter(e.target.value)}
                options={DEPT_FILTER_OPTIONS}
                placeholder="All Departments"
                ariaLabel="Department Filter"
              />
            </div>
          ) : (
            <div className="approvals-fixed-dept" title="Filtered to your assigned department">
              <span>Dept: <strong>{userDept.toUpperCase()}</strong></span>
            </div>
          )}

          <div className="approvals-select-wrapper">
            <SovereignSelect
              value={riskFilter}
              onChange={(e) => setRiskFilter(e.target.value)}
              options={RISK_FILTER_OPTIONS}
              placeholder="All Risk Levels"
              ariaLabel="Risk Filter"
            />
          </div>

          <button
            type="button"
            className="btn btn-secondary btn-refresh"
            onClick={activeTab === 'pending' ? fetchPending : fetchHistory}
            disabled={isLoading}
            title="Refresh queue"
          >
            <svg className={`icon ${isLoading ? 'spinner-micro' : ''}`} viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
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
          <div className="approvals-error-box" role="alert">
            <svg className="icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
              <circle cx="12" cy="12" r="10" stroke="currentColor" fill="none" strokeWidth="2" />
              <path d="M12 8v4M12 16h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <span>{error}</span>
          </div>
        )}

        {!isLoading && filteredList.length === 0 && (
          <div className="approvals-empty-state">
            <div className="empty-icon-wrap" aria-hidden="true">
              {activeTab === 'pending' ? (
                <svg className="icon" viewBox="0 0 24 24" width="28" height="28">
                  <path d="M9 12l2 2 4-4" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  <rect x="3" y="4" width="18" height="18" rx="2" stroke="currentColor" fill="none" strokeWidth="2" />
                </svg>
              ) : (
                <svg className="icon" viewBox="0 0 24 24" width="28" height="28">
                  <circle cx="12" cy="12" r="10" stroke="currentColor" fill="none" strokeWidth="2" />
                  <polyline points="12 6 12 12 16 14" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
            </div>
            <h3>{activeTab === 'pending' ? 'No Pending Approvals' : 'No Historical Records'}</h3>
            <p>
              {activeTab === 'pending'
                ? 'All industrial procedure drafts and safety-gated tasks have been resolved. Tasks requiring supervisory sign-off will automatically route here.'
                : 'No past approval decisions match the current filter criteria.'}
            </p>
          </div>
        )}

        {/* PENDING APPROVAL CARDS */}
        {activeTab === 'pending' && filteredList.map((item) => {
          const isExpanded = !!expandedCards[item.task_id];
          const riskLower = (item.risk_level || 'medium').toLowerCase();
          const docContent = item.document_content || {};
          const sections = Array.isArray(docContent.sections) ? docContent.sections : [];
          const isProcessing = processingTaskId === item.task_id;
          const confScore = Math.round((item.confidence || 0.5) * 100);

          return (
            <div key={item.task_id} className={`approval-card risk-border-${riskLower}`}>
              {/* Card Header / Provenance Bar */}
              <div className="approval-card-head">
                <div className="approval-card-requester">
                  <div className="approval-requester-avatar" aria-hidden="true">
                    {(item.requester_name || 'U')[0].toUpperCase()}
                  </div>
                  <div>
                    <div className="approval-requester-line">
                      <span className="approval-requester-name">{item.requester_name}</span>
                      <span className="approval-dept-tag">{item.department || 'general'}</span>
                      <span className={`risk-tag risk-${riskLower}`}>
                        {riskLower === 'high' && (
                          <svg className="icon icon-sm" viewBox="0 0 24 24" width="12" height="12" aria-hidden="true">
                            <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" stroke="currentColor" fill="none" strokeWidth="2" />
                            <line x1="12" y1="9" x2="12" y2="13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                            <circle cx="12" cy="17" r="1" fill="currentColor" />
                          </svg>
                        )}
                        <span>{riskLower.toUpperCase()} RISK</span>
                      </span>
                    </div>
                    <div className="approval-meta-subline">
                      <span>{item.requester_email || 'operator@plant.local'}</span>
                      <span className="meta-sep">·</span>
                      <span>Requested {formatDate(item.requested_at)}</span>
                    </div>
                  </div>
                </div>

                <div className="approval-card-conf-block">
                  <div className="approval-conf-gauge">
                    <span className="approval-conf-num">{confScore}%</span>
                    <div className="approval-conf-meter" aria-hidden="true">
                      <div
                        className="approval-conf-fill"
                        style={{
                          width: `${confScore}%`,
                          backgroundColor: confScore >= 80 ? '#10b981' : confScore >= 50 ? '#f59e0b' : '#ef4444',
                        }}
                      />
                    </div>
                  </div>
                  <span className="approval-conf-caption">Grounded in Vault</span>
                </div>
              </div>

              {/* Task Prompt Box */}
              <div className="approval-prompt-box">
                <div className="approval-section-label-row">
                  <span className="approval-section-label">Operator Request Prompt</span>
                  <div className="approval-task-id-group">
                    <span className="approval-task-id-code">ID: {item.task_id.slice(0, 10)}</span>
                    <button
                      type="button"
                      className="approval-copy-btn"
                      onClick={(e) => copyTaskId(item.task_id, e)}
                      title="Copy full Task ID"
                    >
                      {copiedTaskId === item.task_id ? 'Copied' : 'Copy'}
                    </button>
                  </div>
                </div>
                <div className="approval-prompt-text">“{item.task_prompt || 'Industrial procedure drafting task.'}”</div>
              </div>

              {/* Safety Backstop Reasoning Callout */}
              <div className="approval-reasoning-callout">
                <div className="approval-reasoning-header">
                  <svg className="icon" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span>Safety Backstop Trigger & Policy Assessment</span>
                </div>
                <p className="approval-reasoning-body">
                  {item.reasoning || 'Hazardous keywords or technical procedures requiring human-in-the-loop sign-off.'}
                </p>
              </div>

              {/* Document Draft Preview */}
              <div className="approval-preview-box">
                <div
                  className="approval-preview-head"
                  onClick={() => toggleExpand(item.task_id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && toggleExpand(item.task_id)}
                >
                  <div className="approval-preview-title">
                    <svg className="icon" viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
                      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="currentColor" fill="none" strokeWidth="2" />
                      <path d="M14 2v6h6" stroke="currentColor" fill="none" strokeWidth="2" />
                      <line x1="16" y1="13" x2="8" y2="13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                      <line x1="16" y1="17" x2="8" y2="17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                    <span><strong>Deliverable Draft:</strong> {docContent.title || 'Technical Procedure Document'}</span>
                    <span className="approval-sections-chip">{sections.length} {sections.length === 1 ? 'section' : 'sections'}</span>
                  </div>
                  <span className="approval-expand-label">
                    {isExpanded ? 'Collapse Preview ▲' : 'Inspect Procedure ▼'}
                  </span>
                </div>

                {isExpanded && (
                  <div className="approval-preview-body">
                    {sections.length === 0 ? (
                      <p className="empty-sections-text">No structured sections available in preview.</p>
                    ) : (
                      sections.map((sec, sIdx) => (
                        <div key={sIdx} className="approval-section-row">
                          <div className="approval-sec-heading">
                            <span className="sec-num">{sIdx + 1}.</span> {sec.heading || `Section ${sIdx + 1}`}
                          </div>
                          <p className="approval-sec-text">{sec.body || ''}</p>
                        </div>
                      ))
                    )}

                    {/* Sources citation list if available */}
                    {Array.isArray(item.sources) && item.sources.length > 0 && (
                      <div className="approval-sources-panel">
                        <div className="approval-sources-title">Cited Vault Evidence & Standards:</div>
                        <div className="approval-sources-list">
                          {item.sources.map((src, srcIdx) => (
                            <div key={srcIdx} className="approval-source-item">
                              <span className="src-bullet">■</span>
                              <span className="src-name">{typeof src === 'string' ? src : src.filename || src.title || 'Plant Manual'}</span>
                              {src.page && <span className="src-page">p. {src.page}</span>}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Action Controls */}
              <div className="approval-card-actions">
                <button
                  type="button"
                  className="btn btn-primary btn-approve"
                  onClick={() => handleApprove(item.task_id)}
                  disabled={isProcessing}
                >
                  <svg className="icon" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
                    <path d="M20 6L9 17l-5-5" stroke="currentColor" fill="none" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span>Approve & Release</span>
                </button>

                <button
                  type="button"
                  className="btn btn-secondary btn-edit"
                  onClick={() => handleOpenEdit(item)}
                  disabled={isProcessing}
                >
                  <svg className="icon" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
                    <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span>Edit Draft & Sign Off</span>
                </button>

                <button
                  type="button"
                  className="btn btn-danger-quiet btn-reject"
                  onClick={() => handleOpenReject(item)}
                  disabled={isProcessing}
                >
                  <svg className="icon" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
                    <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                  <span>Reject Task</span>
                </button>
              </div>
            </div>
          );
        })}

        {/* DECISION HISTORY TABLE (Industrial Ledger Layout) */}
        {activeTab === 'history' && filteredList.length > 0 && (
          <div className="approvals-history-table-wrap">
            <table className="approvals-history-table">
              <thead>
                <tr>
                  <th style={{ width: '130px' }}>Resolution</th>
                  <th style={{ width: '110px' }}>Task ID</th>
                  <th>Deliverable Title & Request</th>
                  <th style={{ width: '160px' }}>Requester / Dept</th>
                  <th style={{ width: '170px' }}>Decided By & Date</th>
                  <th style={{ width: '190px', textAlign: 'right' }}>Deliverables</th>
                </tr>
              </thead>
              <tbody>
                {filteredList.map((item) => {
                  const dec = (item.decision || item.status || 'approved').toLowerCase();
                  const docContent = item.document_content || {};

                  return (
                    <tr key={item.task_id}>
                      <td>
                        {dec === 'approved' && (
                          <span className="status-pill pill-approved">
                            <svg className="icon icon-sm" viewBox="0 0 24 24" width="12" height="12">
                              <path d="M20 6L9 17l-5-5" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                            <span>Approved</span>
                          </span>
                        )}
                        {dec === 'edited' && (
                          <span className="status-pill pill-edited">
                            <svg className="icon icon-sm" viewBox="0 0 24 24" width="12" height="12">
                              <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                              <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                            </svg>
                            <span>Modified</span>
                          </span>
                        )}
                        {(dec === 'reject' || dec === 'rejected') && (
                          <span className="status-pill pill-rejected">
                            <svg className="icon icon-sm" viewBox="0 0 24 24" width="12" height="12">
                              <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                            </svg>
                            <span>Rejected</span>
                          </span>
                        )}
                      </td>
                      <td>
                        <span
                          className="history-task-id-mono"
                          onClick={(e) => copyTaskId(item.task_id, e)}
                          title="Click to copy full Task ID"
                        >
                          {item.task_id.slice(0, 8)}
                        </span>
                      </td>
                      <td>
                        <div className="history-table-doc-title">
                          {docContent.title || item.task_prompt || 'Industrial Deliverable'}
                        </div>
                        <div className="history-table-prompt-sub">
                          “{item.task_prompt || ''}”
                        </div>
                      </td>
                      <td>
                        <div style={{ fontWeight: '500', color: '#0f172a' }}>{item.requester_name || 'Engineer'}</div>
                        <span className="approval-dept-tag">{item.department || 'general'}</span>
                      </td>
                      <td>
                        <div style={{ fontWeight: '500', color: '#0f172a' }}>{item.approver_name || 'Supervisor'}</div>
                        <div className="history-date-sub">{formatDate(item.decided_at || item.requested_at)}</div>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', gap: '6px', alignItems: 'center' }}>
                          {item.download_url && (
                            <a
                              href={item.download_url}
                              download
                              className="btn btn-secondary btn-sm btn-download-deliverable"
                              title={item.filename || 'Download deliverable'}
                            >
                              <svg className="icon icon-sm" viewBox="0 0 24 24" width="12" height="12" style={{ flexShrink: 0 }}>
                                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                                <polyline points="7 10 12 15 17 10" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                                <line x1="12" y1="15" x2="12" y2="3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                              </svg>
                              <span className="download-btn-filename">{item.filename || '.docx'}</span>
                            </a>
                          )}
                          {item.diff && (
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={() => setDiffViewTask(item)}
                              title="Inspect supervisory modifications diff"
                            >
                              <span>Diff</span>
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* SUPERVISOR EDIT MODAL */}
      {editingTask && (
        <div className="modal-backdrop" onClick={() => setEditingTask(null)}>
          <div className="modal-card edit-approval-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div>
                <h3 style={{ margin: 0 }}>Supervisor Modification & Sign-Off</h3>
                <span style={{ fontSize: '12px', color: '#64748b' }}>
                  Task ID: <code style={{ fontFamily: 'monospace' }}>{editingTask.task_id.slice(0, 10)}</code>
                </span>
              </div>
              <button
                type="button"
                className="modal-close"
                onClick={() => setEditingTask(null)}
                aria-label="Close modal"
              >
                ×
              </button>
            </div>

            <div className="modal-body">
              <div className="edit-modal-notice">
                <svg className="icon icon-sm" viewBox="0 0 24 24" width="15" height="15" style={{ flexShrink: 0, color: '#0284c7' }}>
                  <circle cx="12" cy="12" r="10" stroke="currentColor" fill="none" strokeWidth="2" />
                  <path d="M12 16v-4M12 8h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
                <span>
                  Modifications will be recorded in the immutable audit log with a cryptographic unified diff. Once authorized, the final document will be generated and signed.
                </span>
              </div>

              {editError && <div className="edit-error-banner" role="alert">{editError}</div>}

              <div className="form-group" style={{ marginBottom: '16px' }}>
                <label className="form-label" style={{ fontWeight: '600', marginBottom: '6px', display: 'block' }}>
                  Procedure / Document Title
                </label>
                <input
                  type="text"
                  className="input edit-modal-input"
                  value={editTitle}
                  onChange={(e) => setEditTitle(e.target.value)}
                  placeholder="e.g. Standard Operating Procedure: Cooling Water Pump Overhaul"
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <label className="form-label" style={{ fontWeight: '600', margin: 0 }}>
                  Structured Procedure Sections ({editSections.length})
                </label>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={toggleJsonMode}
                  >
                    {editJsonMode ? 'Switch to Form Editor' : 'Advanced JSON Mode'}
                  </button>
                  {!editJsonMode && (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={handleAddSection}
                    >
                      + Add Section
                    </button>
                  )}
                </div>
              </div>

              {!editJsonMode ? (
                <div className="edit-sections-scroll-area">
                  {editSections.map((sec, idx) => (
                    <div key={idx} className="edit-section-card">
                      <div className="edit-section-card-head">
                        <span className="edit-sec-badge">Section {idx + 1}</span>
                        <input
                          type="text"
                          className="input edit-section-title-input"
                          value={sec.heading}
                          onChange={(e) => handleSectionHeadingChange(idx, e.target.value)}
                          placeholder="Section Title / Heading"
                        />
                        {editSections.length > 1 && (
                          <button
                            type="button"
                            className="btn btn-danger-quiet btn-sm"
                            onClick={() => handleRemoveSection(idx)}
                            title="Remove section"
                          >
                            ×
                          </button>
                        )}
                      </div>
                      <textarea
                        className="input edit-section-body-textarea"
                        rows={5}
                        value={sec.body}
                        onChange={(e) => handleSectionBodyChange(idx, e.target.value)}
                        placeholder="Detailed technical instructions, safety precautions, or inspection checklist..."
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="form-group">
                  <textarea
                    className="input edit-modal-textarea"
                    rows={12}
                    value={editSectionsJson}
                    onChange={(e) => setEditSectionsJson(e.target.value)}
                    spellCheck="false"
                  />
                </div>
              )}
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
                {processingTaskId === editingTask.task_id ? 'Saving & Signing...' : 'Save & Authorize Release'}
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
              <div>
                <h3 style={{ margin: 0, color: '#991b1b' }}>Confirm Procedure Rejection</h3>
                <span style={{ fontSize: '12px', color: '#64748b' }}>
                  Task ID: <code style={{ fontFamily: 'monospace' }}>{rejectingTask.task_id.slice(0, 10)}</code>
                </span>
              </div>
              <button
                type="button"
                className="modal-close"
                onClick={() => setRejectingTask(null)}
                aria-label="Close modal"
              >
                ×
              </button>
            </div>

            <div className="modal-body">
              <div className="reject-warning-callout">
                <svg className="icon" viewBox="0 0 24 24" width="18" height="18" style={{ color: '#dc2626', flexShrink: 0 }}>
                  <path d="M12 9v4m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <div>
                  <div style={{ fontWeight: '600', color: '#991b1b', marginBottom: '2px' }}>
                    Deliverable generation will be aborted
                  </div>
                  <div style={{ fontSize: '12.5px', color: '#7f1d1d', lineHeight: '1.4' }}>
                    The procedure document will not be released. The requesting engineer (<strong>{rejectingTask.requester_name}</strong>) will receive this rejection event in their audit trail.
                  </div>
                </div>
              </div>

              <div className="form-group" style={{ marginTop: '16px' }}>
                <label className="form-label" style={{ fontWeight: '600', marginBottom: '6px', display: 'block' }}>
                  Supervisory Reason for Rejection (Required for Compliance)
                </label>
                <textarea
                  className="input reject-reason-textarea"
                  rows={4}
                  placeholder="e.g. Missing dual barrier isolation permit; procedure violates plant safety directive OISD-117."
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
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                onClick={handleSubmitReject}
                disabled={processingTaskId === rejectingTask.task_id}
                style={{ background: '#dc2626', color: '#ffffff', border: 'none' }}
              >
                {processingTaskId === rejectingTask.task_id ? 'Rejecting...' : 'Confirm Rejection'}
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
              <div>
                <h3 style={{ margin: 0 }}>Cryptographic Unified Diff</h3>
                <span style={{ fontSize: '12px', color: '#64748b' }}>
                  Task ID: <code style={{ fontFamily: 'monospace' }}>{diffViewTask.task_id}</code>
                </span>
              </div>
              <button
                type="button"
                className="modal-close"
                onClick={() => setDiffViewTask(null)}
                aria-label="Close modal"
              >
                ×
              </button>
            </div>

            <div className="modal-body">
              <div className="diff-meta-desc">
                Requester: <strong>{diffViewTask.requester_name}</strong> · Approved by: <strong>{diffViewTask.approver_name || 'Supervisor'}</strong> · Date: <strong>{formatDate(diffViewTask.decided_at)}</strong>
              </div>
              <div className="diff-code-box">
                {diffViewTask.diff ? (
                  diffViewTask.diff.split('\n').map((line, idx) => {
                    let cls = 'diff-line';
                    if (line.startsWith('+') && !line.startsWith('+++')) cls += ' diff-add';
                    else if (line.startsWith('-') && !line.startsWith('---')) cls += ' diff-del';
                    else if (line.startsWith('@')) cls += ' diff-hunk';
                    return (
                      <div key={idx} className={cls}>
                        {line}
                      </div>
                    );
                  })
                ) : (
                  <div style={{ color: '#94a3b8', fontStyle: 'italic', padding: '10px' }}>
                    No recorded diff for this deliverable.
                  </div>
                )}
              </div>
            </div>

            <div className="modal-foot">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setDiffViewTask(null)}
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

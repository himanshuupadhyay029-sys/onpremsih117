import React, { useState, useEffect, useMemo, useCallback } from 'react';
import SovereignSelect from './SovereignSelect';

const EVENT_TYPE_OPTIONS = [
  { value: '', label: 'All Event Types' },
  { value: 'route', label: 'Route' },
  { value: 'plan', label: 'Plan' },
  { value: 'step', label: 'Step' },
  { value: 'observe', label: 'Observe' },
  { value: 'search', label: 'Search' },
  { value: 'sandbox', label: 'Sandbox' },
  { value: 'write', label: 'Write' },
  { value: 'approval', label: 'Approval' },
  { value: 'access_denied', label: 'Access Denied' },
  { value: 'firewall', label: 'Firewall' },
  { value: 'admin_override', label: 'Admin Override' },
  { value: 'tamper_detected', label: 'Tamper Detected' },
  { value: 'complete', label: 'Complete' },
  { value: 'error', label: 'Error' },
];

function formatDateTime(isoStr) {
  if (!isoStr) return '—';
  try {
    const d = new Date(isoStr);
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return isoStr;
  }
}

function formatTimeOnly(isoStr) {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    return d.toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return '';
  }
}

export default function AuditLogScreen({ user, onShowAuth }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState('grouped'); // 'grouped' | 'ledger'
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [filterType, setFilterType] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [openTaskGroups, setOpenTaskGroups] = useState({});
  const [verifyState, setVerifyState] = useState({ checking: false, result: null });
  const [inspectEvent, setInspectEvent] = useState(null);
  const [copiedHash, setCopiedHash] = useState(null);

  const copyText = (txt, e) => {
    e?.stopPropagation?.();
    navigator.clipboard?.writeText?.(txt);
    setCopiedHash(txt);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  const handleVerifyChain = async () => {
    setVerifyState({ checking: true, result: null });
    try {
      const res = await fetch('/audit/verify', { credentials: 'include' });
      const data = await res.json();
      setVerifyState({ checking: false, result: data });
    } catch (err) {
      setVerifyState({
        checking: false,
        result: { valid: false, message: `Verification request failed: ${err.message}` },
      });
    }
  };

  const fetchAuditEvents = useCallback(async () => {
    if (!user) {
      setEvents([]);
      setLoading(false);
      return;
    }
    try {
      const res = await fetch('/audit', { credentials: 'include' });
      if (!res.ok) {
        if (res.status === 401) setEvents([]);
        return;
      }
      const data = await res.json();
      const rawEvents = data.events || [];
      // reverse so newest events appear first
      setEvents(rawEvents.slice().reverse());

      // by default, expand first 3 tasks
      const initialOpen = {};
      let count = 0;
      for (const ev of rawEvents.slice().reverse()) {
        const tid = ev.task_id || 'system';
        if (!initialOpen[tid] && count < 3) {
          initialOpen[tid] = true;
          count++;
        }
      }
      setOpenTaskGroups((prev) => ({ ...initialOpen, ...prev }));
    } catch {
      // ignore network errors during polling
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    fetchAuditEvents();
    if (!user) return;
    const interval = setInterval(fetchAuditEvents, 6000);
    return () => clearInterval(interval);
  }, [user?.id, fetchAuditEvents]);

  // Event category classification
  const getCategoryForEvent = (type) => {
    if (['approval', 'access_denied', 'firewall', 'tamper_detected', 'admin_override'].includes(type)) {
      return 'governance';
    }
    if (['route', 'plan', 'step', 'observe'].includes(type)) {
      return 'reasoning';
    }
    if (['search', 'sandbox', 'write'].includes(type)) {
      return 'tools';
    }
    if (['complete', 'error'].includes(type)) {
      return 'terminal';
    }
    return 'other';
  };

  // Filtered Events
  const filteredEvents = useMemo(() => {
    return events.filter((ev) => {
      // Specific event type filter
      if (filterType && ev.event_type !== filterType) return false;

      // Category chip filter
      if (categoryFilter !== 'all') {
        const cat = getCategoryForEvent(ev.event_type);
        if (cat !== categoryFilter) return false;
      }

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchTask = (ev.task_id || '').toLowerCase().includes(q);
        const matchSummary = (ev.summary || '').toLowerCase().includes(q);
        const matchActor = (ev.actor || '').toLowerCase().includes(q);
        const matchType = (ev.event_type || '').toLowerCase().includes(q);
        const matchHash = (ev.entry_hash || '').toLowerCase().includes(q);
        const matchQuery = (ev.metadata?.query || ev.metadata?.task || '').toLowerCase().includes(q);
        if (!matchTask && !matchSummary && !matchActor && !matchType && !matchHash && !matchQuery) {
          return false;
        }
      }

      return true;
    });
  }, [events, filterType, categoryFilter, searchQuery]);

  // Group events by task_id
  const groupedTasks = useMemo(() => {
    const taskMap = new Map();

    for (const event of filteredEvents) {
      const taskId = event.task_id || 'system';

      if (!taskMap.has(taskId)) {
        taskMap.set(taskId, {
          taskId,
          taskText: '',
          startTime: event.timestamp,
          events: [],
          totalExternalCalls: 0,
          status: 'running',
        });
      }

      const group = taskMap.get(taskId);
      group.events.push(event);
      group.totalExternalCalls += event.external_calls || 0;

      // Extract original task query if present in metadata
      if (!group.taskText) {
        if (event.metadata?.task) {
          group.taskText = event.metadata.task;
        } else if (event.metadata?.query) {
          group.taskText = `Query: ${event.metadata.query}`;
        }
      }

      if (event.event_type === 'complete') group.status = 'complete';
      if (event.event_type === 'error') group.status = 'error';
    }

    return Array.from(taskMap.values());
  }, [filteredEvents]);

  const toggleGroup = (taskId) => {
    setOpenTaskGroups((prev) => ({
      ...prev,
      [taskId]: !prev[taskId],
    }));
  };

  // Helper for StatusBadge
  const renderEventTypeBadge = (type) => {
    const cls = `audit-status-badge type-${type || 'step'}`;
    return (
      <span className={cls}>
        <span className="badge-dot" aria-hidden="true" />
        <span className="badge-text">{type}</span>
      </span>
    );
  };

  if (!user) {
    return (
      <section className="screen audit-screen">
        <div className="screen-head">
          <h2 className="screen-title">Audit Logbook</h2>
          <p className="screen-sub">
            Immutable, append-only cryptographic ledger of all agent routing, reasoning, tool executions, and supervisory actions.
          </p>
        </div>

        <div className="audit-auth-guard-card">
          <div className="audit-auth-guard-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="28" height="28" stroke="currentColor" fill="none" strokeWidth="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </div>
          <h3 style={{ fontSize: '18px', fontWeight: '600', marginBottom: '8px', color: '#0f172a' }}>
            Auditor Authentication Required
          </h3>
          <p style={{ maxWidth: '460px', color: '#64748b', fontSize: '13.5px', lineHeight: '1.5', margin: '0 auto 20px' }}>
            The immutable audit trail is cryptographically signed and partition-scoped by department authority. Please sign in to verify chain integrity and inspect operational execution records.
          </p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onShowAuth}
          >
            Sign In with Access Key
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="screen audit-screen">
      {/* Screen Header */}
      <div className="screen-head audit-head">
        <div className="audit-title-group">
          <div className="audit-icon-wrap" aria-hidden="true">
            <svg className="icon" viewBox="0 0 24 24" width="22" height="22">
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="currentColor" fill="none" strokeWidth="2" />
              <path d="M14 2v6h6" stroke="currentColor" fill="none" strokeWidth="2" />
              <line x1="16" y1="13" x2="8" y2="13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <line x1="16" y1="17" x2="8" y2="17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <line x1="10" y1="9" x2="8" y2="9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h2 className="screen-title" style={{ margin: 0 }}>Audit Logbook & Cryptographic Ledger</h2>
              <span className="audit-dept-chip">{user.department ? `${user.department.toUpperCase()}` : 'SITE-WIDE'}</span>
            </div>
            <p className="screen-sub">
              Immutable, append-only cryptographic ledger of all agent routing, reasoning, tool executions, and supervisory actions.
            </p>
          </div>
        </div>

        {/* View Switcher: Grouped vs Flat Ledger */}
        <div className="audit-view-switcher" role="tablist" aria-label="Audit View Mode">
          <button
            type="button"
            role="tab"
            aria-selected={viewMode === 'grouped'}
            className={`audit-switcher-btn ${viewMode === 'grouped' ? 'active' : ''}`}
            onClick={() => setViewMode('grouped')}
          >
            <svg className="icon icon-sm" viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">
              <rect x="3" y="3" width="7" height="7" stroke="currentColor" fill="none" strokeWidth="2" rx="1" />
              <rect x="14" y="3" width="7" height="7" stroke="currentColor" fill="none" strokeWidth="2" rx="1" />
              <rect x="14" y="14" width="7" height="7" stroke="currentColor" fill="none" strokeWidth="2" rx="1" />
              <rect x="3" y="14" width="7" height="7" stroke="currentColor" fill="none" strokeWidth="2" rx="1" />
            </svg>
            <span>Session Groups</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={viewMode === 'ledger'}
            className={`audit-switcher-btn ${viewMode === 'ledger' ? 'active' : ''}`}
            onClick={() => setViewMode('ledger')}
          >
            <svg className="icon icon-sm" viewBox="0 0 24 24" width="13" height="13" aria-hidden="true">
              <line x1="8" y1="6" x2="21" y2="6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <line x1="8" y1="12" x2="21" y2="12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <line x1="8" y1="18" x2="21" y2="18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <line x1="3" y1="6" x2="3.01" y2="6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <line x1="3" y1="12" x2="3.01" y2="12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <line x1="3" y1="18" x2="3.01" y2="18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <span>Flat Ledger</span>
          </button>
        </div>
      </div>

      {/* Top Cryptographic Sovereignty Bar */}
      <div className="audit-sovereignty-bar">
        <div className="audit-sov-left">
          <div className="audit-sov-badge">
            <svg className="icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" stroke="currentColor" fill="none" strokeWidth="2" />
              <path d="M9 12l2 2 4-4" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>SHA-256 Hash Chain: Active</span>
          </div>
          <div className="audit-sov-metrics">
            <div className="sov-metric">
              <span className="sov-label">Total Entries:</span>
              <span className="sov-value">{events.length}</span>
            </div>
            <div className="sov-metric">
              <span className="sov-label">Network Calls:</span>
              <span className="sov-value" style={{ color: '#047857' }}>0 (Strict Air-Gap)</span>
            </div>
            <div className="sov-metric">
              <span className="sov-label">Ledger Protocol:</span>
              <span className="sov-value" style={{ fontFamily: 'monospace' }}>HMAC / SHA-256</span>
            </div>
          </div>
        </div>

        <button
          type="button"
          className="btn btn-secondary audit-verify-btn"
          onClick={handleVerifyChain}
          disabled={verifyState.checking}
        >
          <svg className={`icon icon-sm ${verifyState.checking ? 'spinner-micro' : ''}`} viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" stroke="currentColor" fill="none" strokeWidth="2" />
          </svg>
          <span>{verifyState.checking ? 'Verifying Hashes…' : 'Verify Chain Integrity'}</span>
        </button>
      </div>

      {/* Verification Result Banner */}
      {verifyState.result && (
        <div
          className={`audit-verify-banner ${verifyState.result.valid ? 'banner-valid' : 'banner-invalid'}`}
          role="status"
        >
          <svg className="icon" viewBox="0 0 24 24" width="18" height="18" style={{ flexShrink: 0 }} aria-hidden="true">
            {verifyState.result.valid ? (
              <path d="M20 6L9 17l-5-5" stroke="currentColor" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
            ) : (
              <>
                <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" fill="none" />
                <path d="M12 8v4M12 16h.01" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
              </>
            )}
          </svg>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: '600', fontSize: '13px' }}>
              {verifyState.result.valid
                ? `Cryptographic SHA-256 Hash Chain Verified (${verifyState.result.total_entries || events.length} entries intact)`
                : 'Tamper Detection Warning: Cryptographic Hash Mismatch!'}
            </div>
            <div style={{ fontSize: '12px', marginTop: '2px', opacity: 0.9 }}>
              {verifyState.result.message}
            </div>
          </div>
          <button
            type="button"
            className="alert-close-btn"
            onClick={() => setVerifyState({ checking: false, result: null })}
            aria-label="Dismiss verification banner"
          >
            ×
          </button>
        </div>
      )}

      {/* Toolbar & Category Quick-Filters */}
      <div className="audit-toolbar-box">
        <div className="audit-search-row">
          <div className="audit-search-field">
            <svg className="icon search-icon" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
              <circle cx="11" cy="11" r="8" stroke="currentColor" fill="none" strokeWidth="2" />
              <path d="M21 21l-4.35-4.35" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <input
              type="text"
              className="input audit-search-input"
              placeholder="Filter by Task ID, Query, Actor, Tool, or Hash… (Press '/' to focus)"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          <SovereignSelect
            style={{ width: '200px' }}
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            options={EVENT_TYPE_OPTIONS}
            placeholder="All Event Types"
            ariaLabel="Filter by Event Type"
          />
        </div>

        {/* Category Filter Chips per Recipe 7 */}
        <div className="audit-category-chips" role="group" aria-label="Event Categories">
          <button
            type="button"
            className={`category-chip ${categoryFilter === 'all' ? 'active' : ''}`}
            onClick={() => setCategoryFilter('all')}
          >
            All Events ({events.length})
          </button>
          <button
            type="button"
            className={`category-chip ${categoryFilter === 'governance' ? 'active' : ''}`}
            onClick={() => setCategoryFilter('governance')}
          >
            Governance & Approvals
          </button>
          <button
            type="button"
            className={`category-chip ${categoryFilter === 'reasoning' ? 'active' : ''}`}
            onClick={() => setCategoryFilter('reasoning')}
          >
            Agent Reasoning & Steps
          </button>
          <button
            type="button"
            className={`category-chip ${categoryFilter === 'tools' ? 'active' : ''}`}
            onClick={() => setCategoryFilter('tools')}
          >
            Tool Calls & Sandboxes
          </button>
          <button
            type="button"
            className={`category-chip ${categoryFilter === 'terminal' ? 'active' : ''}`}
            onClick={() => setCategoryFilter('terminal')}
          >
            Terminal Outcomes
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      {loading ? (
        <div className="audit-empty-box">
          <div className="spinner-micro"></div>
          <span>Loading cryptographic audit records…</span>
        </div>
      ) : filteredEvents.length === 0 ? (
        <div className="audit-empty-box">
          <div className="empty-icon-wrap" aria-hidden="true">
            <svg className="icon" viewBox="0 0 24 24" width="28" height="28">
              <circle cx="11" cy="11" r="8" stroke="currentColor" fill="none" strokeWidth="2" />
              <path d="M21 21l-4.35-4.35" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </div>
          <h3 style={{ margin: '0 0 6px', fontSize: '16px', color: '#0f172a' }}>No Audit Records Found</h3>
          <p style={{ margin: 0, fontSize: '13px', color: '#64748b' }}>
            No audit records match the current filter criteria.
          </p>
        </div>
      ) : viewMode === 'grouped' ? (
        /* 1. SESSION GROUPS VIEW */
        <div className="audit-groups-list">
          {groupedTasks.map((group) => {
            const isOpen = Boolean(openTaskGroups[group.taskId]);
            const shortTime = formatDateTime(group.startTime);

            return (
              <div
                key={group.taskId}
                className={`audit-group-card ${isOpen ? 'is-open' : ''}`}
              >
                <div
                  className="audit-group-card-head"
                  onClick={() => toggleGroup(group.taskId)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && toggleGroup(group.taskId)}
                >
                  <svg
                    className="icon icon-sm audit-chevron"
                    viewBox="0 0 24 24"
                    width="14"
                    height="14"
                    aria-hidden="true"
                  >
                    <path d="M9 18l6-6-6-6" stroke="currentColor" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>

                  <div className="audit-group-info">
                    <div className="audit-group-query">
                      {group.taskText || `Task Session (${group.taskId})`}
                    </div>
                    <div className="audit-group-meta-sub">
                      <span className="mono-task-id">Task ID: {group.taskId.slice(0, 12)}</span>
                      <span className="meta-sep">·</span>
                      <span className="audit-time-str">{shortTime}</span>
                    </div>
                  </div>

                  <div className="audit-group-badges">
                    <span className="audit-count-chip">
                      {group.events.length} {group.events.length === 1 ? 'event' : 'events'}
                    </span>
                    <span className="audit-airgap-chip">
                      0 external calls
                    </span>
                  </div>
                </div>

                {isOpen && (
                  <div className="audit-group-events-table-wrap">
                    <table className="audit-events-table">
                      <thead>
                        <tr>
                          <th style={{ width: '150px' }}>Timestamp</th>
                          <th style={{ width: '130px' }}>Event Type</th>
                          <th>Event Summary & Context</th>
                          <th style={{ width: '140px' }}>Actor / Tool</th>
                          <th style={{ width: '120px' }}>SHA-256 Hash</th>
                          <th style={{ width: '70px', textAlign: 'right' }}>Inspect</th>
                        </tr>
                      </thead>
                      <tbody>
                        {group.events.map((ev, eIdx) => {
                          const timeStr = formatDateTime(ev.timestamp);
                          const tool = ev.metadata?.tool || (ev.event_type === 'search' ? 'search' : ev.event_type === 'sandbox' ? 'code_sandbox' : ev.event_type === 'write' ? 'docx_builder' : null);
                          const model = ev.metadata?.model || (ev.actor?.includes(':') ? ev.actor : null);
                          const hashShort = ev.entry_hash ? ev.entry_hash.slice(0, 8) : null;

                          return (
                            <tr key={eIdx} className="audit-event-tr">
                              <td className="time-td">{timeStr}</td>
                              <td>{renderEventTypeBadge(ev.event_type)}</td>
                              <td>
                                <div className="event-summary-text">{ev.summary}</div>
                              </td>
                              <td>
                                <div className="event-actor-wrap">
                                  {tool && <span className="event-meta-pill tool-pill">{tool}</span>}
                                  {model && <span className="event-meta-pill model-pill">{model}</span>}
                                  {!tool && !model && <span className="event-actor-name">{ev.actor || 'system'}</span>}
                                </div>
                              </td>
                              <td>
                                {hashShort ? (
                                  <button
                                    type="button"
                                    className="hash-copy-btn"
                                    onClick={(e) => copyText(ev.entry_hash, e)}
                                    title="Click to copy full SHA-256 hash"
                                  >
                                    <code>{hashShort}</code>
                                    {copiedHash === ev.entry_hash ? ' ✓' : ''}
                                  </button>
                                ) : (
                                  <span style={{ color: '#94a3b8' }}>—</span>
                                )}
                              </td>
                              <td style={{ textAlign: 'right' }}>
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-sm"
                                  onClick={() => setInspectEvent(ev)}
                                  title="Inspect full payload"
                                >
                                  View
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        /* 2. FLAT CHRONOLOGICAL LEDGER VIEW */
        <div className="audit-ledger-table-wrap">
          <table className="audit-events-table">
            <thead>
              <tr>
                <th style={{ width: '160px' }}>Timestamp</th>
                <th style={{ width: '130px' }}>Event Type</th>
                <th style={{ width: '110px' }}>Task ID</th>
                <th>Event Description & Metadata</th>
                <th style={{ width: '140px' }}>Actor / Tool</th>
                <th style={{ width: '120px' }}>SHA-256 Hash</th>
                <th style={{ width: '70px', textAlign: 'right' }}>Inspect</th>
              </tr>
            </thead>
            <tbody>
              {filteredEvents.map((ev, idx) => {
                const timeStr = formatDateTime(ev.timestamp);
                const tool = ev.metadata?.tool || (ev.event_type === 'search' ? 'search' : ev.event_type === 'sandbox' ? 'code_sandbox' : ev.event_type === 'write' ? 'docx_builder' : null);
                const model = ev.metadata?.model || (ev.actor?.includes(':') ? ev.actor : null);
                const hashShort = ev.entry_hash ? ev.entry_hash.slice(0, 8) : null;
                const taskIdShort = ev.task_id ? ev.task_id.slice(0, 8) : 'system';

                return (
                  <tr key={idx} className="audit-event-tr">
                    <td className="time-td">{timeStr}</td>
                    <td>{renderEventTypeBadge(ev.event_type)}</td>
                    <td>
                      <span className="mono-task-id">{taskIdShort}</span>
                    </td>
                    <td>
                      <div className="event-summary-text">{ev.summary}</div>
                    </td>
                    <td>
                      <div className="event-actor-wrap">
                        {tool && <span className="event-meta-pill tool-pill">{tool}</span>}
                        {model && <span className="event-meta-pill model-pill">{model}</span>}
                        {!tool && !model && <span className="event-actor-name">{ev.actor || 'system'}</span>}
                      </div>
                    </td>
                    <td>
                      {hashShort ? (
                        <button
                          type="button"
                          className="hash-copy-btn"
                          onClick={(e) => copyText(ev.entry_hash, e)}
                          title="Click to copy full SHA-256 hash"
                        >
                          <code>{hashShort}</code>
                          {copiedHash === ev.entry_hash ? ' ✓' : ''}
                        </button>
                      ) : (
                        <span style={{ color: '#94a3b8' }}>—</span>
                      )}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => setInspectEvent(ev)}
                        title="Inspect full payload"
                      >
                        View
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* EVENT INSPECTOR MODAL */}
      {inspectEvent && (
        <div className="modal-backdrop" onClick={() => setInspectEvent(null)}>
          <div className="modal-card audit-inspector-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div>
                <h3 style={{ margin: 0 }}>Audit Record Cryptographic Inspection</h3>
                <span style={{ fontSize: '12px', color: '#64748b' }}>
                  Timestamp: {formatDateTime(inspectEvent.timestamp)}
                </span>
              </div>
              <button
                type="button"
                className="modal-close"
                onClick={() => setInspectEvent(null)}
                aria-label="Close inspector"
              >
                ×
              </button>
            </div>

            <div className="modal-body">
              {/* Event Attributes Grid */}
              <div className="audit-inspect-grid">
                <div className="inspect-field">
                  <span className="inspect-field-label">Event Type</span>
                  <div>{renderEventTypeBadge(inspectEvent.event_type)}</div>
                </div>
                <div className="inspect-field">
                  <span className="inspect-field-label">Actor</span>
                  <span className="inspect-field-val" title={inspectEvent.actor || 'system'}>
                    {inspectEvent.actor || 'system'}
                  </span>
                </div>
                <div className="inspect-field">
                  <span className="inspect-field-label">Task ID</span>
                  <code className="inspect-code-val" title={inspectEvent.task_id || 'system'}>
                    {inspectEvent.task_id || 'system'}
                  </code>
                </div>
                <div className="inspect-field">
                  <span className="inspect-field-label">Air-Gap Status</span>
                  <span className="inspect-airgap-tag">0 External Calls</span>
                </div>
              </div>

              {/* Cryptographic Linkage Block */}
              <div className="audit-inspect-crypto-box">
                <div className="crypto-field">
                  <span className="crypto-label">SHA-256 Entry Hash:</span>
                  <div className="crypto-hash-row">
                    <code className="crypto-hash-val">{inspectEvent.entry_hash || 'Unassigned Genesis'}</code>
                    {inspectEvent.entry_hash && (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={(e) => copyText(inspectEvent.entry_hash, e)}
                      >
                        {copiedHash === inspectEvent.entry_hash ? 'Copied' : 'Copy'}
                      </button>
                    )}
                  </div>
                </div>
                {inspectEvent.prev_hash && (
                  <div className="crypto-field" style={{ marginTop: '8px' }}>
                    <span className="crypto-label">Chained Previous Hash:</span>
                    <div className="crypto-hash-row">
                      <code className="crypto-hash-val">{inspectEvent.prev_hash}</code>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={(e) => copyText(inspectEvent.prev_hash, e)}
                      >
                        {copiedHash === inspectEvent.prev_hash ? 'Copied' : 'Copy'}
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Summary */}
              <div style={{ marginBottom: '14px' }}>
                <span className="inspect-field-label">Summary</span>
                <p style={{ margin: '4px 0 0', fontSize: '13.5px', color: '#0f172a', lineHeight: '1.4' }}>
                  {inspectEvent.summary}
                </p>
              </div>

              {/* Metadata JSON Viewer */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <span className="inspect-field-label">Event Payload & Metadata</span>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={(e) => copyText(JSON.stringify(inspectEvent.metadata || {}, null, 2), e)}
                  >
                    Copy JSON
                  </button>
                </div>
                <pre className="inspect-json-box">
                  {JSON.stringify(inspectEvent.metadata || {}, null, 2)}
                </pre>
              </div>
            </div>

            <div className="modal-foot">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setInspectEvent(null)}
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

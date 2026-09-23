import React, { useState, useEffect, useMemo } from 'react';
import { API_BASE } from '../config';


function formatDateTime(isoStr) {
  if (!isoStr) return '';
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

export default function AuditLogScreen({ user, onShowAuth }) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterType, setFilterType] = useState('');
  const [searchTaskId, setSearchTaskId] = useState('');
  const [openTaskGroups, setOpenTaskGroups] = useState({});

  const fetchAuditEvents = async () => {
    if (!user) {
      setEvents([]);
      setLoading(false);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/audit`, { credentials: 'include' });
      if (!res.ok) {
        if (res.status === 401) setEvents([]);
        return;
      }
      const data = await res.json();
      const rawEvents = data.events || [];
      // reverse so newest tasks appear at the top
      setEvents(rawEvents.slice().reverse());

      // by default, expand the first 3 tasks
      const initialOpen = {};
      let count = 0;
      for (const ev of rawEvents.slice().reverse()) {
        const tid = ev.task_id || 'unassigned';
        if (!initialOpen[tid] && count < 3) {
          initialOpen[tid] = true;
          count++;
        }
      }
      setOpenTaskGroups((prev) => ({ ...initialOpen, ...prev }));
    } catch {
      // ignore network errors
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAuditEvents();
    if (!user) return;
    const interval = setInterval(fetchAuditEvents, 5000);
    return () => clearInterval(interval);
  }, [user?.id]);


  // Group events by task_id and extract original task question per task
  const groupedTasks = useMemo(() => {
    const taskMap = new Map();

    for (const event of events) {
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

      // Check status
      if (event.event_type === 'complete') group.status = 'complete';
      if (event.event_type === 'error') group.status = 'error';
    }

    // Apply filtering
    let groups = Array.from(taskMap.values());

    if (searchTaskId.trim()) {
      const q = searchTaskId.trim().toLowerCase();
      groups = groups.filter(
        (g) =>
          g.taskId.toLowerCase().includes(q) ||
          g.taskText.toLowerCase().includes(q)
      );
    }

    if (filterType) {
      groups = groups
        .map((g) => ({
          ...g,
          events: g.events.filter((e) => e.event_type === filterType),
        }))
        .filter((g) => g.events.length > 0);
    }

    return groups;
  }, [events, filterType, searchTaskId]);

  const toggleGroup = (taskId) => {
    setOpenTaskGroups((prev) => ({
      ...prev,
      [taskId]: !prev[taskId],
    }));
  };

  if (!user) {
    return (
      <section className="screen screen-wide">
        <div className="screen-head">
          <h2 className="screen-title">Audit Logbook</h2>
          <p className="screen-sub">
            Immutable, append-only trail of all routing, planning, and tool executions with strict sovereignty verification.
          </p>
        </div>

        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '60px 20px',
          background: 'rgba(255, 255, 255, 0.02)',
          border: '1px dashed rgba(255, 255, 255, 0.12)',
          borderRadius: '12px',
          marginTop: '20px',
          textAlign: 'center',
        }}>
          <div style={{
            width: '56px',
            height: '56px',
            borderRadius: '50%',
            background: 'rgba(99, 102, 241, 0.15)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: '16px',
          }}>
            <svg viewBox="0 0 24 24" width="28" height="28" stroke="#818cf8" fill="none" strokeWidth="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </div>
          <h3 style={{ fontSize: '18px', fontWeight: '600', marginBottom: '8px', color: 'var(--text-primary, #fff)' }}>
            Authentication Required
          </h3>
          <p style={{ maxWidth: '440px', color: 'var(--text-muted, #94a3b8)', fontSize: '14px', lineHeight: '1.5', marginBottom: '24px' }}>
            Audit log records are strictly partitioned and private to authorized operators. Please sign in or register to review your system and agent execution trail.
          </p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={onShowAuth}
            style={{
              padding: '10px 24px',
              fontSize: '14px',
              fontWeight: '500',
              borderRadius: '8px',
              cursor: 'pointer',
            }}
          >
            Sign In / Register
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="screen screen-wide">
      <div className="screen-head">
        <h2 className="screen-title">Audit Logbook</h2>
        <p className="screen-sub">
          Immutable, append-only trail of all routing, planning, and tool
          executions with strict sovereignty verification.
        </p>
      </div>

      <div className="filters">
        <input
          className="field"
          type="search"
          placeholder="Filter by Task ID or Question text…"
          value={searchTaskId}
          onChange={(e) => setSearchTaskId(e.target.value)}
          style={{ flex: 1 }}
        />
        <select
          className="field"
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
        >
          <option value="">All Event Types</option>
          <option value="route">route</option>
          <option value="plan">plan</option>
          <option value="step">step</option>
          <option value="observe">observe</option>
          <option value="search">search</option>
          <option value="sandbox">sandbox</option>
          <option value="write">write</option>
          <option value="approval">approval</option>
          <option value="firewall">firewall</option>
          <option value="complete">complete</option>
          <option value="error">error</option>
        </select>
      </div>

      {loading ? (
        <div className="empty">Loading audit trail…</div>
      ) : groupedTasks.length === 0 ? (
        <div className="empty">No matching audit events found.</div>
      ) : (
        <div className="audit-task-groups">
          {groupedTasks.map((group) => {
            const isOpen = Boolean(openTaskGroups[group.taskId]);
            const shortTime = formatDateTime(group.startTime);

            return (
              <div
                key={group.taskId}
                className={`audit-task-group ${isOpen ? 'is-open' : ''}`}
              >
                <div
                  className="audit-group-head"
                  onClick={() => toggleGroup(group.taskId)}
                >
                  <svg
                    className="icon icon-sm audit-task-chevron"
                    viewBox="0 0 24 24"
                  >
                    <path d="M9 18l6-6-6-6" />
                  </svg>

                  <div className="audit-task-info">
                    <div className="audit-task-query">
                      {group.taskText || `Task Session (${group.taskId})`}
                    </div>
                    <div className="audit-task-id-badge">
                      Task ID: {group.taskId} · {shortTime}
                    </div>
                  </div>

                  <div className="audit-task-meta">
                    <span className="audit-event-count">
                      {group.events.length} event
                      {group.events.length === 1 ? '' : 's'}
                    </span>
                    <span className="audit-event-calls">
                      external: {group.totalExternalCalls}
                    </span>
                  </div>
                </div>

                {isOpen && (
                  <div className="audit-task-events">
                    {group.events.map((ev, eIdx) => {
                      const timeStr = formatDateTime(ev.timestamp);
                      const tool =

                        ev.metadata?.tool ||
                        (ev.event_type === 'search'
                          ? 'search'
                          : ev.event_type === 'sandbox'
                          ? 'code'
                          : ev.event_type === 'write'
                          ? 'document'
                          : null);
                      const model =
                        ev.metadata?.model ||
                        ev.metadata?.model_tag ||
                        (ev.actor && ev.actor.includes(':')
                          ? ev.actor
                          : null);

                      return (
                        <div key={eIdx} className="audit-event-row">
                          <span className="audit-event-time">{timeStr}</span>
                          <span
                            className={`audit-event-type-badge type-${ev.event_type}`}
                          >
                            {ev.event_type}
                          </span>

                          <div className="audit-event-details">
                            <div className="audit-event-summary">
                              {ev.summary}
                            </div>

                            <div className="audit-event-subinfo">
                              {tool && (
                                <span className="audit-event-tool">
                                  <span>Tool:</span>
                                  <span className="audit-badge-val">
                                    {tool}
                                  </span>
                                </span>
                              )}
                              {model && (
                                <span className="audit-event-model">
                                  <span>Model:</span>
                                  <span className="audit-badge-val">
                                    {model}
                                  </span>
                                </span>
                              )}
                              <span className="audit-event-actor">
                                <span>Actor:</span>
                                <span className="audit-badge-val">
                                  {ev.actor}
                                </span>
                              </span>
                            </div>
                          </div>

                          <span className="audit-event-calls">
                            ext: {ev.external_calls ?? 0}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

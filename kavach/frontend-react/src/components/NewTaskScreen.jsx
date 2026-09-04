import React, { useState, useRef, useEffect, useCallback } from 'react';
import MessageTurn from './MessageTurn';

const GREETINGS = [
  "Where should we begin?",
  "Ready when you are.",
  "What's the task at hand?",
  "SOPs, a calculation, or a report?",
  "How can I help, Operator?",
];

const SUGGESTION_CHIPS = [
  {
    label: "Search SOPs",
    prefill: "Search the knowledge vault for ",
    icon: (
      <svg className="icon icon-sm" viewBox="0 0 24 24">
        <circle cx="11" cy="11" r="7" />
        <path d="M21 21l-4.3-4.3" />
      </svg>
    ),
  },
  {
    label: "Calculate",
    prefill: "Calculate ",
    icon: (
      <svg className="icon icon-sm" viewBox="0 0 24 24">
        <rect x="4" y="3" width="16" height="18" rx="2" />
        <path d="M8 7h8M8 11h.01M12 11h.01M8 15h.01M12 15h.01M16 15h.01" />
      </svg>
    ),
  },
  {
    label: "Draft Report",
    prefill: "Draft a formal report on ",
    icon: (
      <svg className="icon icon-sm" viewBox="0 0 24 24">
        <path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8l-5-5z" />
        <path d="M14 3v5h5" />
      </svg>
    ),
  },
  {
    label: "Run Code",
    prefill: "Write and run a Python script to ",
    icon: (
      <svg className="icon icon-sm" viewBox="0 0 24 24">
        <path d="M8 6L3 12l5 6M16 6l5 6-5 6" />
      </svg>
    ),
  },
  {
    label: "Analyze Scan",
    prefill: "Analyze this scanned document: ",
    icon: (
      <svg className="icon icon-sm" viewBox="0 0 24 24">
        <rect x="3" y="3" width="18" height="18" rx="2" />
        <circle cx="9" cy="9" r="2" />
        <path d="M21 15l-5-5L5 21" />
      </svg>
    ),
  },
];

export default function NewTaskScreen({
  setIsThinking,
  user,
  activeChatId,
  setActiveChatId,
  onShowAuth,
  onChatsUpdated,
}) {
  const [taskInput, setTaskInput] = useState('');
  const [attachedFile, setAttachedFile] = useState(null);
  const [uploadingAttachment, setUploadingAttachment] = useState(false);
  const [greeting] = useState(() => GREETINGS[Math.floor(Math.random() * GREETINGS.length)]);

  // Unified conversation turns
  const [messages, setMessages] = useState([]);
  const [running, setRunning] = useState(false);
  const [approvalOutcome, setApprovalOutcome] = useState({});

  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const chatBottomRef = useRef(null);
  const pollTimerRef = useRef(null);
  const tickerRef = useRef(null);
  const startTimeRef = useRef(0);

  const lastLoadedChatIdRef = useRef(undefined);

  // Load chat messages when activeChatId changes
  useEffect(() => {
    // If activeChatId matches what is already loaded/in-memory, do nothing
    if (activeChatId === lastLoadedChatIdRef.current) {
      return;
    }

    lastLoadedChatIdRef.current = activeChatId;

    // Reset turns and input state on session change
    setMessages([]);
    setTaskInput('');
    setAttachedFile(null);
    setApprovalOutcome({});

    if (!activeChatId) {
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`/chats/${encodeURIComponent(activeChatId)}/messages`, {
          credentials: 'include',
        });
        if (res.ok && !cancelled) {
          const dbMsgs = await res.json();
          setMessages(dbMsgs);
        }
      } catch (err) {
        console.error('Failed to load chat messages:', err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeChatId]);

  // Auto-scroll to bottom of thread
  useEffect(() => {
    if (chatBottomRef.current) {
      chatBottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, running]);

  const handleChipClick = (prefill) => {
    setTaskInput(prefill);
    if (textareaRef.current) {
      textareaRef.current.focus();
      setTimeout(() => {
        if (textareaRef.current) {
          textareaRef.current.style.height = 'auto';
          textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 220)}px`;
          textareaRef.current.setSelectionRange(prefill.length, prefill.length);
        }
      }, 0);
    }
  };

  const handleInputChange = (e) => {
    setTaskInput(e.target.value);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 220)}px`;
    }
  };

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

  // Live audit event parser for in-flight assistant turn
  const applyAuditEvents = useCallback((events, asstTurnId) => {
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

    const finished = after.some((e) => e.event_type === 'complete' || e.event_type === 'error');
    const activeIndex = rawSteps.findIndex((s) => s.status === 'pending');

    let statusText = 'Planning steps…';
    const revisions = after.filter(
      (e) => e.event_type === 'observe' && e.metadata?.decision === 'revise'
    ).length;

    if (revisions > 0) {
      statusText = `Self-correcting after an error (revision ${revisions})…`;
    } else if (activeIndex !== -1 && activeIndex < rawSteps.length) {
      const cur = rawSteps[activeIndex];
      statusText = `Step ${activeIndex + 1}/${rawSteps.length}: Running ${cur.tool}…`;
    } else if (finished) {
      statusText = 'Finalizing output…';
    } else if (rawSteps.some((s) => s.status !== 'pending')) {
      statusText = 'Working through steps…';
    }

    let modelMeta = '';
    const route = events.find((e) => e.event_type === 'route');
    if (route) {
      const role = route.metadata?.model_role;
      modelMeta = `${role || 'Model'} · ${route.metadata?.model_tag || ''}`;
    }

    setMessages((prev) =>
      prev.map((msg) => {
        if (msg.id === asstTurnId) {
          return {
            ...msg,
            steps: rawSteps,
            statusText,
            modelMeta: modelMeta || msg.modelMeta,
          };
        }
        return msg;
      })
    );
  }, []);

  // Run Task Execution with Optimistic UI Updates
  const runTask = async (promptOverride = null) => {
    const task = (promptOverride || taskInput).trim();
    if (!task || running) return;

    const taskId = crypto.randomUUID();
    const fullTask = attachedFile?.path ? `${task}\n\nAttached file: ${attachedFile.path}` : task;

    const tempUserId = `temp-user-${Date.now()}`;
    const tempAsstId = `temp-asst-${Date.now()}`;

    const userTurn = {
      id: tempUserId,
      role: 'user',
      content: task,
      created_at: new Date().toISOString(),
      meta: { attachment_type: attachedFile ? 'file' : null, task_id: taskId },
    };

    const asstTurn = {
      id: tempAsstId,
      role: 'assistant',
      is_streaming: true,
      task_id: taskId,
      statusText: 'Planning steps…',
      steps: [],
      content: '',
      retryPrompt: fullTask,
      created_at: new Date().toISOString(),
    };

    // Extract prior conversation history to send to backend
    const priorHistory = messages
      .filter((m) => !m.is_streaming && !m.is_error)
      .map((m) => ({
        role: m.role,
        content: m.content || m.result || '',
      }));

    // Optimistically append user message and streaming assistant turn immediately
    setMessages((prev) => [...prev, userTurn, asstTurn]);
    setTaskInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    setRunning(true);
    setIsThinking(true);
    startTimeRef.current = Date.now();

    // Ticker for elapsed seconds
    tickerRef.current = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTimeRef.current) / 1000);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === tempAsstId ? { ...m, statusText: `${m.statusText?.split(' (')[0] || 'Working…'} (${elapsed}s)` } : m
        )
      );
    }, 1000);

    // Audit poll for live progress
    pollTimerRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/audit?task_id=${encodeURIComponent(taskId)}`);
        if (res.ok) {
          const data = await res.json();
          applyAuditEvents(data.events || [], tempAsstId);
        }
      } catch {
        // ignore poll error
      }
    }, 1000);

    try {
      const response = await fetch('/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          task: fullTask,
          task_id: taskId,
          chat_id: activeChatId || undefined,
          history: priorHistory,
        }),
      });

      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }

      const data = await response.json();

      clearInterval(pollTimerRef.current);
      clearInterval(tickerRef.current);

      // If backend auto-created a new chat, update lastLoadedChatIdRef first to avoid clearing!
      if (data.chat_id && data.chat_id !== activeChatId) {
        lastLoadedChatIdRef.current = data.chat_id;
        setActiveChatId(data.chat_id);
      }
      if (onChatsUpdated) {
        onChatsUpdated();
      }

      // Final audit sync
      try {
        const auditRes = await fetch(`/audit?task_id=${encodeURIComponent(taskId)}`);
        if (auditRes.ok) {
          const auditData = await auditRes.json();
          applyAuditEvents(auditData.events || [], tempAsstId);
        }
      } catch {
        // ignore
      }

      // Finalize assistant message with full rich payload

      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.id === tempAsstId) {
            return {
              ...msg,
              is_streaming: false,
              content: data.result || '',
              result: data.result || '',
              status: data.status,
              steps: data.steps || data.plan || msg.steps || [],
              step_outputs: data.step_outputs || [],
              sources: data.sources || [],
              generated_files: data.generated_files || [],
              code_runs: data.code_runs || [],
              approval: data.approval || null,
              draft_content: data.draft_content || null,
              modelMeta: data.model_used ? `Model · ${data.model_used}` : msg.modelMeta,
              meta: {
                task_id: taskId,
                status: data.status,
                steps: data.steps || data.plan || [],
                step_outputs: data.step_outputs || [],
                sources: data.sources || [],
                generated_files: data.generated_files || [],
                code_runs: data.code_runs || [],
                approval: data.approval || null,
                draft_content: data.draft_content || null,
                model_used: data.model_used,
                routing_decision: data.routing_decision,
              },
            };
          }
          return msg;
        })
      );
    } catch (err) {
      clearInterval(pollTimerRef.current);
      clearInterval(tickerRef.current);

      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.id === tempAsstId) {
            return {
              ...msg,
              is_streaming: false,
              is_error: true,
              errorMsg: `Task execution failed: ${err.message}`,
              retryPrompt: fullTask,
            };
          }
          return msg;
        })
      );
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

  // Human approval handlers
  const handleApprovalAction = async (taskId, decision) => {
    setApprovalOutcome((prev) => ({
      ...prev,
      [taskId]: { loading: true, message: `Processing ${decision}…` },
    }));

    try {
      const res = await fetch(`/approval/${encodeURIComponent(taskId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
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

  const handleApprovalEditSubmit = async (taskId, editTitle, editSections) => {
    let parsedSections = [];
    try {
      parsedSections = JSON.parse(editSections);
      if (!Array.isArray(parsedSections)) {
        parsedSections = [{ heading: 'Summary', body: editSections }];
      }
    } catch {
      parsedSections = [{ heading: 'Summary', body: editSections }];
    }

    setApprovalOutcome((prev) => ({
      ...prev,
      [taskId]: { loading: true, message: 'Rendering edited document…' },
    }));

    try {
      const res = await fetch(`/approval/${encodeURIComponent(taskId)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
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

  const hasMessages = messages.length > 0;

  return (
    <section className="screen-task-container" id="screen-task">
      {/* Scrollable Chat Area */}
      <div className="chat-scroll-area" id="chat-scroll-area">
        {/* Landing State: Greeting & Suggestion Chips (when thread is empty) */}
        {!hasMessages && (
          <div className="landing-hero" id="landing-hero">
            <div className="greeting-wrap" id="greeting-wrap">
              <h1 className="greeting">
                <svg className="greeting-icon icon" viewBox="0 0 24 24">
                  <path d="M12 3l7 3v5.5c0 4.2-2.9 8.1-7 9.5-4.1-1.4-7-5.3-7-9.5V6l7-3z" />
                </svg>
                <span id="greeting-text">{greeting}</span>
              </h1>
            </div>

            <div className="suggestion-chips" id="suggestion-chips">
              {SUGGESTION_CHIPS.map((chip) => (
                <button
                  key={chip.label}
                  className="chip"
                  onClick={() => handleChipClick(chip.prefill)}
                >
                  {chip.icon}
                  <span>{chip.label}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Unified Continuous Chat Thread */}
        {hasMessages && (
          <div className="chat-thread" id="chat-thread">
            {messages.map((turn) => (
              <MessageTurn
                key={turn.id}
                turn={{ ...turn, approvalOutcome }}
                user={user}
                onApprovalAction={handleApprovalAction}
                onApprovalEditSubmit={handleApprovalEditSubmit}
                onRetry={(prompt) => runTask(prompt)}
              />
            ))}
            <div ref={chatBottomRef} style={{ height: '1px' }} />
          </div>
        )}
      </div>

      {/* Pinned Bottom Input Area (Never moves, pinned to bottom of viewport) */}
      <div className="chat-composer-fixed" id="chat-composer-fixed">
        <div className="composer">
          <textarea
            ref={textareaRef}
            id="task-input"
            rows={1}
            placeholder="Ask about an SOP, run a calculation, or draft a report…"
            value={taskInput}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={running}
          />

          {attachedFile && (
            <div className="attachment" id="attachment">
              <svg className="icon icon-sm" viewBox="0 0 24 24">
                <path d="M14 4l-7.5 7.5a3 3 0 004.2 4.2L18 8.5" />
              </svg>
              <span id="attachment-name">{attachedFile.name}</span>
              <button
                id="attachment-clear"
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
              className="composer-plus-btn"
              id="attach-btn"
              onClick={() => fileInputRef.current?.click()}
              disabled={running || uploadingAttachment}
              title="Attach a file"
            >
              <svg className="icon" viewBox="0 0 24 24">
                <path d="M12 5v14M5 12h14" />
              </svg>
            </button>
            <input
              type="file"
              id="file-input"
              ref={fileInputRef}
              onChange={handleFileChange}
              hidden
            />

            <div className="composer-spacer" />

            <button
              className="send-btn"
              id="send-btn"
              onClick={() => runTask()}
              disabled={!taskInput.trim() || running}
              title="Run task"
            >
              <svg className="icon" viewBox="0 0 24 24">
                <path d="M12 19V5M6 11l6-6 6 6" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}


import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import MessageTurn from './MessageTurn';
import { API_BASE } from '../config';

const GREETINGS = [
  "What can I help with today?",
  "What would you like to solve?",
  "How can I assist you today?",
  "Ready for your next task.",
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
    label: "Excel Sheet",
    prefill: "Create a generator fuel and cost analysis spreadsheet with formulas: ",
    icon: (
      <svg className="icon icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <rect x="3" y="3" width="18" height="18" rx="2" strokeWidth="2" />
        <path d="M3 9h18M3 15h18M9 3v18M15 3v18" strokeWidth="1.5" />
      </svg>
    ),
  },
  {
    label: "PPT Slides",
    prefill: "Create a 4-slide executive presentation briefing on ",
    icon: (
      <svg className="icon icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <rect x="2" y="3" width="20" height="14" rx="2" strokeWidth="2" />
        <path d="M8 21h8M12 17v4" strokeWidth="2" strokeLinecap="round" />
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
  const [attachedFiles, setAttachedFiles] = useState([]);
  const [uploadingAttachment, setUploadingAttachment] = useState(false);
  const [taggedVaultFiles, setTaggedVaultFiles] = useState([]);
  const [vaultDocs, setVaultDocs] = useState([]);
  const [loadingVaultDocs, setLoadingVaultDocs] = useState(false);
  const [showMentionPopover, setShowMentionPopover] = useState(false);
  const [mentionFilter, setMentionFilter] = useState('');
  const [mentionSelectedIndex, setMentionSelectedIndex] = useState(0);
  const [isDragOver, setIsDragOver] = useState(false);
  const [greeting] = useState(() => GREETINGS[Math.floor(Math.random() * GREETINGS.length)]);

  // Unified conversation turns
  const [messages, setMessages] = useState([]);
  const [running, setRunning] = useState(false);
  const [approvalOutcome, setApprovalOutcome] = useState({});

  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);
  const chatBottomRef = useRef(null);
  const popoverRef = useRef(null);
  const pollTimerRef = useRef(null);
  const tickerRef = useRef(null);
  const startTimeRef = useRef(0);

  const lastLoadedChatIdRef = useRef(undefined);

  // Fetch Knowledge Vault document list for @ mention autocomplete
  const fetchVaultDocs = useCallback(async () => {
    try {
      setLoadingVaultDocs(true);
      const res = await fetch(`${API_BASE}/knowledge/list`, { credentials: 'include' });
      if (res.ok) {
        const data = await res.json();
        setVaultDocs(data.documents || []);
      }
    } catch (err) {
      console.error('Failed to load knowledge vault documents:', err);
    } finally {
      setLoadingVaultDocs(false);
    }
  }, []);

  // Pre-load vault documents when user or active screen is ready
  useEffect(() => {
    fetchVaultDocs();
  }, [user?.id, fetchVaultDocs]);

  // Click outside to dismiss mention popover
  useEffect(() => {
    const handleGlobalClick = (e) => {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(e.target) &&
        textareaRef.current &&
        !textareaRef.current.contains(e.target) &&
        !e.target.closest('#mention-btn')
      ) {
        setShowMentionPopover(false);
      }
    };
    document.addEventListener('mousedown', handleGlobalClick);
    return () => document.removeEventListener('mousedown', handleGlobalClick);
  }, []);

  // Filtered vault docs based on what operator typed after '@'
  const filteredVaultDocs = useMemo(() => {
    if (!mentionFilter) return vaultDocs;
    const q = mentionFilter.toLowerCase().trim();
    return vaultDocs.filter((d) => d.filename.toLowerCase().includes(q));
  }, [vaultDocs, mentionFilter]);

  // Select a vault document from the @-mention popover
  const selectVaultDoc = (filename) => {
    if (!filename) return;
    if (!taggedVaultFiles.includes(filename)) {
      setTaggedVaultFiles((prev) => [...prev, filename]);
    }
    // Cleanly erase the trailing '@query' from task input text
    if (textareaRef.current) {
      const pos = textareaRef.current.selectionStart || taskInput.length;
      const before = taskInput.slice(0, pos);
      const after = taskInput.slice(pos);
      const atIdx = before.lastIndexOf('@');
      if (atIdx !== -1) {
        const cleaned = before.slice(0, atIdx) + after;
        setTaskInput(cleaned);
        setTimeout(() => {
          if (textareaRef.current) {
            textareaRef.current.focus();
            textareaRef.current.setSelectionRange(atIdx, atIdx);
            textareaRef.current.style.height = 'auto';
            textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 220)}px`;
          }
        }, 0);
      }
    }
    setShowMentionPopover(false);
    setMentionFilter('');
    setMentionSelectedIndex(0);
  };

  const handleToggleMention = () => {
    if (showMentionPopover) {
      setShowMentionPopover(false);
    } else {
      fetchVaultDocs();
      setShowMentionPopover(true);
      setMentionFilter('');
      setMentionSelectedIndex(0);
      if (textareaRef.current) {
        textareaRef.current.focus();
      }
    }
  };

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
    setAttachedFiles([]);
    setTaggedVaultFiles([]);
    setApprovalOutcome({});

    if (!activeChatId) {
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(`${API_BASE}/chats/${encodeURIComponent(activeChatId)}/messages`, {
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
      chatBottomRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
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
    const val = e.target.value;
    const cursorPos = e.target.selectionStart;
    setTaskInput(val);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 220)}px`;
    }

    // Inspect if user typed '@' or is typing a mention filter query
    const textBeforeCursor = val.slice(0, cursorPos);
    const atMatch = textBeforeCursor.match(/@([a-zA-Z0-9_\-.]*)$/);
    if (atMatch) {
      setMentionFilter(atMatch[1] || '');
      setShowMentionPopover(true);
      setMentionSelectedIndex(0);
      if (vaultDocs.length === 0) {
        fetchVaultDocs();
      }
    } else {
      setShowMentionPopover(false);
    }
  };

  const handleKeyDown = (e) => {
    if (showMentionPopover) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setMentionSelectedIndex((prev) => (prev + 1) % (filteredVaultDocs.length || 1));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setMentionSelectedIndex((prev) => (prev - 1 + (filteredVaultDocs.length || 1)) % (filteredVaultDocs.length || 1));
        return;
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        if (filteredVaultDocs.length > 0) {
          e.preventDefault();
          selectVaultDoc(filteredVaultDocs[mentionSelectedIndex]?.filename);
          return;
        }
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setShowMentionPopover(false);
        return;
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if ((taskInput.trim() || attachedFile || taggedVaultFiles.length > 0) && !running) {
        runTask();
      }
    }
  };

  const formatFileSize = (bytes) => {
    if (!bytes && bytes !== 0) return '';
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const getFileTypeCategory = (filename) => {
    const ext = (filename || '').split('.').pop()?.toLowerCase();
    if (ext === 'pdf') return 'pdf';
    if (['png', 'jpg', 'jpeg', 'webp', 'bmp', 'tiff', 'gif'].includes(ext)) return 'img';
    if (['doc', 'docx', 'txt', 'md'].includes(ext)) return 'doc';
    if (['xls', 'xlsx', 'csv'].includes(ext)) return 'sheet';
    return 'default';
  };

  const uploadSingleFile = async (tempId, file) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('ingest', 'false');

    try {
      const res = await fetch(`${API_BASE}/knowledge/upload`, {
        method: 'POST',
        body: formData,
      });

      let data = {};
      const contentType = res.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        try {
          data = await res.json();
        } catch {
          data = {};
        }
      } else {
        const textError = await res.text().catch(() => '');
        data = { detail: textError || res.statusText };
      }

      if (!res.ok) {
        throw new Error(data.detail || data.error || res.statusText || `Server error (${res.status})`);
      }

      setAttachedFiles((prev) =>
        prev.map((f) =>
          f.id === tempId
            ? {
                ...f,
                name: data.filename || file.name,
                path: data.file_path,
                status: 'ready',
              }
            : f
        )
      );
    } catch (err) {
      setAttachedFiles((prev) =>
        prev.map((f) =>
          f.id === tempId
            ? {
                ...f,
                status: 'error',
                error: err.message,
              }
            : f
        )
      );
    }
  };

  const processFiles = (fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length) return;

    setUploadingAttachment(true);
    const newItems = files.map((file) => {
      const tempId = `file-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      const isImg = ['png', 'jpg', 'jpeg', 'webp', 'bmp', 'tiff', 'gif'].includes(
        (file.name || '').split('.').pop()?.toLowerCase()
      );
      return {
        id: tempId,
        fileObj: file,
        name: file.name,
        size: file.size,
        path: null,
        status: 'uploading',
        category: getFileTypeCategory(file.name),
        previewUrl: isImg ? URL.createObjectURL(file) : null,
      };
    });

    // Append to existing attachments (supports both sequential and bulk additions)
    setAttachedFiles((prev) => [...prev, ...newItems]);

    // Kick off uploads concurrently
    Promise.allSettled(newItems.map((item) => uploadSingleFile(item.id, item.fileObj))).finally(() => {
      setUploadingAttachment(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    });
  };

  const handleFileChange = (e) => {
    processFiles(e.target.files);
  };

  const removeAttachment = (id) => {
    setAttachedFiles((prev) => {
      const target = prev.find((f) => f.id === id);
      if (target?.previewUrl) {
        URL.revokeObjectURL(target.previewUrl);
      }
      return prev.filter((f) => f.id !== id);
    });
  };

  const clearAllAttachments = () => {
    attachedFiles.forEach((f) => {
      if (f.previewUrl) URL.revokeObjectURL(f.previewUrl);
    });
    setAttachedFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!running) setIsDragOver(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
    if (running) return;
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processFiles(e.dataTransfer.files);
    }
  };

  const renderAttachmentIcon = (category, previewUrl) => {
    if (category === 'img' && previewUrl) {
      return <img src={previewUrl} alt="preview" className="attachment-chip-img" />;
    }
    if (category === 'pdf') {
      return (
        <svg className="icon icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          <polyline points="14 2 14 8 20 8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          <line x1="16" y1="13" x2="8" y2="13" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          <line x1="16" y1="17" x2="8" y2="17" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          <polyline points="10 9 9 9 8 9" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    }
    if (category === 'sheet') {
      return (
        <svg className="icon icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <rect x="3" y="3" width="18" height="18" rx="2" strokeWidth="2" />
          <line x1="3" y1="9" x2="21" y2="9" strokeWidth="2" />
          <line x1="3" y1="15" x2="21" y2="15" strokeWidth="2" />
          <line x1="9" y1="3" x2="9" y2="21" strokeWidth="2" />
          <line x1="15" y1="3" x2="15" y2="21" strokeWidth="2" />
        </svg>
      );
    }
    if (category === 'img') {
      return (
        <svg className="icon icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor">
          <rect x="3" y="3" width="18" height="18" rx="2" strokeWidth="2" />
          <circle cx="8.5" cy="8.5" r="1.5" strokeWidth="2" />
          <polyline points="21 15 16 10 5 21" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      );
    }
    return (
      <svg className="icon icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <polyline points="14 2 14 8 20 8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
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
      if (event.event_type === 'route') {
        const step = rawSteps.find((s) => s.step_num === event.metadata?.step_num);
        if (step) {
          if (event.metadata?.model_tag) step.model = event.metadata.model_tag;
          if (event.metadata?.model_role) step.model_role = event.metadata.model_role;
          if (event.metadata?.task_type) step.tool = event.metadata.task_type;
        }
      }
      if (event.event_type === 'step') {
        const step = rawSteps.find((s) => s.step_num === event.metadata?.step_num);
        if (step) {
          step.status = event.metadata?.error ? 'failed' : 'done';
          if (event.metadata?.model) step.model = event.metadata.model;
          if (event.metadata?.model_role) step.model_role = event.metadata.model_role;
        }
      }
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
      const modelHint = cur.model ? ` · ${cur.model}` : '';
      statusText = `Step ${activeIndex + 1}/${rawSteps.length}: Running ${cur.tool}${modelHint}…`;
    } else if (finished) {
      statusText = 'Finalizing output…';
    } else if (rawSteps.some((s) => s.status !== 'pending')) {
      statusText = 'Working through steps…';
    }

    let modelMeta = '';
    const distinctModels = Array.from(
      new Set(
        after
          .filter((e) => e.event_type === 'route' || e.event_type === 'step')
          .map((e) => e.metadata?.model_tag || e.metadata?.model)
          .filter((m) => m && !m.endsWith('_tool') && m !== 'vault_search')
      )
    );
    if (distinctModels.length > 1) {
      modelMeta = `Models · ${distinctModels.join(' → ')}`;
    } else if (distinctModels.length === 1) {
      modelMeta = `Model · ${distinctModels[0]}`;
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
    const readyAttachments = attachedFiles.filter((f) => f.status === 'ready' && f.path);
    let fullTask = task;
    if (readyAttachments.length === 1) {
      fullTask = `${task}\n\nAttached file: ${readyAttachments[0].path}`;
    } else if (readyAttachments.length > 1) {
      const filesFormatted = readyAttachments.map((f) => `Attached file: ${f.path}`).join('\n');
      fullTask = `${task}\n\n${filesFormatted}`;
    }

    const hasImageAttachment = readyAttachments.some(
      (f) => f.category === 'img' || (f.path && /\.(png|jpg|jpeg|webp|bmp|tiff)$/i.test(f.path))
    );
    const attachmentType = readyAttachments.length > 0 ? (hasImageAttachment ? 'image' : 'file') : null;

    const tempUserId = `temp-user-${Date.now()}`;
    const tempAsstId = `temp-asst-${Date.now()}`;

    const userTurn = {
      id: tempUserId,
      role: 'user',
      content: task,
      attachments: readyAttachments.map((f) => ({
        name: f.name,
        path: f.path,
        size: f.size,
        category: f.category,
      })),
      created_at: new Date().toISOString(),
      meta: {
        attachment_type: attachmentType,
        attachments: readyAttachments.map((f) => ({ name: f.name, path: f.path, size: f.size, category: f.category })),
        vault_files: taggedVaultFiles.length > 0 ? [...taggedVaultFiles] : null,
        task_id: taskId,
      },
      vault_files: taggedVaultFiles.length > 0 ? [...taggedVaultFiles] : null,
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
    setTaggedVaultFiles([]);
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

    let streamUrl = `${API_BASE}/run/stream?task=${encodeURIComponent(fullTask)}&task_id=${encodeURIComponent(taskId)}${activeChatId ? `&chat_id=${encodeURIComponent(activeChatId)}` : ''}${attachmentType ? `&attachment_type=${encodeURIComponent(attachmentType)}` : ''}`;
    if (taggedVaultFiles.length > 0) {
      taggedVaultFiles.forEach((vf) => {
        streamUrl += `&vault_files=${encodeURIComponent(vf)}`;
      });
    }
    const eventSource = new EventSource(streamUrl, { withCredentials: true });

    eventSource.addEventListener('plan', (e) => {
      try {
        const d = JSON.parse(e.data);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === tempAsstId
              ? {
                  ...m,
                  steps: d.steps || [],
                  statusText: `Plan established: ${d.step_count} step(s)…`,
                  modelMeta: d.model ? `Planner · ${d.model}` : m.modelMeta,
                }
              : m
          )
        );
      } catch {}
    });

    eventSource.addEventListener('step_start', (e) => {
      try {
        const d = JSON.parse(e.data);
        setMessages((prev) =>
          prev.map((m) => {
            if (m.id !== tempAsstId) return m;
            const updatedSteps = (m.steps || []).map((s) =>
              s.step_num === d.step_num ? { ...s, status: 'executing', model: d.model, tool: d.tool } : s
            );
            return {
              ...m,
              steps: updatedSteps,
              statusText: `Step ${d.step_num}/${d.total_steps}: Executing [${d.tool}] with ${d.model}…`,
            };
          })
        );
      } catch {}
    });

    eventSource.addEventListener('tool_done', (e) => {
      try {
        const d = JSON.parse(e.data);
        setMessages((prev) =>
          prev.map((m) => {
            if (m.id !== tempAsstId) return m;
            const updatedSteps = (m.steps || []).map((s) =>
              s.step_num === d.step_num ? { ...s, status: d.error ? 'failed' : 'done' } : s
            );
            return {
              ...m,
              steps: updatedSteps,
              key_facts: d.key_facts || m.key_facts,
            };
          })
        );
      } catch {}
    });

    eventSource.addEventListener('observe', (e) => {
      try {
        const d = JSON.parse(e.data);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === tempAsstId
              ? {
                  ...m,
                  statusText: `Observe: ${d.action.toUpperCase()} — ${d.reasoning}`,
                }
              : m
          )
        );
      } catch {}
    });

    eventSource.addEventListener('replan', (e) => {
      try {
        const d = JSON.parse(e.data);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === tempAsstId
              ? {
                  ...m,
                  steps: d.plan || m.steps,
                  statusText: `Dynamic Replan #${d.replan_count}: ${d.reasoning}`,
                }
              : m
          )
        );
      } catch {}
    });

    eventSource.addEventListener('revise', (e) => {
      try {
        const d = JSON.parse(e.data);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === tempAsstId
              ? {
                  ...m,
                  steps: d.plan || (m.steps || []).map((s) =>
                    s.step === d.step
                      ? { ...s, status: 'revising', input: d.revised_input || s.input }
                      : s
                  ),
                  statusText: `Self-Correction (Retry #${d.retry_count}): Revising Step ${d.step} — ${d.reason || ''}`,
                }
              : m
          )
        );
      } catch {}
    });

    eventSource.addEventListener('clarify', (e) => {
      try {
        const d = JSON.parse(e.data);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === tempAsstId
              ? {
                  ...m,
                  clarify_question: d.question,
                  statusText: 'Awaiting your clarification…',
                }
              : m
          )
        );
      } catch {}
    });

    eventSource.addEventListener('done_stream', (e) => {
      try {
        const data = JSON.parse(e.data);
        eventSource.close();
        clearInterval(tickerRef.current);

        if (data.chat_id && data.chat_id !== activeChatId) {
          lastLoadedChatIdRef.current = data.chat_id;
          setActiveChatId(data.chat_id);
        }
        if (onChatsUpdated) onChatsUpdated();

        setMessages((prev) =>
          prev.map((msg) => {
            if (msg.id === tempAsstId) {
              return {
                ...msg,
                is_streaming: false,
                content: data.result || '',
                result: data.result || '',
                status: data.status,
                clarify_question: data.clarify_question,
                key_facts: data.key_facts,
                steps: data.steps || data.plan || msg.steps || [],
                step_outputs: data.step_outputs || [],
                sources: data.sources || [],
                generated_files: data.generated_files || [],
                code_runs: data.code_runs || [],
                approval: data.approval || null,
                draft_content: data.draft_content || null,
                trace: data.trace || [],
                modelMeta:
                  data.models_used && data.models_used.length > 1
                    ? `Models · ${data.models_used.join(' → ')}`
                    : data.model_used
                    ? `Model · ${data.model_used}`
                    : msg.modelMeta,
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
                  models_used: data.models_used || (data.model_used ? [data.model_used] : []),
                  routing_decision: data.routing_decision,
                  clarify_question: data.clarify_question,
                  key_facts: data.key_facts,
                },
              };
            }
            return msg;
          })
        );
      } catch (err) {
        console.error('Error handling done_stream', err);
      } finally {
        setRunning(false);
        setIsThinking(false);
        setAttachedFiles([]);
      }
    });

    eventSource.addEventListener('error', (e) => {
      eventSource.close();
      clearInterval(tickerRef.current);
      setRunning(false);
      setIsThinking(false);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === tempAsstId
            ? {
                ...msg,
                is_streaming: false,
                is_error: true,
                errorMsg: 'Streaming connection interrupted.',
                retryPrompt: fullTask,
              }
            : msg
        )
      );
    });
  };

  const handleClarifyReply = async (taskId, replyText) => {
    if (!replyText.trim()) return;
    setRunning(true);

    const replyMsgId = `user-reply-${Date.now()}`;
    setMessages((prev) => [
      ...prev.map((m) =>
        m.task_id === taskId || m.meta?.task_id === taskId
          ? {
              ...m,
              statusText: 'Resuming task with clarification…',
              clarify_question: null,
            }
          : m
      ),
      {
        id: replyMsgId,
        role: 'user',
        content: replyText,
        created_at: new Date().toISOString(),
      },
    ]);

    try {
      const res = await fetch(`${API_BASE}/run/${encodeURIComponent(taskId)}/reply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ reply: replyText, chat_id: activeChatId || undefined }),
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const data = await res.json();
      setMessages((prev) =>
        prev.map((m) =>
          m.task_id === taskId || m.meta?.task_id === taskId
            ? {
                ...m,
                content: data.result || m.content,
                result: data.result || m.result,
                status: data.status,
                clarify_question: null,
                statusText: data.status === 'complete' ? 'Completed' : `Status: ${data.status}`,
                steps: data.steps || data.plan || m.steps,
                trace: data.trace || m.trace,
                meta: {
                  ...m.meta,
                  clarify_question: null,
                  status: data.status,
                  steps: data.steps || data.plan || [],
                  step_outputs: data.step_outputs || [],
                  key_facts: data.key_facts || {},
                },
              }
            : m
        )
      );
      if (onChatsUpdated) onChatsUpdated();
    } catch (err) {
      alert(`Failed to send clarification: ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  // Human approval handlers
  const handleApprovalAction = async (taskId, decision) => {
    setApprovalOutcome((prev) => ({
      ...prev,
      [taskId]: { loading: true, message: `Processing ${decision}…` },
    }));

    try {
      const res = await fetch(`${API_BASE}/approval/${encodeURIComponent(taskId)}`, {
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
      const res = await fetch(`${API_BASE}/approval/${encodeURIComponent(taskId)}`, {
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
                onClarifyReply={handleClarifyReply}
                onRetry={(prompt) => runTask(prompt)}
              />
            ))}
            <div ref={chatBottomRef} style={{ height: '1px' }} />
          </div>
        )}
      </div>

      {/* Pinned Bottom Input Area (Never moves, pinned to bottom of viewport) */}
      <div className="chat-composer-fixed" id="chat-composer-fixed">
        <div
          className={`composer ${isDragOver ? 'is-drag-over' : ''}`}
          style={{ position: 'relative' }}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {/* Mention Popover Floating Dropdown */}
          {showMentionPopover && (
            <div className="mention-popover" ref={popoverRef} id="mention-popover">
              <div className="mention-popover-header">
                <svg className="icon icon-sm" viewBox="0 0 24 24">
                  <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                  <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                </svg>
                <span>Knowledge Vault Documents</span>
                <span className="mention-hint-key">↑↓ to navigate · ↵ to select</span>
                <span className="mention-hint-touch">Tap to select</span>
              </div>
              <div className="mention-popover-list">
                {loadingVaultDocs && (
                  <div className="mention-popover-empty">Loading vault documents…</div>
                )}
                {!loadingVaultDocs && filteredVaultDocs.length === 0 && (
                  <div className="mention-popover-empty">
                    {vaultDocs.length === 0
                      ? 'No documents in Knowledge Vault yet.'
                      : `No vault files matching "${mentionFilter}"`}
                  </div>
                )}
                {!loadingVaultDocs &&
                  filteredVaultDocs.map((doc, idx) => (
                    <div
                      key={doc.filename}
                      className={`mention-item ${idx === mentionSelectedIndex ? 'is-selected' : ''}`}
                      onMouseEnter={() => setMentionSelectedIndex(idx)}
                      onClick={() => selectVaultDoc(doc.filename)}
                    >
                      <div className="mention-item-icon">
                        <svg className="icon icon-sm" viewBox="0 0 24 24">
                          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                          <polyline points="14 2 14 8 20 8" />
                          <line x1="16" y1="13" x2="8" y2="13" />
                          <line x1="16" y1="17" x2="8" y2="17" />
                        </svg>
                      </div>
                      <div className="mention-item-info">
                        <span className="mention-item-title">{doc.filename}</span>
                      </div>
                      <span className="mention-item-chunks">
                        {doc.chunk_count} chunk{doc.chunk_count === 1 ? '' : 's'}
                      </span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {/* Attached Knowledge Vault Chips */}
          {taggedVaultFiles.length > 0 && (
            <div className="composer-attachments-row" id="composer-attachments-row">
              {taggedVaultFiles.map((filename) => (
                <div key={filename} className="vault-chip" title="Knowledge Vault Document Reference">
                  <svg className="icon icon-sm" viewBox="0 0 24 24">
                    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
                  </svg>
                  <span className="vault-chip-name">{filename}</span>
                  <button
                    type="button"
                    className="vault-chip-remove"
                    onClick={() => setTaggedVaultFiles((prev) => prev.filter((f) => f !== filename))}
                    title="Remove vault document"
                  >
                    <svg className="icon icon-sm" viewBox="0 0 24 24">
                      <path d="M6 6l12 12M18 6L6 18" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          )}

          <textarea
            ref={textareaRef}
            id="task-input"
            rows={1}
            placeholder="Message Kavach or reference @document…"
            value={taskInput}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            disabled={running}
          />

          {attachedFiles.length > 0 && (
            <div className="attachment-tray" id="attachment-tray">
              {attachedFiles.map((file) => (
                <div
                  key={file.id}
                  className={`attachment-chip ${file.status === 'uploading' ? 'is-uploading' : ''} ${file.status === 'error' ? 'is-error' : ''}`}
                  title={file.error ? `Error: ${file.error}` : file.name}
                >
                  <div className={`attachment-chip-preview preview-${file.category}`}>
                    {renderAttachmentIcon(file.category, file.previewUrl)}
                  </div>
                  <div className="attachment-chip-info">
                    <span className="attachment-chip-name">{file.name}</span>
                    <span className="attachment-chip-meta">
                      {file.status === 'uploading'
                        ? 'Uploading…'
                        : file.status === 'error'
                        ? 'Failed'
                        : formatFileSize(file.size)}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="attachment-chip-remove"
                    onClick={() => removeAttachment(file.id)}
                    title="Remove attachment"
                  >
                    <svg className="icon icon-sm" viewBox="0 0 24 24">
                      <path d="M6 6l12 12M18 6L6 18" />
                    </svg>
                  </button>
                </div>
              ))}

              {attachedFiles.length > 1 && (
                <button
                  type="button"
                  className="attachment-clear-all"
                  onClick={clearAllAttachments}
                  title="Clear all attachments"
                >
                  Clear all
                </button>
              )}
            </div>
          )}

          <div className="composer-bar">
            <button
              className="composer-plus-btn"
              id="attach-btn"
              onClick={() => fileInputRef.current?.click()}
              disabled={running || uploadingAttachment}
              title="Attach files (bulk or sequential)"
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
              multiple
              hidden
            />

            <button
              className={`composer-mention-btn ${showMentionPopover || taggedVaultFiles.length > 0 ? 'is-active' : ''}`}
              id="mention-btn"
              onClick={handleToggleMention}
              disabled={running}
              title="Reference a Knowledge Vault document (@)"
            >
              <svg className="icon" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="4" />
                <path d="M16 8v5a3 3 0 0 0 6 0v-1a10 10 0 1 0-3.92 7.94" />
              </svg>
            </button>

            <div className="composer-spacer" />

            <button
              className="send-btn"
              id="send-btn"
              onClick={() => runTask()}
              disabled={(!taskInput.trim() && attachedFiles.length === 0 && taggedVaultFiles.length === 0) || running}
              title="Run task"
            >
              <svg className="icon" viewBox="0 0 24 24">
                <path d="M12 19V5M6 11l6-6 6 6" />
              </svg>
            </button>
          </div>
        </div>

        <div className="composer-disclaimer">
          Kavach is an air-gapped sovereign AI. Verify critical operational outputs.
        </div>
      </div>
    </section>
  );
}

